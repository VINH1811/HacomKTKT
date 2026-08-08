"""Ba lỗi ghi nhận từ phản hồi người dùng khi chấm gói PCCC / Thông gió.

1. Ống thép chữa cháy bị ghép với ống luồn dây điện (và các cặp tương tự) khiến
   mô tả, thương hiệu hiển thị sai.
2. Cột chi phí quản lý bị bỏ trống dù nhà thầu có chào — do hồ sơ viết tắt khác
   với "CF quản lý"; nặng hơn là "CPQL"/"QL" từng bị nhận nhầm thành đơn giá.
3. Ô "Mô tả/Quy cách" trong bảng tổng hợp đầy ghi chú lạc đề (thiếu đơn giá,
   tổng hợp giá...) vì mọi sai lệch không có ô riêng đều bị dồn vào đó.
"""

from __future__ import annotations

from core.excel_reader import _flatten_header, map_columns
from core.matcher import _has_type_conflict, _lexical_score
from core.models import DocumentRole, ItemRecord, RowType
from core.reporter import _NOTE_IDX, _leaf_for_field
from core.text_normalizer import normalize_name


def _item(name: str, unit: str = "m") -> ItemRecord:
    return ItemRecord(
        source_id="x", role=DocumentRole.HSDT, bidder="b", workbook="w", sheet="PCCC",
        row_number=1, item_name=name, unit=unit,
        normalized_name=normalize_name(name), normalized_unit=unit,
        row_type=RowType.DETAIL,
    )


# --------------------------------------------------------------------------
# 1. Ghép nhầm chủng loại
# --------------------------------------------------------------------------

CONFLICTING = [
    ("Ống thép đen luồn dây chữa cháy D100", "Ống luồn dây điện D100"),
    ("Bình chữa cháy bột ABC 8kg", "Bình chữa cháy khí CO2 5kg"),
    ("Cáp điện Cu/XLPE/PVC 3x95", "Cáp điện Cu/PVC 3x95"),
    ("Đầu báo khói địa chỉ", "Đầu báo nhiệt địa chỉ"),
    ("Ống gió tôn tráng kẽm", "Ống nhựa PVC D90"),
]

COMPATIBLE = [
    ("Ống thép tráng kẽm DN100", "Ống thép tráng kẽm DN 100"),
    ("Đầu báo khói địa chỉ", "Đầu báo khói địa chỉ GST"),
    ("Cáp Cu/XLPE 3x95", "Cáp điện Cu/XLPE 3x95 mm2"),
    ("Tủ điện tổng MSB", "Tủ điện tổng MSB-1"),
]


def test_conflicting_types_are_blocked():
    for left, right in CONFLICTING:
        assert _has_type_conflict(_item(left), _item(right)), (
            f"Phải chặn ghép: {left!r} ↔ {right!r}"
        )


def test_same_type_still_matches():
    for left, right in COMPATIBLE:
        assert not _has_type_conflict(_item(left), _item(right)), (
            f"KHÔNG được chặn: {left!r} ↔ {right!r}"
        )


def test_conflicting_pairs_are_lexically_similar():
    # Chứng minh vì sao cần luật này: chỉ dựa vào điểm giống chữ thì đã ghép nhầm.
    for left, right in CONFLICTING[:4]:
        assert _lexical_score(_item(left), _item(right)) >= 0.58


# --------------------------------------------------------------------------
# 2. Cột chi phí quản lý
# --------------------------------------------------------------------------

MANAGEMENT_LABELS = ["CF quản lý", "Chi phí quản lý", "Quản lý", "CP quản lý",
                     "CPQL", "QL", "Chi phí chung"]


def _price_row_mapping(management_label: str) -> dict[int, str]:
    top = ["STT", "Hạng mục", "ĐVT", "ĐƠN GIÁ", None, None, None, None]
    sub = [None, None, None, "VL chính", "NC&M", management_label, "Lợi nhuận", "ĐG tổng hợp"]
    flat = _flatten_header([top, sub], len(top))
    fixed, _ = map_columns(flat, DocumentRole.HSDT)
    return fixed


def test_management_cost_column_recognised_in_all_spellings():
    for label in MANAGEMENT_LABELS:
        mapping = _price_row_mapping(label)
        assert mapping.get(5) == "price_management", (
            f"Cột {label!r} không được nhận là chi phí quản lý (được {mapping.get(5)!r})"
        )


def test_total_unit_price_column_still_correct():
    # Không được để biến thể mới nuốt mất cột ĐG tổng hợp.
    for label in MANAGEMENT_LABELS:
        assert _price_row_mapping(label).get(7) == "unit_price_total"


# --------------------------------------------------------------------------
# 3. Ghi chú lạc đề trong ô Mô tả/Quy cách
# --------------------------------------------------------------------------

def test_item_description_fields_map_to_description_cell():
    assert _leaf_for_field("Tên hạng mục") == _NOTE_IDX
    assert _leaf_for_field("Thông số: Công suất") == _NOTE_IDX
    assert _leaf_for_field("Vật tư/Quy cách") == _NOTE_IDX


def test_quantity_variants_map_to_quantity_cell():
    from core.reporter import _KL_IDX
    assert _leaf_for_field("Khối lượng nhà thầu chào") == _KL_IDX
    assert _leaf_for_field("KL mời thầu trong file") == _KL_IDX


def test_non_item_warnings_are_not_pushed_into_description():
    from core.reporter import _NON_ITEM_FIELDS
    for field in ("Chất lượng dữ liệu", "Hạng mục"):
        assert any(field.lower().startswith(p) for p in _NON_ITEM_FIELDS), (
            f"{field!r} phải nằm trong danh sách loại khỏi ô Mô tả"
        )
