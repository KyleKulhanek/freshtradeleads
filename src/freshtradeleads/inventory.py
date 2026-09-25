from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import and_, func, select, update

from .exporter import export_xlsx
from .query import lead_query, latest_data_date
from .parsing import CLASSIFICATION_DESCRIPTIONS
from .schema import bonds, classifications, contractor_classifications, contractors, licenses, source_imports, workers_comp

SOUTHERN_CALIFORNIA_COUNTIES=("Los Angeles","Orange","Riverside","San Bernardino","San Diego","Ventura")
CORE_TRADES={"A","B","C10","C20","C27","C33","C36","C39"}
WINDOWS=(7,14,30,60,90)


def _pct(value,total): return round(value*100/total,1) if total else 0.0


def _score(row):
    count=row["total_newly_issued"]
    volume=max(0,100-abs(count-47.5)*1.45) if 20<=count<=75 else max(0,60-min(abs(count-20),abs(count-75))*2)
    relevance=100 if row["classification_code"] in CORE_TRADES else (70 if row["classification_code"].startswith("C") else 40)
    geography=100 if row["geography_type"]=="county" else (95 if row["geography_type"]=="region" else 75)
    recency={7:100,14:90,30:80}.get(row["window_days"],50)
    return round(.30*volume+.20*row["phone_percent"]+.20*row["clear_percent"]+.15*relevance+.10*geography+.05*recency,2)


def _price(count):
    if count < 15: return 5
    if count <= 40: return 15
    return 29


