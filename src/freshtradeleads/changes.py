from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, insert, or_, select

from .parsing import parse_classifications
from .schema import license_snapshots, snapshot_changes, source_imports


def _norm(value: Any) -> Any:
    if value is None: return None
    if isinstance(value, str):
        cleaned = re.sub(r"\s+", " ", value).strip()
        return cleaned.upper() if cleaned else None
    return value


def _view(raw: dict | None, fields: list[str]) -> dict:
    raw = raw or {}
    return {field: _norm(raw.get(field)) for field in fields}


def _categories(raw: dict | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "status-change": _view(raw, ["PrimaryStatus", "SecondaryStatus", "PendingSuspension"]),
        "classification-change": sorted(parse_classifications(raw.get("Classifications(s)"))),
        "workers-comp-change": _view(raw, ["WorkersCompCoverageType", "WCInsuranceCompany", "WCPolicyNumber", "WCEffectiveDate", "WCExpirationDate", "WCCancellationDate", "WCSuspendDate"]),
        "bond-change": {
            "contractor": _view(raw, ["CBSuretyCompany", "CBNumber", "CBEffectiveDate", "CBCancellationDate", "CBAmount"]),
            "worker": _view(raw, ["WBSuretyCompany", "WBNumber", "WBEffectiveDate", "WBCancellationDate", "WBAmount"]),
            "disciplinary": _view(raw, ["DBSuretyCompany", "DBNumber", "DBEffectiveDate", "DBCancellationDate", "DBAmount", "DateRequired", "DiscpCaseRegion", "DBBondReason", "DBCaseNo"]),
        },
    }


def _write_reports(report: dict, processed_dir: Path) -> dict:
    processed_dir.mkdir(parents=True, exist_ok=True)
    stamp = report["current_source_date"] or f"import-{report['current_import_id']}"
    basename=f"change_report_{stamp}_import_{report['current_import_id']}"
    json_path = processed_dir / f"{basename}.json"
    md_path = processed_dir / f"{basename}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    lines=[f"# CSLB change report — {stamp}","",f"Previous import: {report['previous_import_id'] or 'none (baseline)'}",f"Current import: {report['current_import_id']}",f"Previous hash: `{report['previous_hash'] or 'n/a'}`",f"Current hash: `{report['current_hash']}`","","## Counts",""]
    for key,value in report["counts"].items(): lines.append(f"- {key}: {value:,}")
    lines.extend(["","## Representative examples",""])
    for kind,examples in report["examples"].items():
        lines.append(f"### {kind}"); lines.append("")
        if not examples: lines.append("None.")
        for example in examples: lines.append(f"- License `{example['license_number']}`: `{example.get('old_value')}` → `{example.get('new_value')}`")
        lines.append("")
    for warning in report["warnings"]: lines.append(f"> Warning: {warning}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json":str(json_path),"markdown":str(md_path)}


