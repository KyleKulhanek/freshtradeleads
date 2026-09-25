from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import insert, select, update

from .exporter import export_csv, export_xlsx
from .products import REPORT_COLUMNS, inventory, report_rows
from .schema import download_tokens, funnel_events, order_leads, orders, products, source_imports, stripe_events


class UnknownProductError(ValueError):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def track_event(conn, event_type: str, *, visitor_id: str | None = None, order_id: str | None = None, utm: dict | None = None, metadata: dict | None = None):
    utm=utm or {}
    conn.execute(insert(funnel_events).values(id=str(uuid.uuid4()),event_type=event_type,visitor_id=visitor_id,order_id=order_id,utm_source=utm.get("utm_source"),utm_medium=utm.get("utm_medium"),utm_campaign=utm.get("utm_campaign"),utm_content=utm.get("utm_content"),utm_term=utm.get("utm_term"),metadata=metadata or {}))


def _discount(price: int, percent: int) -> int:
    return (price * percent + 50) // 100


def create_order(engine, sku: str, *, utm: dict, visitor_id: str | None, base_url: str, gateway, promotion_code: str | None = None, promotion_id: str | None = None, promotion_percent: int = 20):
    order_id=str(uuid.uuid4()); token=secrets.token_urlsafe(32)
    with engine.begin() as conn:
        snapshot, items=inventory(conn)
        product=next((x for x in items if x["sku"] == sku), None)
        if not product: raise UnknownProductError(sku)
        ids=product["lead_ids"]
        if not ids: raise RuntimeError("This product currently has no qualifying leads")
        filters={"classification":"C10","counties":product["counties"],"window_days":product["window_days"],"lead_limit":product["lead_limit"],"anchor_date":snapshot["newest_issue_date"].isoformat()}
        discount=_discount(product["price_cents"],promotion_percent) if promotion_id else 0
        final=product["price_cents"]-discount
        conn.execute(insert(orders).values(id=order_id,sku=sku,status="created",price_cents=product["price_cents"],final_price_cents=final,discount_cents=discount,promotion_code=promotion_code if promotion_id else None,stripe_promotion_code_id=promotion_id, currency=product["currency"],source_import_id=snapshot["id"],source_data_date=snapshot["newest_issue_date"],filter_definition=filters,pinned_lead_count=len(ids),utm_attribution=utm))
        conn.execute(insert(order_leads), [{"order_id":order_id,"license_number":lid,"position":i} for i,lid in enumerate(ids,1)])
        conn.execute(insert(download_tokens).values(token_hash=token_hash(token),order_id=order_id))
    success=f"{base_url}/order/{order_id}/success?session_id={{CHECKOUT_SESSION_ID}}&token={quote(token)}"
    cancel=f"{base_url}/?checkout=cancelled"
    try:
        checkout=gateway.create_checkout(order_id=order_id,sku=sku,name=product["name"],description=f"{len(ids)} pinned leads · source data through {snapshot['newest_issue_date'].isoformat()}",amount=product["price_cents"],currency=product["currency"],success_url=success,cancel_url=cancel,promotion_id=promotion_id,allow_promotion_codes=not bool(promotion_id))
    except Exception:
        with engine.begin() as conn: conn.execute(update(orders).where(orders.c.id==order_id).values(status="failed",updated_at=datetime.now(timezone.utc)))
        raise
    with engine.begin() as conn:
        conn.execute(update(orders).where(orders.c.id==order_id).values(status="checkout_pending",stripe_checkout_session_id=checkout.id,checkout_started_at=datetime.now(timezone.utc),updated_at=datetime.now(timezone.utc)))
        track_event(conn,"checkout_started",visitor_id=visitor_id,order_id=order_id,utm=utm,metadata={"sku":sku,"original_price_cents":product["price_cents"],"expected_price_cents":final,"promotion_code":promotion_code if promotion_id else None,"lead_count":len(ids)})
    return order_id, token, checkout


def _event_data(event):
    if hasattr(event, "to_dict_recursive"): event=event.to_dict_recursive()
    return event if isinstance(event, dict) else dict(event)