def build_inventory(engine, data_dir: Path, docs_dir: Path, *, generate_packs: bool = True) -> dict:
    processed=data_dir/"processed"; exports=data_dir/"exports"; processed.mkdir(parents=True,exist_ok=True); exports.mkdir(parents=True,exist_ok=True)
    with engine.begin() as connection:
        for code,description in CLASSIFICATION_DESCRIPTIONS.items():
            connection.execute(update(classifications).where(classifications.c.code==code).values(description=description))
    with engine.connect() as connection:
        anchor=latest_data_date(connection)
        latest=connection.execute(select(source_imports).where(source_imports.c.status=="complete").order_by(source_imports.c.id.desc()).limit(1)).mappings().one()
        cb=select(bonds.c.license_number).where(bonds.c.bond_type=="contractor",bonds.c.surety_company.is_not(None)).distinct().subquery()
        stmt=select(licenses.c.license_number,licenses.c.original_issue_date,licenses.c.primary_status,contractors.c.business_name,contractors.c.phone_normalized,contractors.c.phone_raw,contractors.c.mailing_address,contractors.c.city,contractors.c.county,contractors.c.state,contractors.c.zip_code,contractor_classifications.c.classification_code,classifications.c.description,workers_comp.c.coverage_type,workers_comp.c.carrier,workers_comp.c.expiration_date.label("wc_expiration"),(cb.c.license_number.is_not(None)).label("has_bond")).join(contractors,contractors.c.id==licenses.c.contractor_id).join(contractor_classifications,contractor_classifications.c.license_number==licenses.c.license_number).outerjoin(classifications,classifications.c.code==contractor_classifications.c.classification_code).outerjoin(workers_comp,workers_comp.c.license_number==licenses.c.license_number).outerjoin(cb,cb.c.license_number==licenses.c.license_number).where(licenses.c.original_issue_date.between(anchor-timedelta(days=89),anchor))
        records=[dict(row) for row in connection.execute(stmt).mappings()]
    aggregates=defaultdict(lambda:Counter())
    descriptions={}
    for record in records:
        code=record["classification_code"]; descriptions[code]=record["description"]
        geographies=[("statewide","California")]
        if record["county"]: geographies.append(("county",record["county"]))
        if record["county"] in SOUTHERN_CALIFORNIA_COUNTIES: geographies.append(("region","Southern California"))
        age=(anchor-record["original_issue_date"]).days
        for days in WINDOWS:
            if age>=days: continue
            for geo_type,geo_name in geographies:
                bucket=aggregates[(code,geo_type,geo_name,days)]; bucket["total"]+=1
                bucket["clear"]+=record["primary_status"]=="CLEAR"; bucket["phone"]+=bool(record["phone_normalized"]); bucket["county"]+=bool(record["county"])
                bucket["wc_insurance"]+=record["coverage_type"]=="Workers' Compensation Insurance"; bucket["wc_exempt"]+=record["coverage_type"]=="Exempt"; bucket["bond"]+=bool(record["has_bond"])
    rows=[]
    for (code,geo_type,geo_name,days),c in aggregates.items():
        row={"classification_code":code,"classification_description":descriptions.get(code) or "","geography_type":geo_type,"geography_name":geo_name,"window_days":days,"total_newly_issued":c["total"],"clear_count":c["clear"],"clear_percent":_pct(c["clear"],c["total"]),"phone_count":c["phone"],"phone_percent":_pct(c["phone"],c["total"]),"county_count":c["county"],"workers_comp_insurance_count":c["wc_insurance"],"workers_comp_exempt_count":c["wc_exempt"],"bond_information_count":c["bond"]}
        row["candidate_score"]=_score(row) if days in (7,14,30) else ""; rows.append(row)
    rows.sort(key=lambda r:(r["classification_code"],r["geography_type"],r["geography_name"],r["window_days"]))
    matrix=processed/"inventory_matrix.csv"
    with matrix.open("w",newline="",encoding="utf-8") as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    candidates=[r for r in rows if r["window_days"] in (7,14,30) and r["total_newly_issued"]>=10 and r["classification_code"] in CORE_TRADES]
    candidates.sort(key=lambda r:(r["candidate_score"],r["total_newly_issued"]),reverse=True)
    # Avoid near-duplicate windows/geographies for the initial five.
    top=[]; used=set()
    for row in candidates:
        key=(row["classification_code"],row["geography_name"])
        if key in used: continue
        top.append(row); used.add(key)
        if len(top)==5: break
    products=[]
    with engine.connect() as connection:
        for rank,row in enumerate(top,1):
            code=row["classification_code"]; geo=row["geography_name"]; days=row["window_days"]
            kwargs={"classification":code,"days":days,"anchor_date":anchor,"dialect_name":engine.dialect.name}
            if row["geography_type"]=="county": kwargs["county"]=geo
            statement=lead_query(**kwargs)
            if row["geography_type"]=="region": statement=statement.where(contractors.c.county.in_(SOUTHERN_CALIFORNIA_COUNTIES))
            leads=[dict(item) for item in connection.execute(statement).mappings()]
            description=row["classification_description"] or code; price=_price(len(leads)); slug=re.sub(r"[^a-z0-9]+","_",f"{rank}_{code}_{geo}_{days}d".lower()).strip("_")
            path=exports/f"candidate_{slug}.xlsx"
            if generate_packs: export_xlsx(leads,list(leads[0]) if leads else [c.key for c in statement.selected_columns],path,{"generated_at":datetime.now(timezone.utc).isoformat(),"source_as_of":str(anchor),"source_sha256":latest["sha256"]})
            products.append({"rank":rank,"report_name":f"New {description}s — {geo}, Last {days} Days","audience":"Commercial insurance and surety professionals serving contractors","classification":code,"geography":geo,"geography_type":row["geography_type"],"window_days":days,"lead_count":len(leads),"score":row["candidate_score"],"suggested_price":price,"ad_proposition":f"Reach {len(leads)} newly licensed {description.lower()} businesses in {geo} before established lead lists catch up.","report_path":str(path) if generate_packs else None})
    candidates_path=processed/"commercial_candidates.json"; candidates_path.write_text(json.dumps(products,indent=2)+"\n",encoding="utf-8")
    quality=quality_audit(engine,anchor); quality_path=processed/"commercial_quality_audit.json"; quality_path.write_text(json.dumps(quality,indent=2,default=str)+"\n",encoding="utf-8")
    docs_dir.mkdir(parents=True,exist_ok=True); analysis=docs_dir/"inventory-analysis.md"
    state30=sorted([r for r in rows if r["geography_type"]=="statewide" and r["window_days"]==30],key=lambda r:r["total_newly_issued"],reverse=True)[:15]
    recent30={record["license_number"]:record for record in records if (anchor-record["original_issue_date"]).days<30}
    county30=Counter(record["county"] or "(missing)" for record in recent30.values())
    lines=["# FreshTradeLeads inventory analysis","",f"Source anchor: **{anchor}**. Windows contain exactly N calendar dates ending on the anchor.","",f"Southern California is defined only as: {', '.join(SOUTHERN_CALIFORNIA_COUNTIES)}.","","## Candidate score","","Score = 30% lead-count fit (favoring 20–75) + 20% phone completeness + 20% CLEAR status + 15% trade relevance to insurance/surety + 10% geography clarity + 5% recency. It is a transparent ranking heuristic, not an ML model.","","## Highest-volume statewide classifications, 30 days","","| Code | Description | Leads | CLEAR | Phone |","|---|---|---:|---:|---:|"]
    for r in state30: lines.append(f"| {r['classification_code']} | {r['classification_description'] or 'Unmapped'} | {r['total_newly_issued']} | {r['clear_percent']}% | {r['phone_percent']}% |")
    lines.extend(["","## Highest-volume counties, all trades, 30 days","","| County | Newly issued licenses |","|---|---:|"])
    for county,count in county30.most_common(15): lines.append(f"| {county} | {count} |")
    lines.extend(["","## Recommended initial products",""])
    for p in products: lines.extend([f"### {p['rank']}. {p['report_name']}","",f"- Leads: {p['lead_count']}; score: {p['score']}; suggested price: ${p['suggested_price']}",f"- Audience: {p['audience']}",f"- Ad hook: {p['ad_proposition']}",f"- Sample: `{p['report_path']}`",""])
    lines.extend(["## Data fitness","",f"Recent 30-day records are classified as clean ({quality['fitness'].get('clean',0)}), usable with caveat ({quality['fitness'].get('usable_with_caveat',0)}), or questionable ({quality['fitness'].get('questionable',0)}).", "", "| Field | Complete | Percent |", "|---|---:|---:|"])
    for field,metric in quality["completeness"].items(): lines.append(f"| {field.replace('_',' ').title()} | {metric['count']} | {metric['percent']}% |")
    lines.extend(["","Structural anomaly counts are retained in `data/processed/commercial_quality_audit.json`; questionable source values are not guessed or rewritten.","","Policy numbers, disciplinary case identifiers/reasons, and person-level names should not be sold in the MVP. Workers-comp carrier should be displayed only when the coverage type is actual insurance; its overall missing rate mostly reflects exempt or no-current-coverage records rather than corruption."])
    analysis.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return {"source_anchor":str(anchor),"matrix_path":str(matrix),"matrix_rows":len(rows),"candidates_path":str(candidates_path),"quality_path":str(quality_path),"analysis_path":str(analysis),"products":products}


