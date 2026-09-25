# Official CSLB source acquisition

## Selected source

Portal: <https://www.cslb.ca.gov/onlineservices/dataportal/ContractorList>

Official XLSX handler: <https://www.cslb.ca.gov/OnlineServices/DataPortal/DownLoadFile.ashx?fName=MasterLicenseData&type=X>

The portal's License Master selection performs an ordinary ASP.NET postback which resolves to the handler above. The handler is an official, stable, unauthenticated download and is therefore preferable to browser automation. It returns a ZIP-based XLSX despite the legacy `application/vnd.ms-excel` content type.

Observed download metadata on 2026-09-04:

- HTTP 200 and attachment filename `MasterLicenseData.xlsx`
- no ETag
- no Last-Modified
- no Content-Length (chunked transfer)
- Range request ignored

Consequently, portal `Updated as of` supplies the filename date and SHA-256 supplies identity. The portal showed 2026-09-02. The master page does not document a contractual publication schedule; observed behavior is compatible with business-day updates, so the timer checks once daily and unchanged content is cheap aside from the download.

## SOAP assessment

The official `GetbyClassification.asmx` WSDL exposes `GetMasterFile(fileType, Token)` and returns base64. A standards-compliant request with an empty token returned the UTF-16 message `Missing Token`. The public WSDL and operation page do not document token issuance, eligibility, or lifecycle. No attempt was made to guess or bypass it. Unless CSLB provides documented credentials later, the public download handler is the supported practical choice.

## Safe fetch pipeline

```bash
freshtradeleads --json source fetch
```

The command takes a nonblocking filesystem lock, reads the official source date, downloads into a hidden temporary file on the same filesystem, flushes it, validates its ZIP/XLSX structure, worksheet, critical headers, size, and row count, then hashes it. An existing completed-import hash results in `unchanged` and temporary-file deletion. A new hash is atomically renamed to a dated raw path before import, validation, and change reporting. Failures are recorded in `source_fetches`, logged with a traceback, return nonzero, and do not replace existing raw files.

## Scheduling and operations

The installed timer checks daily at 1:15 PM America/Los_Angeles with up to 15 minutes randomized delay:

```bash
systemctl status freshtradeleads-source-fetch.timer
sudo systemctl start freshtradeleads-source-fetch.service
journalctl -u freshtradeleads-source-fetch.service -n 200 --no-pager
sudo systemctl disable --now freshtradeleads-source-fetch.timer
sudo systemctl enable --now freshtradeleads-source-fetch.timer
```

Systemd will not start a second instance of an active oneshot service; the application lock also prevents overlap with manual execution.

## Failure recovery

Read the service journal and the latest `source_fetches` row. HTTP and validation failures need no cleanup because temporary files are removed. A valid new raw snapshot is deliberately retained if a later import/report stage fails, allowing a manual retry after correcting the cause. Never delete the latest completed source or restore a snapshot merely for a fetch error.

