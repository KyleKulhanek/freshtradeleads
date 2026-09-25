from __future__ import annotations

import argparse
import base64
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from .config import database_url
from .db import get_engine
from .schema import funnel_events, orders


FUNNEL_TYPES = ("landing_viewed", "sample_downloaded", "checkout_started", "payment_completed", "paid_report_downloaded")


@dataclass(frozen=True)
class ReportSettings:
    database_url: str
    recipient: str
    timezone_name: str
    campaign_start: date
    output_dir: Path
    meta_access_token: str | None
    meta_ad_account_id: str | None
    meta_campaign_id: str | None
    meta_api_version: str
    google_client_id: str | None
    google_client_secret: str | None
    google_refresh_token: str | None


def settings_from_env() -> ReportSettings:
    return ReportSettings(
        database_url=database_url(),
        recipient=os.getenv("FTL_REPORT_RECIPIENT", "owner@example.com"),
        timezone_name=os.getenv("FTL_REPORT_TIMEZONE", "America/Los_Angeles"),
        campaign_start=date.fromisoformat(os.getenv("FTL_REPORT_CAMPAIGN_START", "2026-01-01")),
        output_dir=Path(os.getenv("FTL_REPORT_OUTPUT_DIR", "/opt/freshtradeleads/data/processed/campaign-reports")),
        meta_access_token=os.getenv("META_MARKETING_ACCESS_TOKEN") or None,
        meta_ad_account_id=os.getenv("META_AD_ACCOUNT_ID") or None,
        meta_campaign_id=os.getenv("META_CAMPAIGN_ID") or None,
        meta_api_version=os.getenv("META_GRAPH_API_VERSION", "v22.0"),
        google_client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID") or None,
        google_client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or None,
        google_refresh_token=os.getenv("GOOGLE_OAUTH_REFRESH_TOKEN") or None,
    )


def _window(day: date, tz_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(tz_name)
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day, time.max, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def first_party_metrics(engine, report_day: date, campaign_start: date, tz_name: str) -> dict:
    day_start, day_end = _window(report_day, tz_name)
    campaign_start_utc, _ = _window(campaign_start, tz_name)

    def collect(conn, start: datetime, end: datetime) -> dict:
        rows = conn.execute(
            select(funnel_events.c.event_type, func.count())
            .where(funnel_events.c.occurred_at >= start, funnel_events.c.occurred_at <= end)
            .group_by(funnel_events.c.event_type)
        ).all()
        event_counts = {name: 0 for name in FUNNEL_TYPES}
        event_counts.update({name: int(count) for name, count in rows})
        order_row = conn.execute(
            select(
                func.count().filter(orders.c.status.in_(["fulfilled", "partially_refunded", "refunded"])),
                func.coalesce(func.sum(orders.c.final_price_cents).filter(orders.c.status.in_(["fulfilled", "partially_refunded", "refunded"])), 0),
                func.coalesce(func.sum(orders.c.refund_amount_cents).filter(orders.c.status.in_(["partially_refunded", "refunded"])), 0),
            ).where(orders.c.paid_at >= start, orders.c.paid_at <= end)
        ).one()
        return {
            "events": event_counts,
            "paid_orders": int(order_row[0] or 0),
            "gross_revenue_cents": int(order_row[1] or 0),
            "refunds_cents": int(order_row[2] or 0),
            "net_revenue_cents": int(order_row[1] or 0) - int(order_row[2] or 0),
        }

    with engine.connect() as conn:
        return {"today": collect(conn, day_start, day_end), "campaign": collect(conn, campaign_start_utc, day_end)}


def _action_value(row: dict, action_type: str) -> int:
    for item in row.get("actions", []) or []:
        if item.get("action_type") == action_type:
            return int(float(item.get("value", 0)))
    return 0


def fetch_meta_metrics(settings: ReportSettings, since: date, until: date) -> dict:
    if not all((settings.meta_access_token, settings.meta_ad_account_id, settings.meta_campaign_id)):
        return {"available": False, "error": "Meta Marketing API token is not configured", "ads": []}
    params = {
        "access_token": settings.meta_access_token,
        "fields": "campaign_name,ad_id,ad_name,spend,impressions,reach,frequency,cpm,inline_link_clicks,ctr,cpc,actions",
        "level": "ad",
        "time_range": json.dumps({"since": since.isoformat(), "until": until.isoformat()}),
        "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": [settings.meta_campaign_id]}]),
        "limit": "100",
    }
    account = settings.meta_ad_account_id.removeprefix("act_")
    url = f"https://graph.facebook.com/{settings.meta_api_version}/act_{account}/insights?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError) as exc:
        detail = getattr(exc, "reason", None) or str(exc)
        return {"available": False, "error": f"Meta Insights request failed: {detail}", "ads": []}
    ads = [{
        "ad_id": row.get("ad_id"), "ad_name": row.get("ad_name", "Unknown ad"),
        "spend": float(row.get("spend", 0)), "impressions": int(row.get("impressions", 0)),
        "reach": int(row.get("reach", 0)), "frequency": float(row.get("frequency", 0)),
        "cpm": float(row.get("cpm", 0)), "link_clicks": int(row.get("inline_link_clicks", 0)),
        "ctr": float(row.get("ctr", 0)), "cpc": float(row.get("cpc", 0)),
        "meta_purchases": _action_value(row, "purchase"),
    } for row in payload.get("data", [])]
    return {"available": True, "error": None, "ads": ads}


