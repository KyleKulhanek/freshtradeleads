from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func, insert, select, update

from .query import lead_query
from .schema import (
    contractor_classifications, contractors, license_snapshots, licenses,
    products, source_imports,
)

SOCAL_COUNTIES = ["Los Angeles", "Orange", "Riverside", "San Bernardino", "San Diego", "Ventura"]
PRODUCT_DEFINITIONS = (
    {"sku":"starter","name":"Starter","description":"The 10 newest matching C10 Southern California leads.","price_cents":1500,"currency":"usd","classification_code":"C10","counties":SOCAL_COUNTIES,"window_days":None,"lead_limit":10,"recommended":False,"active":True},
    {"sku":"fresh-pack","name":"Fresh Pack","description":"All matching C10 Southern California leads from the last 14 days.","price_cents":2900,"currency":"usd","classification_code":"C10","counties":SOCAL_COUNTIES,"window_days":14,"lead_limit":None,"recommended":True,"active":True},
    {"sku":"expanded","name":"Expanded","description":"All matching C10 Southern California leads from the last 30 days.","price_cents":5900,"currency":"usd","classification_code":"C10","counties":SOCAL_COUNTIES,"window_days":30,"lead_limit":None,"recommended":False,"active":True},
)

REPORT_COLUMNS = ["Business Name","License Number","Classification Code(s)","Trade / Classification Description","Original Issue Date","Current License Status","Business Type","Phone","Address","City","County","State","ZIP","Workers Compensation Coverage Type","Workers Compensation Carrier","Contractor Bond Surety","Contractor Bond Amount"]


def seed_products(conn) -> None:
    for definition in PRODUCT_DEFINITIONS:
        existing = conn.execute(select(products.c.sku).where(products.c.sku == definition["sku"])).scalar_one_or_none()
        if existing:
            conn.execute(update(products).where(products.c.sku == definition["sku"]).values(**definition, updated_at=datetime.now(timezone.utc)))
        else:
            conn.execute(insert(products).values(**definition))


def latest_import(conn) -> dict[str, Any]:
    row = conn.execute(select(source_imports).where(source_imports.c.status == "complete").order_by(source_imports.c.completed_at.desc(), source_imports.c.id.desc()).limit(1)).mappings().first()
    if not row:
        raise RuntimeError("No completed source import is available")
    return dict(row)


def _eligible_statement(product: dict, source_date: date):
    stmt = select(licenses.c.license_number).join(contractors, contractors.c.id == licenses.c.contractor_id).where(
        licenses.c.license_number.in_(select(contractor_classifications.c.license_number).where(func.upper(contractor_classifications.c.classification_code) == product["classification_code"])),
        func.lower(contractors.c.county).in_([c.lower() for c in product["counties"]]),
        licenses.c.original_issue_date <= source_date,
    ).order_by(licenses.c.original_issue_date.desc(), licenses.c.license_number.desc())
    if product.get("window_days"):
        stmt = stmt.where(licenses.c.original_issue_date >= source_date - timedelta(days=product["window_days"] - 1))
    if product.get("lead_limit"):
        stmt = stmt.limit(product["lead_limit"])
    return stmt


def product_lead_ids(conn, product: dict, source_date: date) -> list[str]:
    return list(conn.execute(_eligible_statement(product, source_date)).scalars())


def inventory(conn) -> tuple[dict, list[dict]]:
    seed_products(conn)
    snapshot = latest_import(conn)
    result = []
    for row in conn.execute(select(products).where(products.c.active.is_(True)).order_by(products.c.price_cents)).mappings():
        item = dict(row)
        item["lead_ids"] = product_lead_ids(conn, item, snapshot["newest_issue_date"])
        item["lead_count"] = len(item["lead_ids"])
        result.append(item)
    return snapshot, result


