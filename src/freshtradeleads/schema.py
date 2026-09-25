from __future__ import annotations

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index,
    Integer, MetaData, Numeric, String, Table, Text, UniqueConstraint, func,
)

metadata = MetaData()
ID_TYPE = BigInteger().with_variant(Integer, "sqlite")

source_imports = Table(
    "source_imports", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("source_file", Text, nullable=False),
    Column("sha256", String(64), nullable=False, index=True),
    Column("file_size", BigInteger, nullable=False),
    Column("sheet_name", Text),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("completed_at", DateTime(timezone=True)),
    Column("status", String(20), nullable=False),
    Column("duplicate_of_id", BigInteger, ForeignKey("source_imports.id")),
    Column("workbook_rows", Integer),
    Column("imported_rows", Integer),
    Column("rejected_rows", Integer, nullable=False, server_default="0"),
    Column("newest_issue_date", Date),
    Column("statistics", JSON),
    Column("error_message", Text),
)

source_fetches = Table(
    "source_fetches", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("completed_at", DateTime(timezone=True)),
    Column("portal_url", Text, nullable=False),
    Column("download_url", Text, nullable=False),
    Column("portal_source_date", Date),
    Column("http_status", Integer),
    Column("etag", Text),
    Column("last_modified", Text),
    Column("content_length", BigInteger),
    Column("downloaded_bytes", BigInteger),
    Column("sha256", String(64), index=True),
    Column("status", String(30), nullable=False),
    Column("saved_path", Text),
    Column("import_id", BigInteger, ForeignKey("source_imports.id")),
    Column("message", Text),
)