def _totals(ads: list[dict]) -> dict:
    spend = sum(x["spend"] for x in ads); impressions = sum(x["impressions"] for x in ads)
    reach = sum(x["reach"] for x in ads); clicks = sum(x["link_clicks"] for x in ads)
    return {"spend": spend, "impressions": impressions, "reach": reach, "link_clicks": clicks,
            "ctr": clicks / impressions * 100 if impressions else 0, "cpc": spend / clicks if clicks else 0,
            "meta_purchases": sum(x["meta_purchases"] for x in ads)}


def build_report(engine, settings: ReportSettings, report_day: date) -> dict:
    first_party = first_party_metrics(engine, report_day, settings.campaign_start, settings.timezone_name)
    meta_today = fetch_meta_metrics(settings, report_day, report_day)
    meta_campaign = fetch_meta_metrics(settings, settings.campaign_start, report_day)
    for section in (meta_today, meta_campaign):
        section["totals"] = _totals(section["ads"]) if section["available"] else {}
    campaign = first_party["campaign"]; spend = meta_campaign.get("totals", {}).get("spend")
    campaign["cac"] = spend / campaign["paid_orders"] if spend is not None and campaign["paid_orders"] else None
    campaign["roas"] = (campaign["net_revenue_cents"] / 100) / spend if spend else None
    return {"report_day": report_day.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
            "campaign_start": settings.campaign_start.isoformat(), "first_party": first_party,
            "meta": {"today": meta_today, "campaign": meta_campaign}}


def _money(cents: int) -> str:
    return f"${cents / 100:,.2f}"


