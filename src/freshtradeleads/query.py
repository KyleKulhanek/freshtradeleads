from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy import and_, func, select

from .schema import bonds, classifications, contractor_classifications, contractors, licenses, source_imports, workers_comp


def latest_data_date(conn) -> date | None:
    return conn.execute(select(func.max(source_imports.c.newest_issue_date)).where(source_imports.c.status == "complete")).scalar()


def lead_query(*, classification=None, county=None, city=None, zip_code=None, zip_prefix=None, status=None, days=None, issue_from=None, issue_to=None, business_type=None, workers_comp_type=None, anchor_date=None, dialect_name="postgresql"):
    agg = func.group_concat if dialect_name == "sqlite" else func.string_agg
    class_agg = select(contractor_classifications.c.license_number, agg(contractor_classifications.c.classification_code, " | ").label("classification_codes")).group_by(contractor_classifications.c.license_number).subquery()
    class_desc = select(contractor_classifications.c.license_number, agg(func.coalesce(classifications.c.description, contractor_classifications.c.classification_code), " | ").label("classification_descriptions")).join(classifications, classifications.c.code==contractor_classifications.c.classification_code).group_by(contractor_classifications.c.license_number).subquery()
    cb = select(bonds).where(bonds.c.bond_type=="contractor").subquery()
    q=select(contractors.c.business_name.label("Business Name"),licenses.c.license_number.label("License Number"),class_agg.c.classification_codes.label("Classification Code(s)"),class_desc.c.classification_descriptions.label("Trade / Classification Description"),licenses.c.original_issue_date.label("Original Issue Date"),licenses.c.primary_status.label("Current License Status"),contractors.c.business_type.label("Business Type"),contractors.c.phone_raw.label("Phone"),contractors.c.mailing_address.label("Address"),contractors.c.city.label("City"),contractors.c.county.label("County"),contractors.c.state.label("State"),contractors.c.zip_code.label("ZIP"),workers_comp.c.coverage_type.label("Workers Compensation Coverage Type"),workers_comp.c.carrier.label("Workers Compensation Carrier"),cb.c.surety_company.label("Contractor Bond Surety"),cb.c.amount.label("Contractor Bond Amount")).join(licenses,licenses.c.contractor_id==contractors.c.id).outerjoin(class_agg,class_agg.c.license_number==licenses.c.license_number).outerjoin(class_desc,class_desc.c.license_number==licenses.c.license_number).outerjoin(workers_comp,workers_comp.c.license_number==licenses.c.license_number).outerjoin(cb,cb.c.license_number==licenses.c.license_number)
    conditions=[]
    if classification: conditions.append(licenses.c.license_number.in_(select(contractor_classifications.c.license_number).where(func.upper(contractor_classifications.c.classification_code)==classification.upper())))
    if county: conditions.append(func.lower(contractors.c.county)==county.lower())
    if city: conditions.append(func.lower(contractors.c.city)==city.lower())
    if zip_code: conditions.append(contractors.c.zip_code==zip_code)
    if zip_prefix: conditions.append(contractors.c.zip_code.like(zip_prefix+"%"))
    if status: conditions.append(func.lower(licenses.c.primary_status)==status.lower())
    if business_type: conditions.append(func.lower(contractors.c.business_type)==business_type.lower())
    if workers_comp_type: conditions.append(func.lower(workers_comp.c.coverage_type)==workers_comp_type.lower())
    if days is not None:
        if not anchor_date: raise ValueError("anchor_date required with days")
        if days < 1: raise ValueError("days must be at least 1")
        conditions.extend([licenses.c.original_issue_date >= anchor_date-timedelta(days=days-1), licenses.c.original_issue_date <= anchor_date])
    if issue_from: conditions.append(licenses.c.original_issue_date>=issue_from)
    if issue_to: conditions.append(licenses.c.original_issue_date<=issue_to)
    return q.where(and_(*conditions)).order_by(licenses.c.original_issue_date.desc(), licenses.c.license_number)
