from core.number_parser import parse_number, safe_amount


def test_parse_vietnamese_and_international_numbers():
    assert parse_number("1.234.567,89") == 1234567.89
    assert parse_number("1,234,567.89") == 1234567.89
    assert parse_number("1 234 567") == 1234567
    assert parse_number("(1.000)") == -1000
    assert parse_number("-0.5") == -0.5
    assert parse_number(0) == 0
    assert safe_amount(2, 100, 0) == 0
