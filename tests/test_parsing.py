from datetime import date
import pytest
from freshtradeleads.parsing import parse_classifications, parse_date, normalize_phone


def test_classification_parsing_is_normalized_and_ordered():
    assert parse_classifications(" A | B | C10 | C10 ") == ["A","B","C10"]


def test_date_parsing_and_invalid_date():
    assert parse_date(" 09/02/2026") == date(2026,9,2)
    with pytest.raises(ValueError): parse_date("2026/09/02")


def test_phone_normalization():
    assert normalize_phone("+1 (213) 555-0100") == "2135550100"

