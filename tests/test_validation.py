from freshtradeleads.importer import import_xlsx
from freshtradeleads.validation import validation_report


def test_validation_report(engine,workbook):
    import_xlsx(engine,workbook)
    with engine.connect() as c: report=validation_report(c)
    assert report["workbook_rows"] == report["records_imported"] == 3
    assert report["recent_issue_counts"]["7"] == 2
    assert report["duplicate_license_numbers"] == 0

