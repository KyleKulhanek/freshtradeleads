from datetime import date, datetime, timezone
from sqlalchemy import insert
from freshtradeleads.campaign_report import ReportSettings, build_report, render_text
from freshtradeleads.schema import funnel_events, orders, source_imports


def _settings(tmp_path):
    return ReportSettings("sqlite://", "owner@example.com", "America/Los_Angeles", date(2026, 9, 4), tmp_path, None, None, None, "v22.0", None, None, None)


def test_report_counts_first_party_funnel(engine, tmp_path):
    occurred = datetime(2026, 9, 5, 3, tzinfo=timezone.utc)
    with engine.begin() as conn:
        conn.execute(insert(funnel_events), [{"id": "e1", "event_type": "landing_viewed", "metadata": {}, "occurred_at": occurred}, {"id": "e2", "event_type": "sample_downloaded", "metadata": {}, "occurred_at": occurred}])
    report = build_report(engine, _settings(tmp_path), date(2026, 9, 4))
    assert report["first_party"]["today"]["events"]["landing_viewed"] == 1
    assert report["first_party"]["campaign"]["events"]["sample_downloaded"] == 1
    assert report["meta"]["campaign"]["available"] is False
    assert "Meta Marketing API token is not configured" in render_text(report)


def test_report_uses_verified_orders_for_revenue(engine, tmp_path):
    paid = datetime(2026, 9, 5, 3, tzinfo=timezone.utc)
    with engine.begin() as conn:
        result = conn.execute(insert(source_imports).values(source_file="fixture.xlsx", sha256="a" * 64, file_size=1, status="completed"))
        snapshot_id = result.inserted_primary_key[0]
        conn.execute(insert(orders).values(id="order-1", sku="fresh-pack", status="fulfilled", price_cents=2900, final_price_cents=2320, discount_cents=580, currency="usd", source_import_id=snapshot_id, source_data_date=date(2026, 9, 3), filter_definition={}, pinned_lead_count=45, utm_attribution={}, paid_at=paid))
    report = build_report(engine, _settings(tmp_path), date(2026, 9, 4))
    values = report["first_party"]["campaign"]
    assert values["paid_orders"] == 1
    assert values["net_revenue_cents"] == 2320
    rendered = render_text(report)
    assert "Verified payment transactions: 1 today / 1 campaign" in rendered
    assert "Gross revenue: $23.20 today / $23.20 campaign" in rendered
    assert "Refunds: $0.00 today / $0.00 campaign" in rendered
