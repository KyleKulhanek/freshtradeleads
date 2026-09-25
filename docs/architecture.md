# Architecture

## Design goals

The pipeline separates immutable source history from the current query model. A source file is hashed before processing. Each successful file creates an import record and one immutable `license_snapshots` row per source record (raw JSON plus canonical row hash). Current normalized tables are upserted by CSLB license number. This supports future diffs without confusing “first observed by FreshTradeLeads” with “originally issued by CSLB.”

Classification strings such as `A| B| C10| C36` are split into ordered, de-duplicated codes. Raw strings are retained on `licenses`. Phone, ZIP, bond number, policy number, and license number are strings, preventing loss of formatting or leading zeroes. Dates are database `DATE` values.

## Import transaction behavior

Files stream through openpyxl in bounded batches. Required values are validated; bad rows enter `import_rejections` rather than being silently coerced. The importer upserts current entities, replaces each license's classification links, and appends immutable snapshot records. Exact source hashes are recorded as duplicate attempts and skipped.

The importer streams bounded workbook batches inside one database transaction. A database or parsing failure rolls back all current-table and snapshot mutations, while the import-attempt record is retained as failed for diagnosis. A PostgreSQL advisory transaction lock prevents overlapping imports. The downloader stages to a temporary filename, verifies hash/size/content, then atomically renames a new snapshot to a dated raw filename.

## Acquisition and change intelligence

`source_fetches` records every automated retrieval attempt and available HTTP metadata. Downloads are validated and atomically moved into `data/raw` before import. An application lock and systemd oneshot semantics prevent overlap.

`snapshot_changes` stores normalized comparisons between consecutive completed imports. Categories distinguish new source records, genuinely newly issued licenses, status, classification, workers-comp, bond, and removed-from-source events. Raw `license_snapshots` remain the source of truth, so every historical published row can be reconstructed. Comparisons collapse insignificant whitespace/case changes but retain old and new semantic values.

## Query boundaries

`IssueDate` is exposed as `original_issue_date`; `ReissueDate` stays separate. Last-N-days queries are inclusive and use the latest original issue date in the latest complete snapshot as their anchor. Classification filters operate on normalized association rows, never substring matching.

`IssueDate != first_seen_date`: IssueDate is CSLB's original issuance fact. First seen records when FreshTradeLeads happened to ingest the license. A license can be old but first observed today, or genuinely issued after the previous snapshot; the change model stores both concepts separately.
