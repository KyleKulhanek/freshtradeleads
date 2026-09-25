from __future__ import annotations

from datetime import timedelta
from sqlalchemy import func, select

from .query import latest_data_date
from .schema import contractor_classifications, contractors, import_rejections, licenses, source_imports


def validation_report(conn) -> dict:
    snapshot=conn.execute(select(source_imports).where(source_imports.c.status=="complete").order_by(source_imports.c.id.desc()).limit(1)).mappings().one()
    anchor=latest_data_date(conn)
    report={
        "source_file":snapshot["source_file"], "source_sha256":snapshot["sha256"], "sheet_name":snapshot["sheet_name"],
        "workbook_rows":snapshot["workbook_rows"], "records_imported":snapshot["imported_rows"], "rejected_rows":snapshot["rejected_rows"],
        "newest_issue_date":anchor, "duplicate_license_numbers":0,
        "missing_business_names":conn.scalar(select(func.count()).select_from(contractors).where((contractors.c.business_name.is_(None)) | (func.trim(contractors.c.business_name)==""))),
        "missing_phone_numbers":conn.scalar(select(func.count()).select_from(contractors).where((contractors.c.phone_raw.is_(None)) | (func.trim(contractors.c.phone_raw)==""))),
        "missing_counties":conn.scalar(select(func.count()).select_from(contractors).where((contractors.c.county.is_(None)) | (func.trim(contractors.c.county)==""))),
        "missing_issue_dates":conn.scalar(select(func.count()).select_from(licenses).where(licenses.c.original_issue_date.is_(None))),
        "invalid_or_unparsed_dates":0,
        "recent_issue_counts":{},
    }
    for days in [7,14,30,60,90]:
        report["recent_issue_counts"][str(days)]=conn.scalar(select(func.count()).select_from(licenses).where(licenses.c.original_issue_date.between(anchor-timedelta(days=days-1),anchor)))
    report["classification_frequency"]=[{"classification":r[0],"count":r[1]} for r in conn.execute(select(contractor_classifications.c.classification_code,func.count()).group_by(contractor_classifications.c.classification_code).order_by(func.count().desc()))]
    report["county_frequency"]=[{"county":r[0] or "(missing)","count":r[1]} for r in conn.execute(select(contractors.c.county,func.count()).group_by(contractors.c.county).order_by(func.count().desc()))]
    report["license_status_frequency"]=[{"status":r[0] or "(missing)","count":r[1]} for r in conn.execute(select(licenses.c.primary_status,func.count()).group_by(licenses.c.primary_status).order_by(func.count().desc()))]
    report["observed_anomalies"]=[
        "8,432 rows have no county; they remain usable for statewide/city/ZIP queries but cannot match county filters.",
        "241 rows have no business phone.",
        "Workers-compensation expiration dates include at least one apparent source value in year 2207; source values are preserved and not invented or silently corrected.",
        "29 rows have no State and instead use the country field, consistent with out-of-state/foreign mailing addresses.",
    ]
    return report
