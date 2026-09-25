from __future__ import annotations

import argparse, json, logging, sys
from datetime import date, datetime, timezone
from pathlib import Path
from sqlalchemy import func, select, text

from .config import data_dir
from .db import get_engine
from .exporter import export_csv, export_xlsx
from .importer import import_xlsx
from .query import latest_data_date, lead_query
from .schema import classifications, contractors, licenses, metadata, source_imports
from .validation import validation_report
from .changes import compare_snapshots, list_changes
from .inventory import build_inventory
from .source import fetch_source


def parser():
    p=argparse.ArgumentParser(prog="freshtradeleads",description="Import, query, and export normalized CSLB contractor lead data.")
    p.add_argument("--json",action="store_true",help="emit machine-readable JSON to stdout")
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="check database, directories, and current source snapshot")
    imp=sub.add_parser("import-file",help="idempotently import a CSLB XLSX source snapshot"); imp.add_argument("file")
    sub.add_parser("stats",help="show database and recent-license statistics")
    val=sub.add_parser("validate",help="generate a detailed validation report for the latest completed import"); val.add_argument("--out",type=Path)
    source=sub.add_parser("source",help="acquire official CSLB source data"); source_sub=source.add_subparsers(dest="source_command",required=True)
    fetch=source_sub.add_parser("fetch",help="fetch, validate, hash, and conditionally import the official master XLSX")
    changes=sub.add_parser("changes",help="compare or inspect immutable source snapshots"); change_sub=changes.add_subparsers(dest="changes_command",required=True)
    latest=change_sub.add_parser("latest",help="compare the latest completed import with its predecessor"); latest.add_argument("--examples",type=int,default=10)
    listing=change_sub.add_parser("list",help="list persisted changes"); listing.add_argument("--since",type=date.fromisoformat); listing.add_argument("--type",dest="change_type"); listing.add_argument("--limit",type=int,default=100)
    inventory=sub.add_parser("inventory",help="analyze commercial inventory and generate candidate packs"); inv_sub=inventory.add_subparsers(dest="inventory_command",required=True)
    build=inv_sub.add_parser("build",help="build inventory matrix, quality audit, rankings, and sample reports"); build.add_argument("--no-packs",action="store_true")
    for name in ["search","export"]:
        q=sub.add_parser(name,help=f"{name} filtered lead records")
        q.add_argument("--classification"); q.add_argument("--county"); q.add_argument("--city"); q.add_argument("--zip"); q.add_argument("--zip-prefix"); q.add_argument("--status"); q.add_argument("--days",type=int); q.add_argument("--from",dest="issue_from",type=date.fromisoformat); q.add_argument("--to",dest="issue_to",type=date.fromisoformat); q.add_argument("--business-type"); q.add_argument("--workers-comp-type"); q.add_argument("--limit",type=int,default=50 if name=="search" else None)
        if name=="export": q.add_argument("--format",choices=["xlsx","csv"],default="xlsx"); q.add_argument("--out",type=Path)
    return p


def emit(value, as_json=False):
    if as_json: print(json.dumps(value,default=str,indent=2))
    elif isinstance(value,list):
        for row in value: print(" | ".join(f"{k}: {v}" for k,v in row.items()))
    elif isinstance(value,dict):
        for k,v in value.items(): print(f"{k}: {v}")
    else: print(value)


def filters(args):
    return dict(classification=args.classification,county=args.county,city=args.city,zip_code=args.zip,zip_prefix=args.zip_prefix,status=args.status,days=args.days,issue_from=args.issue_from,issue_to=args.issue_to,business_type=args.business_type,workers_comp_type=args.workers_comp_type)


