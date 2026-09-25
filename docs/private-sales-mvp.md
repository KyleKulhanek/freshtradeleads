# Private sales MVP

The application is a server-rendered FastAPI service intended to bind to loopback behind a TLS-terminating reverse proxy. See [production-staging.md](production-staging.md).

## Products

- `starter`: $15, ten newest C10 Southern California leads
- `fresh-pack`: $29, all matching leads in the 14-day window (recommended)
- `expanded`: $59, all matching leads in the 30-day window

Counts and the source-data date come from the newest completed import. Southern California means Los Angeles, Orange, Riverside, San Bernardino, San Diego, and Ventura counties.

## Orders and fulfillment

Checkout freezes the product, price, filter, source import, source date, ordered license identifiers, and exact count. Reports are reconstructed from `license_snapshots.raw_record` for that pinned import—not mutable current tables.

Stripe-hosted Checkout handles one-time payment. A browser return never changes payment state. Only a signature-verified Stripe event whose Session identifier, amount, currency, and paid status match the order can authorize fulfillment. Stripe event IDs make handling idempotent.

The application creates a 256-bit URL-safe token and stores only its SHA-256 digest. It activates after verified fulfillment and expires seven days later. Reports live in ignored `data/web/orders/` paths.

## Secret configuration

`/etc/freshtradeleads-web.env` is outside Git:

```dotenv
FRESHTRADELEADS_DATABASE_URL=postgresql+psycopg:///freshtradeleads
FRESHTRADELEADS_DATA_DIR=/opt/freshtradeleads/data
FRESHTRADELEADS_BASE_URL=https://leads.example.com
FRESHTRADELEADS_SESSION_SECRET=<random value>
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER=price_...
STRIPE_PRICE_FRESH_PACK=price_...
STRIPE_PRICE_EXPANDED=price_...
STRIPE_USE_CLI=true
FRESHTRADELEADS_DOWNLOAD_DAYS=7
```

For optional local-development webhook delivery, authenticate Stripe CLI on a LAN machine and run:

```bash
stripe listen --forward-to http://127.0.0.1:8080/webhooks/stripe
```

The public sandbox instead uses the registered HTTPS endpoint and its distinct signing secret. `STRIPE_USE_CLI=true` currently activates the OAuth-managed CLI adapter strictly for sandbox Checkout creation; live production must use a dedicated restricted server API key. Checkout uses pre-created, allowlisted Stripe Price IDs and the local order UUID as Stripe's idempotency key. Initial payment methods are restricted to cards and eligible card-backed wallets so paid digital delivery is immediate.

## Operations

```bash
sudo systemctl status freshtradeleads-web
sudo systemctl restart freshtradeleads-web
sudo journalctl -u freshtradeleads-web -f
curl http://127.0.0.1:8080/health
```

The independent CSLB fetch timer remains enabled.

## Funnel measurement

`funnel_events` records landing views, sample downloads, checkout starts, verified payments, and paid-report downloads. Common `utm_*` values are retained in a signed first-party session and copied to the order. No third-party analytics are installed.

## Historical phase-three blockers

- Owner/legal review of Privacy, Terms, and Refund Policy drafts
- Owner/legal approval remains outstanding.
- Live Stripe objects and a dedicated restricted live credential remain intentionally unconfigured.
