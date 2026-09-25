# CSLB posting-list research

Official index: <https://www2.cslb.ca.gov/Consumers/Data.aspx>

## What the files contain

“Posting List by Business” files are PDF posting-event lists, not a list of newly issued licenses. The observed PDF columns include application filing number (AFN), event/type and entity codes, exam/waiver indicator, DBA name, an existing license number when applicable, mailing address, posting date, examinee name, and requested classifications. Many rows have license number `0`, demonstrating that an application/posting is not a granted contractor license. The code meanings are not fully defined on the index and should not be guessed.

The files include person/examinee names. FreshTradeLeads does not need to expose these person-level fields and should not add them to a commercial report.

## Cadence and URLs

The index displayed one business and one personnel PDF for nearly every weekday, with gaps over weekends, and approximately one month of links. Names are predictable (`PLYYMMDD.pdf`), for example:

`https://www2.cslb.ca.gov/Resources/CSLB/PL260902.pdf`

The sample PDF had Last-Modified, ETag, Content-Length, and byte-range headers—better HTTP metadata than the master XLSX. CSLB states that posting lists changed to PDF in November 2020 and permits extracting their data programmatically.

## Recommendation

Do not integrate posting lists into production tonight. They are useful as an optional early application-intent signal, but they cannot support the claim “newly licensed” until the license appears in the master dataset with an IssueDate. A later experimental pipeline could:

1. ingest each business posting PDF as an immutable event;
2. retain AFN and posting date without selling examinee names;
3. label entries explicitly as pending/application signals;
4. reconcile them to a subsequently issued master license;
5. use the master dataset for authoritative business contact, status, bond, workers-comp, and IssueDate enrichment.

This could improve sales timing before master enrichment, but it represents a different product claim and needs semantic validation of CSLB’s type codes first.

