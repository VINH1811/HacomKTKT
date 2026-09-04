"""Không gọi được AI thì vẫn phải đưa ra khoảng giá bằng thống kê.

Phản hồi thực tế: máy chủ Ollama không chạy nên bảng dự đoán giá trắng hoàn
toàn — trạng thái FAILED, mọi ô N/A. Nhưng CSDL giá nội bộ vẫn có sẵn dữ liệu
tham chiếu; tính khoảng giá từ đó không cần mô hình nào cả.

Trả về bảng trống trong tình huống đó là vứt đi thông tin đang nằm sẵn trong
tay người dùng.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app import _statistical_price


@dataclass
class _Record:
    unit_price: float | None
    unit: str


@dataclass
class _Match:
    record: _Record


def _items(pairs: list[tuple[float | None, str]]) -> list[_Match]:
    return [_Match(_Record(price, unit)) for price, unit in pairs]


def test_range_is_computed_from_matching_units():
    status, low, high, confidence, reason = _statistical_price(
        _items([(100_000, "m"), (150_000, "m"), (120_000, "m")]), "m")
    assert status == "validated"
    assert low == pytest.approx(95_000)      # thấp nhất trừ biên 5%
    assert high == pytest.approx(157_500)    # cao nhất cộng biên 5%
    assert confidence == 0.8
    assert "3 báo giá" in reason


def test_other_units_are_excluded():
    # Trộn đ/m với đ/bộ thì khoảng giá vô nghĩa.
    status, low, high, _, _ = _statistical_price(
        _items([(100_000, "m"), (9_000_000, "bộ")]), "m")
    assert status == "validated"
    assert low == pytest.approx(95_000) and high == pytest.approx(105_000)


def test_unit_comparison_ignores_case_and_spaces():
    status, low, _, _, _ = _statistical_price(_items([(100_000, " M ")]), "m")
    assert status == "validated" and low == pytest.approx(95_000)


def test_missing_prices_are_skipped():
    status, low, _, _, _ = _statistical_price(
        _items([(None, "m"), (100_000, "m")]), "m")
    assert status == "validated" and low == pytest.approx(95_000)


@pytest.mark.parametrize("items, unit", [
    ([], "m"),
    ([(100_000, "bộ")], "m"),
    ([(None, "m")], "m"),
])
def test_no_reference_gives_needs_review_not_a_wrong_number(items, unit):
    status, low, high, confidence, reason = _statistical_price(_items(items), unit)
    assert status == "needs_review"
    assert low is None and high is None and confidence == 0.0
    assert "Không có mẫu tham chiếu" in reason