contractors = Table(
    "contractors", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("license_number", String(20), nullable=False, unique=True),
    Column("business_name", Text, nullable=False),
    Column("business_name_2", Text),
    Column("full_business_name", Text),
    Column("business_type", Text),
    Column("mailing_address", Text),
    Column("city", Text),
    Column("state", String(20)),
    Column("county", Text),
    Column("zip_code", String(20)),
    Column("country", Text),
    Column("phone_raw", Text),
    Column("phone_normalized", String(20)),
    Column("first_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_contractors_county_city", contractors.c.county, contractors.c.city)
Index("ix_contractors_zip", contractors.c.zip_code)

licenses = Table(
    "licenses", metadata,
    Column("license_number", String(20), primary_key=True),
    Column("contractor_id", BigInteger, ForeignKey("contractors.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("last_source_update", Date),
    Column("original_issue_date", Date, nullable=False),
    Column("reissue_date", Date),
    Column("expiration_date", Date),
    Column("inactivation_date", Date),
    Column("reactivation_date", Date),
    Column("primary_status", Text),
    Column("secondary_status", Text),
    Column("pending_suspension", Text),
    Column("pending_class_removal", Text),
    Column("pending_class_replace", Text),
    Column("asbestos_registration", Text),
    Column("classifications_raw", Text, nullable=False),
    Column("first_seen_import_id", BigInteger, ForeignKey("source_imports.id"), nullable=False),
    Column("last_seen_import_id", BigInteger, ForeignKey("source_imports.id"), nullable=False),
    Column("current_row_hash", String(64), nullable=False),
)
Index("ix_licenses_issue_date", licenses.c.original_issue_date)
Index("ix_licenses_status_issue", licenses.c.primary_status, licenses.c.original_issue_date)

classifications = Table(
    "classifications", metadata,
    Column("code", String(20), primary_key=True),
    Column("description", Text),
)

contractor_classifications = Table(
    "contractor_classifications", metadata,
    Column("license_number", String(20), ForeignKey("licenses.license_number", ondelete="CASCADE"), primary_key=True),
    Column("classification_code", String(20), ForeignKey("classifications.code"), primary_key=True),
    Column("position", Integer, nullable=False),
)
Index("ix_contractor_classifications_code", contractor_classifications.c.classification_code)

workers_comp = Table(
    "workers_comp", metadata,
    Column("license_number", String(20), ForeignKey("licenses.license_number", ondelete="CASCADE"), primary_key=True),
    Column("coverage_type", Text),
    Column("carrier", Text),
    Column("policy_number", Text),
    Column("effective_date", Date),
    Column("expiration_date", Date),
    Column("cancellation_date", Date),
    Column("suspension_date", Date),
)

bonds = Table(
    "bonds", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("license_number", String(20), ForeignKey("licenses.license_number", ondelete="CASCADE"), nullable=False),
    Column("bond_type", String(20), nullable=False),
    Column("surety_company", Text),
    Column("bond_number", Text),
    Column("effective_date", Date),
    Column("cancellation_date", Date),
    Column("amount", Numeric(14, 2)),
    Column("date_required", Date),
    Column("case_region", Text),
    Column("reason", Text),
    Column("case_number", Text),
    UniqueConstraint("license_number", "bond_type", name="uq_bond_license_type"),
)

license_snapshots = Table(
    "license_snapshots", metadata,
    Column("import_id", BigInteger, ForeignKey("source_imports.id", ondelete="CASCADE"), primary_key=True),
    Column("license_number", String(20), primary_key=True),
    Column("row_number", Integer, nullable=False),
    Column("row_hash", String(64), nullable=False),
    Column("raw_record", JSON, nullable=False),
)
Index("ix_license_snapshots_license", license_snapshots.c.license_number)

import_rejections = Table(
    "import_rejections", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("import_id", BigInteger, ForeignKey("source_imports.id", ondelete="CASCADE"), nullable=False),
    Column("row_number", Integer, nullable=False),
    Column("license_number_raw", Text),
    Column("reason", Text, nullable=False),
    Column("raw_record", JSON),
)

snapshot_changes = Table(
    "snapshot_changes", metadata,
    Column("id", ID_TYPE, primary_key=True, autoincrement=True),
    Column("previous_import_id", BigInteger, ForeignKey("source_imports.id")),
    Column("current_import_id", BigInteger, ForeignKey("source_imports.id"), nullable=False),
    Column("license_number", String(20), nullable=False),
    Column("change_type", String(40), nullable=False),
    Column("field_name", String(80)),
    Column("old_value", JSON),
    Column("new_value", JSON),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("current_import_id", "license_number", "change_type", "field_name", name="uq_snapshot_change"),
)
Index("ix_snapshot_changes_current_type", snapshot_changes.c.current_import_id, snapshot_changes.c.change_type)
Index("ix_snapshot_changes_license", snapshot_changes.c.license_number)

products = Table(
    "products", metadata,
    Column("sku", String(40), primary_key=True),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("price_cents", Integer, nullable=False),
    Column("currency", String(3), nullable=False, server_default="usd"),
    Column("classification_code", String(20), nullable=False),
    Column("counties", JSON, nullable=False),
    Column("window_days", Integer),
    Column("lead_limit", Integer),
    Column("recommended", Boolean, nullable=False, server_default="false"),
    Column("active", Boolean, nullable=False, server_default="true"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

orders = Table(
    "orders", metadata,
    Column("id", String(36), primary_key=True),
    Column("sku", String(40), ForeignKey("products.sku"), nullable=False),
    Column("status", String(30), nullable=False),
    Column("price_cents", Integer, nullable=False),
    Column("final_price_cents", Integer),
    Column("discount_cents", Integer, nullable=False, server_default="0"),
    Column("promotion_code", Text),
    Column("stripe_promotion_code_id", Text),
    Column("currency", String(3), nullable=False),
    Column("source_import_id", BigInteger, ForeignKey("source_imports.id"), nullable=False),
    Column("source_data_date", Date, nullable=False),
    Column("filter_definition", JSON, nullable=False),
    Column("pinned_lead_count", Integer, nullable=False),
    Column("stripe_checkout_session_id", Text, unique=True),
    Column("stripe_payment_intent_id", Text),
    Column("customer_email", Text),
    Column("utm_attribution", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("checkout_started_at", DateTime(timezone=True)),
    Column("paid_at", DateTime(timezone=True)),
    Column("fulfilled_at", DateTime(timezone=True)),
    Column("refunded_at", DateTime(timezone=True)),
    Column("refund_amount_cents", Integer, nullable=False, server_default="0"),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_orders_status_created", orders.c.status, orders.c.created_at)

order_leads = Table(
    "order_leads", metadata,
    Column("order_id", String(36), ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
    Column("license_number", String(20), primary_key=True),
    Column("position", Integer, nullable=False),
)

download_tokens = Table(
    "download_tokens", metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("order_id", String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("expires_at", DateTime(timezone=True)),
    Column("last_downloaded_at", DateTime(timezone=True)),
    Column("download_count", Integer, nullable=False, server_default="0"),
)

stripe_events = Table(
    "stripe_events", metadata,
    Column("event_id", Text, primary_key=True),
    Column("event_type", Text, nullable=False),
    Column("order_id", String(36), ForeignKey("orders.id")),
    Column("status", String(30), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("processed_at", DateTime(timezone=True)),
    Column("error_message", Text),
)

funnel_events = Table(
    "funnel_events", metadata,
    Column("id", String(36), primary_key=True),
    Column("event_type", String(50), nullable=False),
    Column("visitor_id", String(36)),
    Column("order_id", String(36), ForeignKey("orders.id")),
    Column("utm_source", Text), Column("utm_medium", Text), Column("utm_campaign", Text), Column("utm_content", Text), Column("utm_term", Text),
    Column("metadata", JSON, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_funnel_events_type_time", funnel_events.c.event_type, funnel_events.c.occurred_at)
