"""S1 - Unit tests cho chuẩn hóa dữ liệu và ghép hạng mục.

Chạy riêng:
    python -m pytest -q -ra tests/test_s1_normalizer.py
"""

from __future__ import annotations

from typing import Any

import pytest

from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import DocumentRole, ItemRecord, MatchKind, RowType
from core.number_parser import parse_number, percent_delta, safe_amount
from core.text_normalizer import (
    normalize_code,
    normalize_name,
    normalize_stt,
    normalize_unit,
)


def _cfg() -> EnterpriseConfig:
    config = EnterpriseConfig()
    config.enable_semantic_matching = False
    config.enable_reranker = False
    return config


def _item(
    *,
    code: str,
    name: str,
    unit: str = "cái",
    sheet: str = "Điện",
    row: int = 2,
    role: DocumentRole = DocumentRole.HSDT,
    bidder: str = "NT",
) -> ItemRecord:
    return ItemRecord(
        source_id=f"{bidder}:{sheet}:{row}",
        role=role,
        bidder=bidder,
        workbook=f"{bidder}.xlsx",
        sheet=sheet,
        row_number=row,
        item_code=code,
        item_name=name,
        unit=unit,
        row_type=RowType.DETAIL,
        normalized_code=normalize_code(code),
        normalized_name=normalize_name(name),
        normalized_unit=normalize_unit(unit),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234.567,89", 1_234_567.89),
        ("1,234,567.89", 1_234_567.89),
        ("1 234 567", 1_234_567.0),
        ("(1.000)", -1_000.0),
        ("-0.5", -0.5),
        ("1.500.000 VNĐ", 1_500_000.0),
        (0, 0.0),
    ],
)
def test_s1_nr01_parse_vietnamese_and_international_numbers(
    raw: Any,
    expected: float,
) -> None:
    """Đọc đúng các kiểu số Việt Nam và quốc tế."""
    assert parse_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize(
    "raw",
    ["m2", "M2", "m²", "m^2", "m 2", "mét vuông", "met vuong"],
)
def test_s1_nr02_normalize_square_metre_variants(raw: str) -> None:
    """Mọi biến thể đơn vị diện tích phải trở thành m²."""
    assert normalize_unit(raw) == "m²"


@pytest.mark.parametrize(
    "raw",
    ["m3", "M3", "m³", "m^3", "m 3", "mét khối", "met khoi"],
)
def test_s1_nr03_normalize_cubic_metre_variants(raw: str) -> None:
    """Mọi biến thể đơn vị thể tích phải trở thành m³."""
    assert normalize_unit(raw) == "m³"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Cái", "cái"),
        ("chiếc", "cái"),
        ("BỘ", "bộ"),
        ("tủ", "tủ"),
        ("mét", "m"),
        ("thiết bị", "thiết bị"),
        ("kg", "kg"),
        ("Tấn", "tấn"),
        ("100m", "100m"),
    ],
)
def test_s1_nr04_normalize_common_units(raw: str, expected: str) -> None:
    """Chuẩn hóa các đơn vị phổ biến."""
    assert normalize_unit(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("M01", "M-01"),
        ("M.01", "M-01"),
        ("M/01", "M-01"),
        (" AB_12 ", "AB-12"),
        ("=A1", ""),
        ("", ""),
    ],
)
def test_s1_nr05_normalize_item_codes(raw: str, expected: str) -> None:
    """Chuẩn hóa mã hiệu và loại bỏ ô chứa công thức."""
    assert normalize_code(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" I.1 ", "I.1"),
        ("1.2.3", "1.2.3"),
        (" A-01 ", "A-01"),
        ("=ROW()-1", ""),
        ("", ""),
    ],
)
def test_s1_nr06_normalize_stt(raw: str, expected: str) -> None:
    """Chuẩn hóa STT và không nhận công thức làm STT."""
    assert normalize_stt(raw) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Tủ điện LV-G.1 + LV-G.2", "TU DIEN LV G 1 LV G 2"),
        ("Máy bơm nước sinh hoạt", "MAY BOM NUOC SINH HOAT"),
        ("Cáp điện 3×2.5 mm²", "cap dien 3x2 5 mm2"),
    ],
)
def test_s1_nr07_normalize_vietnamese_names_and_symbols(
    left: str,
    right: str,
) -> None:
    """Tên có dấu, không dấu và ký hiệu kỹ thuật phải quy về cùng khóa."""
    assert normalize_name(left) == normalize_name(right)