def quality_audit(engine, anchor):
    with engine.connect() as connection:
        cb=select(bonds.c.license_number,bonds.c.surety_company,bonds.c.amount).where(bonds.c.bond_type=="contractor").subquery()
        cls=select(contractor_classifications.c.license_number,func.count().label("class_count")).group_by(contractor_classifications.c.license_number).subquery()
        q=select(licenses.c.license_number,licenses.c.original_issue_date,licenses.c.primary_status,contractors.c.business_name,contractors.c.phone_raw,contractors.c.phone_normalized,contractors.c.mailing_address,contractors.c.city,contractors.c.county,contractors.c.zip_code,workers_comp.c.coverage_type,workers_comp.c.carrier,workers_comp.c.expiration_date.label("wc_expiration"),cb.c.surety_company,cb.c.amount,cls.c.class_count).join(contractors,contractors.c.id==licenses.c.contractor_id).outerjoin(workers_comp,workers_comp.c.license_number==licenses.c.license_number).outerjoin(cb,cb.c.license_number==licenses.c.license_number).outerjoin(cls,cls.c.license_number==licenses.c.license_number).where(licenses.c.original_issue_date.between(anchor-timedelta(days=29),anchor))
        records=[dict(r) for r in connection.execute(q).mappings()]
    fields={name:0 for name in ["business_name","phone","address","city","county","zip","classification","issue_date","status","workers_comp_type","workers_comp_carrier","bond_surety","bond_amount"]}
    anomalies=defaultdict(list); names=Counter(re.sub(r"[^A-Z0-9]","",(r["business_name"] or "").upper()) for r in records)
    fitness=Counter()
    for r in records:
        checks={"business_name":r["business_name"],"phone":r["phone_normalized"],"address":r["mailing_address"],"city":r["city"],"county":r["county"],"zip":r["zip_code"],"classification":r["class_count"],"issue_date":r["original_issue_date"],"status":r["primary_status"],"workers_comp_type":r["coverage_type"],"workers_comp_carrier":r["carrier"],"bond_surety":r["surety_company"],"bond_amount":r["amount"]}
        for key,value in checks.items(): fields[key]+=bool(value)
        reasons=[]; phone=r["phone_normalized"] or ""; zipcode=re.sub(r"\D","",r["zip_code"] or "")
        if phone and (len(phone)!=10 or len(set(phone))<=2 or phone in {"1234567890","0000000000","9999999999"}): reasons.append("malformed_or_placeholder_phone"); anomalies["phones"].append({"license":r["license_number"],"value":r["phone_raw"]})
        if zipcode and len(zipcode) not in {5,9}: reasons.append("weird_zip"); anomalies["zips"].append({"license":r["license_number"],"value":r["zip_code"]})
        caveats=[]
        if not phone: caveats.append("missing_phone")
        if not r["county"]: caveats.append("missing_county")
        if re.search(r"\bP\.?\s*O\.?\s+BOX\b",r["mailing_address"] or "",re.I): caveats.append("po_box"); anomalies["po_boxes"].append({"license":r["license_number"],"address":r["mailing_address"]})
        normalized=re.sub(r"[^A-Z0-9]","",(r["business_name"] or "").upper())
        if normalized and names[normalized]>1: caveats.append("duplicate_business_name"); anomalies["duplicate_business_names"].append({"license":r["license_number"],"business_name":r["business_name"]})
        if r["wc_expiration"] and r["wc_expiration"]>anchor+timedelta(days=3650): reasons.append("extreme_wc_date"); anomalies["extreme_dates"].append({"license":r["license_number"],"wc_expiration":str(r["wc_expiration"])})
        if r["amount"] is not None and (r["amount"]<=0 or r["amount"]>1_000_000): reasons.append("suspicious_bond_amount"); anomalies["bond_amounts"].append({"license":r["license_number"],"amount":str(r["amount"])})
        fitness["questionable" if reasons else ("usable_with_caveat" if caveats else "clean")]+=1
    total=len(records)
    return {"source_anchor":str(anchor),"window_days":30,"records":total,"completeness":{key:{"count":value,"percent":_pct(value,total)} for key,value in fields.items()},"fitness":dict(fitness),"anomaly_counts":{key:len(value) for key,value in anomalies.items()},"anomaly_examples":{key:value[:20] for key,value in anomalies.items()},"notes":["Questionable means a structural anomaly, not a claim that CSLB data is false.","Usable-with-caveat includes missing county/phone, PO boxes, or repeated business names.","No questionable government value is automatically corrected."]}