def fulfill_verified_event(engine, event, *, data_dir: Path, download_days: int = 7, approved_promotion_id: str | None = None, approved_promotion_code: str | None = None) -> dict:
    event=_event_data(event); eid=event["id"]; etype=event["type"]
    obj=event.get("data",{}).get("object",{}); metadata=obj.get("metadata",{}) or {}; order_id=metadata.get("order_id")
    with engine.begin() as conn:
        prior=conn.execute(select(stripe_events).where(stripe_events.c.event_id==eid)).mappings().first()
        if prior and prior["status"] in {"processed","ignored"}: return {"duplicate":True,"status":prior["status"],"order_id":prior["order_id"]}
        if not prior: conn.execute(insert(stripe_events).values(event_id=eid,event_type=etype,order_id=order_id,status="received"))
    if etype in {"checkout.session.expired","checkout.session.async_payment_failed"}:
        now=datetime.now(timezone.utc)
        with engine.begin() as conn:
            if order_id: conn.execute(update(orders).where(orders.c.id==order_id,orders.c.status.in_(["created","checkout_pending"])).values(status="cancelled" if etype.endswith("expired") else "failed",updated_at=now))
            conn.execute(update(stripe_events).where(stripe_events.c.event_id==eid).values(status="processed",processed_at=now))
        return {"status":"processed","order_id":order_id}
    if etype == "charge.refunded":
        payment_intent=obj.get("payment_intent")
        if not payment_intent: raise ValueError("Refund event is missing its Payment Intent")
        with engine.connect() as conn:
            order=conn.execute(select(orders).where(orders.c.stripe_payment_intent_id==payment_intent)).mappings().first()
        if not order: raise ValueError("Refund event references an unknown Payment Intent")
        refunded=int(obj.get("amount_refunded",0) or 0); charged=int(obj.get("amount",0) or 0)
        if refunded < 0 or charged <= 0 or refunded > charged: raise ValueError("Refund event has invalid amounts")
        full=refunded >= charged; now=datetime.now(timezone.utc)
        with engine.begin() as conn:
            conn.execute(update(orders).where(orders.c.id==order["id"]).values(status="refunded" if full else "partially_refunded",refunded_at=now,refund_amount_cents=refunded,updated_at=now))
            if full: conn.execute(update(download_tokens).where(download_tokens.c.order_id==order["id"]).values(expires_at=now))
            conn.execute(update(stripe_events).where(stripe_events.c.event_id==eid).values(order_id=order["id"],status="processed",processed_at=now))
            track_event(conn,"payment_refunded",order_id=order["id"],utm=order["utm_attribution"],metadata={"sku":order["sku"],"refund_amount_cents":refunded,"full_refund":full})
        return {"status":"refunded" if full else "partially_refunded","order_id":order["id"],"refund_amount_cents":refunded}
    if etype not in {"checkout.session.completed","checkout.session.async_payment_succeeded"}:
        with engine.begin() as conn: conn.execute(update(stripe_events).where(stripe_events.c.event_id==eid).values(status="ignored",processed_at=datetime.now(timezone.utc)))
        return {"ignored":True}
    with engine.connect() as conn: order=conn.execute(select(orders).where(orders.c.id==order_id)).mappings().first()
    if not order: raise ValueError("Stripe event references an unknown order")
    paid=obj.get("payment_status") == "paid"
    if not paid:
        now=datetime.now(timezone.utc)
        with engine.begin() as conn: conn.execute(update(stripe_events).where(stripe_events.c.event_id==eid).values(status="processed",processed_at=now,error_message="Checkout completed but payment remains pending"))
        return {"status":"payment_pending","order_id":order_id}
    amount_total=int(obj.get("amount_total",-1)); amount_discount=int((obj.get("total_details") or {}).get("amount_discount",0) or 0)
    applied_promotions=[d.get("promotion_code") for d in (obj.get("discounts") or []) if isinstance(d,dict) and d.get("promotion_code")]
    if amount_discount not in {0, _discount(order["price_cents"],20)}:
        raise ValueError("Stripe Checkout Session contains an unapproved discount")
    if amount_discount and (not approved_promotion_id or applied_promotions != [approved_promotion_id]):
        raise ValueError("Stripe Checkout Session contains an unapproved promotion code")
    if order["stripe_promotion_code_id"] and amount_discount != order["discount_cents"]:
        raise ValueError("Stripe Checkout Session does not contain the pinned promotion")
    expected=order["price_cents"]-amount_discount
    if obj.get("id") != order["stripe_checkout_session_id"] or amount_total != expected or obj.get("currency") != order["currency"]:
        raise ValueError("Stripe Checkout Session does not match the pinned order")
    with engine.connect() as conn:
        ids=list(conn.execute(select(order_leads.c.license_number).where(order_leads.c.order_id==order_id).order_by(order_leads.c.position)).scalars())
        snapshot=conn.execute(select(source_imports).where(source_imports.c.id==order["source_import_id"])).mappings().one()
        rows=report_rows(conn,ids,import_id=order["source_import_id"])
    if len(rows) != order["pinned_lead_count"]: raise RuntimeError("Pinned report row count mismatch")
    out=Path(data_dir)/"web"/"orders"/order_id; out.mkdir(parents=True,exist_ok=True)
    meta={"generated_at":datetime.now(timezone.utc).isoformat(),"source_as_of":order["source_data_date"].isoformat(),"source_sha256":snapshot["sha256"]}
    export_xlsx(rows,REPORT_COLUMNS,out/"report.xlsx",meta); export_csv(rows,REPORT_COLUMNS,out/"report.csv",meta)
    now=datetime.now(timezone.utc)
    with engine.begin() as conn:
        customer_email=(obj.get("customer_details") or {}).get("email") or obj.get("customer_email")
        conn.execute(update(orders).where(orders.c.id==order_id).values(status="fulfilled",final_price_cents=amount_total,discount_cents=amount_discount,promotion_code=order["promotion_code"] or (approved_promotion_code if amount_discount else None),stripe_promotion_code_id=order["stripe_promotion_code_id"] or (approved_promotion_id if amount_discount else None),stripe_payment_intent_id=obj.get("payment_intent"),customer_email=customer_email,paid_at=order["paid_at"] or now,fulfilled_at=order["fulfilled_at"] or now,updated_at=now))
        conn.execute(update(download_tokens).where(download_tokens.c.order_id==order_id).values(expires_at=now+timedelta(days=download_days)))
        conn.execute(update(stripe_events).where(stripe_events.c.event_id==eid).values(status="processed",processed_at=now))
        track_event(conn,"payment_completed",order_id=order_id,utm=order["utm_attribution"],metadata={"sku":order["sku"],"original_price_cents":order["price_cents"],"final_price_cents":amount_total,"discount_cents":amount_discount})
    return {"duplicate":False,"status":"fulfilled","order_id":order_id}


def order_status(engine, order_id: str):
    with engine.connect() as conn: return conn.execute(select(orders).where(orders.c.id==order_id)).mappings().first()


def authorize_download(engine, token: str, fmt: str, *, data_dir: Path):
    if fmt not in {"xlsx","csv"}: return None
    now=datetime.now(timezone.utc)
    with engine.begin() as conn:
        row=conn.execute(select(download_tokens,orders.c.status,orders.c.sku,orders.c.pinned_lead_count).join(orders,orders.c.id==download_tokens.c.order_id).where(download_tokens.c.token_hash==token_hash(token))).mappings().first()
        if not row or row["status"] not in {"fulfilled", "partially_refunded"} or not row["expires_at"]: return None
        expires=row["expires_at"]
        if expires.tzinfo is None: expires=expires.replace(tzinfo=timezone.utc)
        if expires <= now: return None
        conn.execute(update(download_tokens).where(download_tokens.c.token_hash==token_hash(token)).values(download_count=download_tokens.c.download_count+1,last_downloaded_at=now))
        track_event(conn,"paid_report_downloaded",order_id=row["order_id"],metadata={"format":fmt,"sku":row["sku"]})
        return Path(data_dir)/"web"/"orders"/row["order_id"]/f"report.{fmt}"