def render_text(report: dict) -> str:
    day = report["first_party"]["today"]; campaign = report["first_party"]["campaign"]
    meta_day = report["meta"]["today"]; meta_campaign = report["meta"]["campaign"]
    lines = [f"FreshTradeLeads nightly campaign report — {report['report_day']}", "",
             "FIRST-PARTY FUNNEL (authoritative)",
             f"Landing views: {day['events']['landing_viewed']} today / {campaign['events']['landing_viewed']} campaign",
             f"Sample downloads: {day['events']['sample_downloaded']} today / {campaign['events']['sample_downloaded']} campaign",
             f"Checkout starts: {day['events']['checkout_started']} today / {campaign['events']['checkout_started']} campaign",
             f"Verified payment transactions: {day['paid_orders']} today / {campaign['paid_orders']} campaign",
             f"Paid report downloads: {day['events']['paid_report_downloaded']} today / {campaign['events']['paid_report_downloaded']} campaign",
             f"Gross revenue: {_money(day['gross_revenue_cents'])} today / {_money(campaign['gross_revenue_cents'])} campaign",
             f"Refunds: {_money(day['refunds_cents'])} today / {_money(campaign['refunds_cents'])} campaign",
             f"Net revenue: {_money(day['net_revenue_cents'])} today / {_money(campaign['net_revenue_cents'])} campaign", "", "META DELIVERY"]
    if not meta_campaign["available"]:
        lines.append(f"Unavailable: {meta_campaign['error']}")
    else:
        today = meta_day["totals"]; total = meta_campaign["totals"]
        lines += [f"Spend: ${today['spend']:.2f} today / ${total['spend']:.2f} campaign",
                  f"Impressions: {today['impressions']:,} today / {total['impressions']:,} campaign",
                  f"Reach: {today['reach']:,} today / {total['reach']:,} campaign",
                  f"Link clicks: {today['link_clicks']:,} today / {total['link_clicks']:,} campaign",
                  f"CTR: {total['ctr']:.2f}% campaign | CPC: ${total['cpc']:.2f}", "", "BY AD"]
        lines += [f"{ad['ad_name']}: ${ad['spend']:.2f} spent, {ad['impressions']:,} impressions, {ad['link_clicks']} clicks, {ad['ctr']:.2f}% CTR" for ad in meta_campaign["ads"]]
    lines += ["", "DERIVED",
              f"Customer acquisition cost: ${campaign['cac']:.2f}" if campaign["cac"] is not None else "Customer acquisition cost: not available yet",
              f"Return on ad spend: {campaign['roas']:.2f}x" if campaign["roas"] is not None else "Return on ad spend: not available yet"]
    if meta_campaign["available"] and meta_campaign["totals"]["meta_purchases"] != campaign["paid_orders"]:
        lines.append(f"Attribution note: Meta reports {meta_campaign['totals']['meta_purchases']} purchase(s); FreshTradeLeads verified {campaign['paid_orders']}.")
    return "\n".join(lines) + "\n"


def render_html(report: dict) -> str:
    return "<html><body style='font-family:system-ui;color:#102a32'><pre style='white-space:pre-wrap'>" + html.escape(render_text(report)) + "</pre></body></html>"


def _google_access_token(settings: ReportSettings) -> str:
    if not all((settings.google_client_id, settings.google_client_secret, settings.google_refresh_token)):
        raise RuntimeError("Google OAuth mail credentials are not configured")
    body = urllib.parse.urlencode({"client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                                   "refresh_token": settings.google_refresh_token, "grant_type": "refresh_token"}).encode()
    request = urllib.request.Request("https://oauth2.googleapis.com/token", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["access_token"]


def send_report(settings: ReportSettings, report: dict) -> str:
    message = EmailMessage(); message["To"] = settings.recipient
    message["Subject"] = f"FreshTradeLeads nightly report — {report['report_day']}"
    message.set_content(render_text(report)); message.add_alternative(render_html(report), subtype="html")
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")
    request = urllib.request.Request("https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        data=json.dumps({"raw": raw}).encode(), headers={"Authorization": f"Bearer {_google_access_token(settings)}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["id"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate and email the nightly FreshTradeLeads campaign report")
    parser.add_argument("--date", type=date.fromisoformat); parser.add_argument("--no-email", action="store_true")
    args = parser.parse_args(argv); settings = settings_from_env()
    report_day = args.date or datetime.now(ZoneInfo(settings.timezone_name)).date()
    report = build_report(get_engine(settings.database_url), settings, report_day)
    settings.output_dir.mkdir(parents=True, exist_ok=True); output = settings.output_dir / f"{report_day.isoformat()}.json"
    temporary = output.with_suffix(".json.tmp"); temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"); temporary.replace(output)
    print(render_text(report), end="")
    if not args.no_email:
        print(f"Email sent: {send_report(settings, report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
