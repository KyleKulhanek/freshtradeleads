# FreshTradeLeads

FreshTradeLeads is an open-source Python toolkit for turning the California
Contractors State License Board (CSLB) public master-license workbook into a
normalized, queryable database and reproducible CSV/XLSX reports.

The project began as a small commercial experiment. That experiment has ended,
and the complete application is now published as a portfolio and reference
project. It is not an active hosted service, but the data engine, web storefront,
Stripe integration, automated source checks, and campaign-reporting code remain
available for reuse.

## What it does

- Imports dated CSLB workbooks into PostgreSQL with source hashes and audit metadata.
- Preserves immutable snapshots while maintaining normalized current records.
- Searches and exports reports by trade, location, status, date, and coverage.
- Detects source changes and produces validation and change reports.
- Includes optional FastAPI/Stripe storefront and campaign-reporting components.

Only synthetic fixtures are included. CSLB workbooks, generated reports,
databases, order records, credentials, and advertising identifiers are excluded.

## Quick start

Requirements: Python 3.11+ and PostgreSQL.

```bash
git clone https://github.com/KyleKulhanek/freshtradeleads.git
cd freshtradeleads
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'

sudo -u postgres createuser "$USER"
sudo -u postgres createdb -O "$USER" freshtradeleads
export FRESHTRADELEADS_DATABASE_URL=postgresql+psycopg:///freshtradeleads
```

Place a dated CSLB workbook in `data/raw/` and import it:

```bash
freshtradeleads import-file data/raw/YYYY-MM-DD_MasterLicenseData.xlsx
freshtradeleads stats
freshtradeleads --json doctor
freshtradeleads validate --out data/processed/validation.json
```

Search and export:

```bash
freshtradeleads search --classification C10 --county "Los Angeles" --days 30
freshtradeleads export --classification C36 --days 7 --format csv \
  --out data/exports/plumbers.csv
```

Recency is inclusive and anchored to the newest `IssueDate` in the imported
source, rather than the machine clock, so historical imports are reproducible.

## Architecture

The CLI uses SQLAlchemy and PostgreSQL. Core tables cover source imports,
contractors, licenses, classifications, workers compensation, bonds, immutable
license snapshots, and import rejections. See [the architecture guide](docs/architecture.md).

The optional web app is a server-rendered FastAPI service. Copy `.env.example`,
replace every placeholder, and review [the storefront guide](docs/private-sales-mvp.md)
before enabling payment handling. Never commit the resulting environment file.

## Tests

```bash
pytest
```

The suite uses a generated synthetic workbook and isolated SQLite databases; no
production data or external credentials are required.

## Data source and responsible use

The source workbook is published by CSLB. Review its terms and applicable law
before collecting, redistributing, or using its records. This repository does
not include the source data. Users are responsible for lawful outreach, privacy
compliance, and honoring opt-outs.

FreshTradeLeads is independent and is not affiliated with or endorsed by CSLB.

## Project status

This repository is archived as a completed experiment and is provided without a
hosted service or maintenance commitment. Issues and forks are welcome, but
response times are not guaranteed.

## License

[MIT](LICENSE) — free to use, modify, and redistribute while retaining the
copyright and license notice.
