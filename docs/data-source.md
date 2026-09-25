# CSLB data source and semantics

Source portal: <https://www.cslb.ca.gov/onlineservices/dataportal/ContractorList>

CSLB describes the no-cost license master as covering licenses that are currently renewed or expired-but-renewable, with business/contact, status, issue/expiration, classifications, bond, and workers-compensation information. Consequently, absence from a later file is meaningful but does not by itself prove a business ceased operating; future diff tooling should label it “no longer present in this source scope.” CSLB also warns that status can change and should be verified with its Instant License Check.

## Newly licensed definition

FreshTradeLeads defines “newly licensed” using workbook `IssueDate`, stored as `licenses.original_issue_date`. This is the original license issuance signal and is appropriate for identifying market entrants. `ReissueDate` is stored independently: it can represent reissuance/activity on an existing license and is not treated as a new market entry. `first_seen_import_id` means only when FreshTradeLeads first observed the license and is never substituted for issuance.

Edge cases:

- A recent `IssueDate` can still have a non-`CLEAR` status; status is a separate filter.
- Some newly issued licenses may already have a `ReissueDate`; original issue remains the primary recency field.
- The file includes renewed and expired-but-renewable licenses, not every historical CSLB license.
- Calendar-day windows contain exactly N dates, inclusive of the anchor date, from `anchor - (N - 1) days` through the anchor.
- Future-dated insurance or cancellation fields are preserved as published; they do not affect issue-date recency.

## Fields relied on

Stable key: `LicenseNo`. Recency: `IssueDate`. Status: `PrimaryStatus` and `SecondaryStatus`. Trades: `Classifications(s)`. Geography: mailing `City`, `State`, `County`, and `ZIPCode`. Business contact/type: `BusinessName`, `MailingAddress`, `BusinessPhone`, `BusinessType`. Coverage and bond fields retain the workbook's current values.
