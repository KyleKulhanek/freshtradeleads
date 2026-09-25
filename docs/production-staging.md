# Production deployment guide

A recommended ingress chain is:

`HTTPS edge or tunnel -> Caddy/Nginx -> FreshTradeLeads 127.0.0.1:8080`

Keep PostgreSQL and Uvicorn off the public network. Terminate TLS at the reverse
proxy, restrict accepted hostnames, limit request bodies, and forward the
original HTTPS scheme. The example systemd and Caddy files in `ops/` use generic
paths and hostnames and must be reviewed for each deployment.

## Services and operations

```bash
sudo systemctl status freshtradeleads-web
sudo systemctl restart freshtradeleads-web
sudo journalctl -u freshtradeleads-web -f
sudo systemctl status freshtradeleads-source-fetch.timer
curl http://127.0.0.1:8080/health
```

Uvicorn access logging is disabled in the supplied service because fulfillment
URLs contain bearer download tokens. Ensure the reverse proxy also avoids
logging query strings or sensitive download paths.

## Stripe environments and promotions

Create separate Stripe test and live credentials. Store every secret and object
identifier outside Git. Configure the webhook for Checkout completion,
expiration, asynchronous payment success/failure, and refunds. The application
verifies signatures and fulfills only a paid Session matching the pinned order,
currency, approved amount, and approved promotion. Event IDs make replays
idempotent; full refunds revoke downloads and partial refunds remain recorded.

Promotion codes are allowlisted through environment variables. Guest Checkout
does not provide durable per-person “first purchase” enforcement; that requires
stable Customer reuse or an application-level identity step.

## Meta Pixel

Set `META_PIXEL_ID` only if browser advertising measurement is appropriate for
your deployment and disclosed in its privacy policy. Never put a Meta Marketing
API token in the web application's environment. First-party funnel events,
pinned orders, and UTM attribution remain authoritative.

## Release checklist

- Replace all example hostnames, paths, recipients, and identifiers.
- Generate a strong session secret and enable secure cookies behind HTTPS.
- Use a restricted live Stripe key and a distinct live webhook secret.
- Review the legal, privacy, refund, data-retention, and tax checklist.
- Test payment, fulfillment, download expiry, refunds, and webhook replay.
- Confirm database backups and a credential-rotation procedure.

Never commit production environment files, source workbooks, generated reports,
order data, API credentials, or payment/advertising object identifiers.