def compare_snapshots(engine, current_import_id: int, processed_dir: Path, *, example_limit: int = 10) -> dict:
    with engine.connect() as connection:
        current=connection.execute(select(source_imports).where(source_imports.c.id==current_import_id,source_imports.c.status=="complete")).mappings().one()
        previous=connection.execute(select(source_imports).where(source_imports.c.status=="complete",source_imports.c.id<current_import_id).order_by(source_imports.c.id.desc()).limit(1)).mappings().first()
    report={"generated_at":datetime.now(timezone.utc).isoformat(),"previous_import_id":previous["id"] if previous else None,"current_import_id":current_import_id,"previous_source_date":str(previous["newest_issue_date"]) if previous else None,"current_source_date":str(current["newest_issue_date"]),"previous_hash":previous["sha256"] if previous else None,"current_hash":current["sha256"],"previous_rows":previous["imported_rows"] if previous else 0,"current_rows":current["imported_rows"],"counts":{},"examples":{},"warnings":[]}
    if not previous:
        report["counts"]={kind:0 for kind in ["new-source-record","newly-licensed","status-change","classification-change","workers-comp-change","bond-change","source-record-removed"]}
        report["warnings"].append("No previous completed source snapshot exists; this import is the comparison baseline.")
        report["paths"]=_write_reports(report,processed_dir); return report
    old=select(license_snapshots).where(license_snapshots.c.import_id==previous["id"]).subquery("old")
    new=select(license_snapshots).where(license_snapshots.c.import_id==current_import_id).subquery("new")
    joined=old.join(new,old.c.license_number==new.c.license_number,full=True)
    stmt=select(func.coalesce(old.c.license_number,new.c.license_number).label("license_number"),old.c.raw_record.label("old_raw"),new.c.raw_record.label("new_raw"),old.c.row_hash.label("old_hash"),new.c.row_hash.label("new_hash")).select_from(joined)
    counts=Counter(); examples={}; pending=[]
    with engine.begin() as connection:
        connection.execute(delete(snapshot_changes).where(snapshot_changes.c.current_import_id==current_import_id))
        for row in connection.execution_options(stream_results=True).execute(stmt).mappings():
            lic=row["license_number"]; old_raw=row["old_raw"]; new_raw=row["new_raw"]
            found=[]
            if old_raw is None: found.append(("new-source-record",None,None,new_raw))
            elif new_raw is None: found.append(("source-record-removed",None,old_raw,None))
            elif row["old_hash"] != row["new_hash"]:
                old_cat=_categories(old_raw); new_cat=_categories(new_raw)
                for kind in old_cat:
                    if old_cat[kind] != new_cat[kind]: found.append((kind,None,old_cat[kind],new_cat[kind]))
            if new_raw is not None:
                try: issue=datetime.strptime(str(new_raw.get("IssueDate","")).strip(),"%m/%d/%Y").date()
                except ValueError: issue=None
                if issue and issue > previous["newest_issue_date"]: found.append(("newly-licensed","IssueDate",None,new_raw.get("IssueDate")))
            for kind,field,old_value,new_value in found:
                counts[kind]+=1
                pending.append({"previous_import_id":previous["id"],"current_import_id":current_import_id,"license_number":lic,"change_type":kind,"field_name":field,"old_value":old_value,"new_value":new_value})
                examples.setdefault(kind,[])
                if len(examples[kind])<example_limit: examples[kind].append({"license_number":lic,"old_value":old_value,"new_value":new_value})
            if len(pending)>=1000: connection.execute(insert(snapshot_changes),pending); pending=[]
        if pending: connection.execute(insert(snapshot_changes),pending)
    all_types=["new-source-record","newly-licensed","status-change","classification-change","workers-comp-change","bond-change","source-record-removed"]
    report["counts"]={kind:counts[kind] for kind in all_types}; report["examples"]={kind:examples.get(kind,[]) for kind in all_types}
    if counts["source-record-removed"]: report["warnings"].append("Records absent from the current master are labeled removed-from-source, not cancelled or revoked; the CSLB master excludes some non-renewable licenses.")
    report["paths"]=_write_reports(report,processed_dir); return report


def list_changes(connection, *, current_import_id: int | None = None, since: date | None = None, change_type: str | None = None, limit: int = 100) -> list[dict]:
    query=select(snapshot_changes)
    if current_import_id: query=query.where(snapshot_changes.c.current_import_id==current_import_id)
    if since:
        ids=select(source_imports.c.id).where(source_imports.c.status=="complete",source_imports.c.newest_issue_date>=since)
        query=query.where(snapshot_changes.c.current_import_id.in_(ids))
    if change_type: query=query.where(snapshot_changes.c.change_type==change_type)
    return [dict(row) for row in connection.execute(query.order_by(snapshot_changes.c.current_import_id.desc(),snapshot_changes.c.license_number).limit(limit)).mappings()]