def current_preview(conn, count: int = 5) -> list[dict]:
    snapshot, items = inventory(conn)
    fresh = next(x for x in items if x["sku"] == "fresh-pack")
    if not fresh["lead_ids"]:
        return []
    rows = conn.execute(select(
        licenses.c.license_number, licenses.c.original_issue_date, licenses.c.primary_status,
        contractors.c.phone_raw,
    ).join(contractors, contractors.c.id == licenses.c.contractor_id).where(licenses.c.license_number.in_(fresh["lead_ids"][:count]))).mappings()
    by_id = {r["license_number"]: r for r in rows}
    return [{"lead_number": i, "trade":"C10 Electrical", "region":"Southern California", "issued":by_id[lid]["original_issue_date"], "status":by_id[lid]["primary_status"], "phone_included":bool(by_id[lid]["phone_raw"])} for i, lid in enumerate(fresh["lead_ids"][:count], 1)]


def report_rows(conn, license_numbers: list[str], *, import_id: int | None = None) -> list[dict]:
    if not license_numbers:
        return []
    if import_id is None:
        snapshot = latest_import(conn)
        import_id = snapshot["id"]
    raw_rows = conn.execute(select(license_snapshots.c.license_number, license_snapshots.c.raw_record).where(license_snapshots.c.import_id == import_id, license_snapshots.c.license_number.in_(license_numbers))).all()
    raw_by_id = {str(k): v for k, v in raw_rows}
    def parse_amount(value):
        try: return Decimal(str(value).replace(",", "")) if value not in (None, "") else None
        except Exception: return None
    def parse_date(value):
        if isinstance(value, date): return value
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try: return datetime.strptime(str(value), fmt).date()
            except (ValueError, TypeError): pass
        return None
    output=[]
    for lid in license_numbers:
        r=raw_by_id.get(str(lid));
        if not r: continue
        classes=str(r.get("Classifications(s)") or "").replace("|", " | ")
        output.append({"Business Name":r.get("FullBusinessName") or r.get("BusinessName"),"License Number":str(r.get("LicenseNo") or lid),"Classification Code(s)":classes,"Trade / Classification Description":"Electrical (C10)" if "C10" in classes.upper() else classes,"Original Issue Date":parse_date(r.get("IssueDate")),"Current License Status":r.get("PrimaryStatus"),"Business Type":r.get("BusinessType"),"Phone":r.get("BusinessPhone"),"Address":r.get("MailingAddress"),"City":r.get("City"),"County":r.get("County"),"State":r.get("State"),"ZIP":str(r.get("ZIPCode") or ""),"Workers Compensation Coverage Type":r.get("WorkersCompCoverageType"),"Workers Compensation Carrier":r.get("WCInsuranceCompany"),"Contractor Bond Surety":r.get("CBSuretyCompany"),"Contractor Bond Amount":parse_amount(r.get("CBAmount"))})
    return output


def historical_sample(conn, count: int = 5) -> tuple[dict, list[dict]]:
    snapshot = latest_import(conn); anchor=snapshot["newest_issue_date"]
    stmt = select(licenses.c.license_number).join(contractors, contractors.c.id == licenses.c.contractor_id).where(
        licenses.c.license_number.in_(select(contractor_classifications.c.license_number).where(func.upper(contractor_classifications.c.classification_code) == "C10")),
        func.lower(contractors.c.county).in_([c.lower() for c in SOCAL_COUNTIES]),
        licenses.c.original_issue_date.between(anchor-timedelta(days=120), anchor-timedelta(days=90)),
        func.lower(licenses.c.primary_status) == "clear",
        contractors.c.business_name.is_not(None), contractors.c.phone_raw.is_not(None), contractors.c.mailing_address.is_not(None), contractors.c.zip_code.is_not(None),
    ).order_by(licenses.c.original_issue_date.desc(), licenses.c.license_number).limit(count)
    ids=list(conn.execute(stmt).scalars())
    if len(ids) < count:
        raise RuntimeError(f"Only {len(ids)} commercially complete historical sample records found")
    return snapshot, report_rows(conn, ids, import_id=snapshot["id"])