def main(argv=None):
    args=parser().parse_args(argv); logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    engine=get_engine(); metadata.create_all(engine)
    try:
        if args.command=="doctor":
            d=data_dir(); d.mkdir(parents=True,exist_ok=True)
            with engine.connect() as c: c.execute(text("select 1")); snap=c.execute(select(source_imports).where(source_imports.c.status=="complete").order_by(source_imports.c.id.desc()).limit(1)).mappings().first()
            emit({"ok":True,"database":"connected","data_dir":str(d),"data_dir_writable":d.exists(),"latest_snapshot":dict(snap) if snap else None},args.json); return
        if args.command=="import-file": emit(import_xlsx(engine,args.file),args.json); return
        if args.command=="stats":
            with engine.connect() as c:
                anchor=latest_data_date(c); result={"contractors":c.scalar(select(func.count()).select_from(contractors)),"licenses":c.scalar(select(func.count()).select_from(licenses)),"classifications":c.scalar(select(func.count()).select_from(classifications)),"source_data_date":anchor}
                for days in [7,14,30,60,90]: result[f"issued_last_{days}_days"]=c.scalar(select(func.count()).select_from(licenses).where(licenses.c.original_issue_date>=anchor-__import__("datetime").timedelta(days=days-1),licenses.c.original_issue_date<=anchor)) if anchor else 0
            emit(result,args.json); return
        if args.command=="validate":
            with engine.connect() as c: result=validation_report(c)
            if args.out:
                args.out.parent.mkdir(parents=True,exist_ok=True); args.out.write_text(json.dumps(result,default=str,indent=2)+"\n",encoding="utf-8"); result={"ok":True,"path":str(args.out.resolve()),"summary":{k:result[k] for k in ["workbook_rows","records_imported","rejected_rows","newest_issue_date","recent_issue_counts"]}}
            emit(result,args.json); return
        if args.command=="source":
            def pipeline(import_id, source_date):
                with engine.connect() as c: validation=validation_report(c)
                validation_path=data_dir()/"processed"/f"validation_{source_date}.json"; validation_path.parent.mkdir(parents=True,exist_ok=True); validation_path.write_text(json.dumps(validation,default=str,indent=2)+"\n",encoding="utf-8")
                change=compare_snapshots(engine,import_id,data_dir()/"processed")
                return {"validation_path":str(validation_path),"change_report_paths":change["paths"],"change_counts":change["counts"]}
            emit(fetch_source(engine,data_dir()/"raw",run_pipeline=pipeline),args.json); return
        if args.command=="changes":
            if args.changes_command=="latest":
                with engine.connect() as c: current_id=c.scalar(select(source_imports.c.id).where(source_imports.c.status=="complete").order_by(source_imports.c.id.desc()).limit(1))
                emit(compare_snapshots(engine,current_id,data_dir()/"processed",example_limit=args.examples),args.json); return
            with engine.connect() as c: emit(list_changes(c,since=args.since,change_type=args.change_type,limit=args.limit),args.json); return
        if args.command=="inventory":
            emit(build_inventory(engine,data_dir(),Path("/opt/freshtradeleads/docs"),generate_packs=not args.no_packs),args.json); return
        with engine.connect() as c:
            anchor=latest_data_date(c); stmt=lead_query(**filters(args),anchor_date=anchor,dialect_name=engine.dialect.name)
            if args.command=="search":
                rows=[dict(r) for r in c.execute(stmt.limit(args.limit)).mappings()]; emit(rows,args.json); return
            rows=[dict(r) for r in c.execute(stmt).mappings()]
            snap=c.execute(select(source_imports).where(source_imports.c.status=="complete").order_by(source_imports.c.id.desc()).limit(1)).mappings().one()
        fmt=args.format; out=args.out or data_dir()/"exports"/f"leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"
        meta={"generated_at":datetime.now(timezone.utc).isoformat(),"source_as_of":str(snap["newest_issue_date"]),"source_sha256":snap["sha256"]}; columns=list(rows[0]) if rows else [c.key for c in stmt.selected_columns]
        (export_xlsx if fmt=="xlsx" else export_csv)(rows,columns,out,meta)
        emit({"ok":True,"path":str(out.resolve()),"format":fmt,"records":len(rows),**meta},args.json)
    except Exception as exc:
        if args.json: print(json.dumps({"ok":False,"error":str(exc)}))
        else: print(f"error: {exc}",file=sys.stderr)
        raise SystemExit(1)
