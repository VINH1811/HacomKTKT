"""Sổ tay tên cột: hiểu viết tắt và biến thể, nhưng không đoán bừa.

Hồ sơ thầu viết tắt rất nhiều: ĐVT, KLMT, ĐGTH, TT. Bộ luật từ khóa chính khớp
chuỗi con nên chỉ đúng với những cách viết đã liệt kê sẵn — gặp cách viết mới là
cả cột bị bỏ sót. Lớp này chạy CUỐI CÙNG, chỉ nhận những cột chưa khóa nào lấy.

Ngưỡng đặt cao có chủ đích: nhầm một cột còn tệ hơn bỏ sót, vì bỏ sót thì đã có
cảnh báo và lớp suy luận theo số liệu đỡ tiếp.
"""

from __future__ import annotations

import pytest

from core.column_synonyms import guess_field, score_header
from core.excel_reader import _flatten_header, map_columns
from core.models import DocumentRole

FIELDS = ("stt", "item_code", "item_name", "unit", "bid_quantity",
          "reference_quantity", "unit_price_total", "bid_amount",
          "material", "brand", "origin", "note")


@pytest.mark.parametrize("header, field", [
    ("ĐVT", "unit"),
    ("Đ.V.T", "unit"),
    ("ĐGTH", "unit_price_total"),
    ("KLMT", "reference_quantity"),
    ("TT", "bid_amount"),
    ("Ten hang muc", "item_name"),
    ("THUONG HIEU", "brand"),
    ("Xuat xu", "origin"),
    ("Ghi chu", "note"),
])
def test_abbreviations_and_accentless_forms(header: str, field: str):
    assert guess_field(header, FIELDS) == (field, 100.0)


@pytest.mark.parametrize("header", [
    "Cột 5", "X1", "1", "Ghi chú thêm của tổ thẩm định", "ĐƠN VỊ THI CÔNG",
])
def test_meaningless_or_misleading_headers_are_refused(header: str):
    assert guess_field(header, FIELDS) is None


def test_user_can_extend_the_vocabulary(monkeypatch: pytest.MonkeyPatch):
    assert guess_field("Đơn giá kiểu mới XYZ", FIELDS) is None
    monkeypatch.setenv("HSMT_COLUMN_SYNONYMS",
                       "unit_price_total=Đơn giá kiểu mới XYZ;note=Diễn giải thêm")
    guessed = guess_field("Đơn giá kiểu mới XYZ", FIELDS)
    assert guessed and guessed[0] == "unit_price_total"


def test_score_is_zero_for_empty_header():
    assert score_header("", "unit") == 0.0
    assert score_header("   ", "unit") == 0.0


# ------------------------------------------------- tích hợp vào map_columns

def _map(header: list[str]) -> dict[int, str]:
    fixed, _ = map_columns(_flatten_header([header], len(header)), DocumentRole.HSDT)
    return fixed


def test_all_abbreviated_header_is_mapped():
    fixed = _map(["STT", "Mã hiệu", "Tên hạng mục", "Đ.V.T", "KLNT", "ĐGTH", "TT"])
    assert fixed[3] == "unit"
    assert fixed[4] == "bid_quantity"
    assert fixed[5] == "unit_price_total"
    assert fixed[6] == "bid_amount"


def test_standard_header_is_untouched():
    header = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "KL nhà thầu chào",
              "Đơn giá tổng hợp", "Thành tiền", "Thương hiệu", "Xuất xứ"]
    fixed = _map(header)
    assert [fixed.get(i) for i in range(len(header))] == [
        "stt", "item_code", "item_name", "unit", "bid_quantity",
        "unit_price_total", "bid_amount", "brand", "origin",
    ]


def test_meaningless_columns_stay_unmapped():
    fixed = _map(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Cột 5", "Cột 6", "Cột 7"])
    assert 4 not in fixed and 5 not in fixed and 6 not in fixed
