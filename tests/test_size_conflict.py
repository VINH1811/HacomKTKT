"""Tên hạng mục là mã kích thước: các con số mới là danh tính.

Ống gió và ống nước thường được đặt tên bằng chính kích thước ("KT 1350x300",
"D90/40"). Chữ cái giống hệt nhau nên điểm so khớp chuỗi rất cao — "KT 1350x300"
và "KT 350x350" đạt 0.68 và từng bị ghép làm một. Hậu quả là hệ thống so khối
lượng, thương hiệu, mã hiệu của HAI hạng mục khác nhau rồi báo lệch tới 450%.

Đo trên hồ sơ thật: lớp chặn này loại 49 cặp ghép sai trên bốn nhà thầu.
"""

from __future__ import annotations

import pytest

from core.matcher import _has_size_conflict, _size_tokens
from core.models import DocumentRole, ItemRecord, RowType
from core.text_normalizer import normalize_name


def _item(name: str) -> ItemRecord:
    return ItemRecord(
        source_id="x", role=DocumentRole.HSDT, bidder="b", workbook="w", sheet="s",
        row_number=1, row_type=RowType.DETAIL, stt="1", item_code="", item_name=name,
        unit="m", material="", brand="", origin="", note="",
        normalized_name=normalize_name(name), normalized_code="",
        normalized_unit="m", normalized_path="", structural_key="",
    )


@pytest.mark.parametrize("text, expected", [
    ("KT 1350x300", {"1350", "300"}),
    ("KT 600x600/600x600", {"600"}),
    ("DN100", {"100"}),
    # normalize_name bỏ dấu "/" nên chỉ còn "d90"; vẫn đủ phân biệt với D110.
    ("D90/40", {"90"}),
    # Độ dày 0.58mm không phải kích thước, không được tính vào danh tính.
    ("KT 250x200/150x150 độ dày tôn 0.58mm", {"250", "200", "150"}),
    ("Đầu báo khói địa chỉ", set()),
    ("MCB 2P 50A 6kA", set()),
])
def test_size_tokens(text: str, expected: set[str]):
    assert set(_size_tokens(normalize_name(text))) == expected


@pytest.mark.parametrize("left, right", [
    ("KT 1350x300", "KT 350x350"),
    ("KT 1200x600", "KT: 600x600/600x600"),
    ("KT 700x900", "KT 900x600/600x900"),
    ("D90/40", "D110-40"),
    ("Ống thép DN100", "Ống thép DN80"),
])
def test_different_sizes_are_blocked(left: str, right: str):
    assert _has_size_conflict(_item(left), _item(right)) is True


@pytest.mark.parametrize("left, right", [
    ("KT 250x200/150x150 độ dày tôn 0.58mm", "KT 250x200/150x150"),
    ("D140", "Bích PPR D140"),
    ("D280", "Mặt bích HDPE D280"),
    ("Ống thép tráng kẽm DN100", "Ống thép mạ kẽm DN100"),
])
def test_same_sizes_are_allowed(left: str, right: str):
    assert _has_size_conflict(_item(left), _item(right)) is False


@pytest.mark.parametrize("left, right", [
    ("Đầu báo khói địa chỉ", "Đầu báo khói loại địa chỉ"),
    ("Vật tư phụ", "Vật tư phụ lắp đặt"),
])
def test_names_without_sizes_are_untouched(left: str, right: str):
    # Không có kích thước thì lớp chặn này không can thiệp.
    assert _has_size_conflict(_item(left), _item(right)) is False