def test_s1_nr08_safe_amount_respects_explicit_zero() -> None:
    """Giá trị thành tiền bằng 0 phải được giữ nguyên."""
    assert safe_amount(2, 100, 0) == 0
    assert safe_amount(2, 100, None) == 200


@pytest.mark.parametrize(
    ("baseline", "candidate", "expected"),
    [
        (100, 108, 0.08),
        (100, 95, -0.05),
        (100, 100, 0.0),
    ],
)
def test_s1_nr09_percent_delta(
    baseline: float,
    candidate: float,
    expected: float,
) -> None:
    """Tính đúng tỷ lệ tăng, giảm và không chênh lệch."""
    assert percent_delta(baseline, candidate) == pytest.approx(expected)


def test_s1_nr10_hybrid_match_is_one_to_one() -> None:
    """Mỗi dòng chuẩn và dòng ứng viên chỉ được ghép một lần."""
    references = [
        _item(
            code="M-01",
            name="Tủ điện phân phối tổng",
            row=2,
            role=DocumentRole.HSMT,
            bidder="PL01",
        ),
        _item(
            code="M-02",
            name="Cáp đồng XLPE 4x10",
            row=3,
            role=DocumentRole.HSMT,
            bidder="PL01",
        ),
    ]

    candidates = [
        _item(code="M01", name="Tủ phân phối điện tổng", row=8, bidder="A"),
        _item(
            code="",
            name="Cáp điện đồng cách điện XLPE 4 x 10",
            row=9,
            bidder="A",
        ),
    ]

    matches = match_items(references, candidates, _cfg())
    paired = [
        match
        for match in matches
        if match.reference_index is not None
        and match.candidate_index is not None
    ]

    assert len(paired) == 2
    assert len({match.reference_index for match in paired}) == 2
    assert len({match.candidate_index for match in paired}) == 2


def test_s1_nr11_exact_name_can_match_across_different_sheets() -> None:
    """Tên chính xác vẫn phải ghép dù hai file dùng tên sheet khác nhau."""
    item_name = "Tủ điện LV-G.1+LV-G.2+LV-G.3+LV-G.4+LV-G.5+LV-G.6"

    reference = _item(
        code="",
        name=item_name,
        unit="Tủ",
        sheet="2 - PHAN TU HA THE",
        role=DocumentRole.HSMT,
        bidder="PHỤ LỤC 01",
    )
    candidate = _item(
        code="",
        name=item_name,
        unit="Tủ",
        sheet="1. HT điện",
        role=DocumentRole.HSDT,
        bidder="Linh Anh",
    )

    matches = match_items([reference], [candidate], _cfg())
    paired = [
        match
        for match in matches
        if match.reference_index == 0 and match.candidate_index == 0
    ]

    assert len(paired) == 1
    assert paired[0].kind is MatchKind.EXACT_NAME
    assert paired[0].score >= 0.95
    assert "khác tên sheet" in paired[0].reason.lower()


def test_s1_nr12_different_names_are_not_forced_into_exact_name_match() -> None:
    """Hai hạng mục khác nhau không được gắn nhãn EXACT_NAME."""
    reference = _item(
        code="",
        name="Tủ điện phân phối tổng",
        role=DocumentRole.HSMT,
        bidder="PL01",
    )
    candidate = _item(
        code="",
        name="Ống nước HDPE D110",
        role=DocumentRole.HSDT,
        bidder="Nhà thầu A",
    )

    matches = match_items([reference], [candidate], _cfg())
    exact_pairs = [
        match
        for match in matches
        if match.reference_index == 0
        and match.candidate_index == 0
        and match.kind is MatchKind.EXACT_NAME
    ]

    assert exact_pairs == []
