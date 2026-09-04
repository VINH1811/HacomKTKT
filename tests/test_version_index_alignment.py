"""Ghép cặp giữa hai phiên bản phải theo NỘI DUNG, không theo vị trí dòng.

Bộ ghép cặp chỉ làm việc trên các hạng mục so sánh được, và chỉ số trong kết
quả trỏ vào danh sách ĐÃ LỌC. So sánh phiên bản lại tra chỉ số đó vào danh sách
gốc (còn cả dòng nhóm, dòng tiêu đề), nên lệch đúng bằng số dòng nhóm đứng
trước — mọi cặp ghép trỏ sang hạng mục khác.

Hậu quả đúng như phản hồi thực tế: so nhầm thương hiệu, sai chênh lệch đơn giá,
và số hạng mục thay đổi bị thổi phồng.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from core.config import EnterpriseConfig
from core.version_compare import (
    STATUS_CHANGED,
    STATUS_SUPPLEMENTED,
    STATUS_UNCHANGED,
    compare_quote_versions,
)

HDR = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "KL nhà thầu chào",
       "Đơn giá tổng hợp", "Thành tiền", "Thương hiệu"]


def _book(path: Path, rows: list[list]) -> Path:
    wb = Workbook(); ws = wb.active; ws.title = "PCCC"
    ws.append(HDR)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _config() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


# Xen kẽ nhiều dòng NHÓM để chỉ số danh sách gốc lệch hẳn so với danh sách lọc.
def _rows(price_of_valve: int, brand_of_valve: str) -> list[list]:
    return [
        ["A", "", "PHẦN A - HỆ THỐNG BÁO CHÁY", "", None, None, None, ""],
        ["I", "", "Thiết bị đầu vào", "", None, None, None, ""],
        ["1", "DI-M9102", "Đầu báo khói địa chỉ", "cái", 10, 500_000, 5_000_000, "GST"],
        ["2", "DI-M9103", "Đầu báo nhiệt địa chỉ", "cái", 8, 480_000, 3_840_000, "GST"],
        ["B", "", "PHẦN B - HỆ THỐNG CHỮA CHÁY", "", None, None, None, ""],
        ["II", "", "Van và phụ kiện", "", None, None, None, ""],
        ["3", "VG-50", "Van góc chữa cháy DN50", "cái", 4, price_of_valve,
         4 * price_of_valve, brand_of_valve],
        ["4", "ST-100", "Ống thép tráng kẽm DN100", "m", 50, 280_000, 14_000_000, "Hòa Phát"],
    ]


def test_pairs_are_matched_by_content_not_row_position(tmp_path: Path):
    old = _book(tmp_path / "v1.xlsx", _rows(900_000, "Shanxi"))
    new = _book(tmp_path / "v2.xlsx", _rows(950_000, "Shanxi"))
    result = compare_quote_versions(old, new, "NT", config=_config())

    paired = [r for r in result.rows if r.old is not None and r.new is not None]
    assert paired, "Phải ghép được các hạng mục"
    for row in paired:
        assert (row.old.item_name or "").strip() == (row.new.item_name or "").strip(), \
            f"Ghép sai: {row.old.item_name!r} <-> {row.new.item_name!r}"


def test_only_the_changed_item_is_reported(tmp_path: Path):
    old = _book(tmp_path / "v1.xlsx", _rows(900_000, "Shanxi"))
    new = _book(tmp_path / "v2.xlsx", _rows(950_000, "Shanxi"))
    result = compare_quote_versions(old, new, "NT", config=_config())

    changed = [r for r in result.rows if r.status == STATUS_CHANGED]
    assert len(changed) == 1
    assert changed[0].item_name == "Van góc chữa cháy DN50"
    assert result.count(STATUS_UNCHANGED) == 3


def test_brand_is_compared_on_the_same_item(tmp_path: Path):
    old = _book(tmp_path / "v1.xlsx", _rows(900_000, "Shanxi"))
    new = _book(tmp_path / "v2.xlsx", _rows(900_000, "Kidde"))
    result = compare_quote_versions(old, new, "NT", config=_config())

    brand_changes = [(r.item_name, c.old_value, c.new_value)
                     for r in result.rows for c in r.changes if c.field == "Thương hiệu"]
    assert brand_changes == [("Van góc chữa cháy DN50", "Shanxi", "Kidde")]


def test_filling_a_blank_field_is_not_counted_as_a_change(tmp_path: Path):
    # Bản cũ bỏ trống thương hiệu, bản mới điền vào -> BỔ SUNG, không phải sửa.
    old = _book(tmp_path / "v1.xlsx", _rows(900_000, ""))
    new = _book(tmp_path / "v2.xlsx", _rows(900_000, "Shanxi"))
    result = compare_quote_versions(old, new, "NT", config=_config())
    assert result.count(STATUS_SUPPLEMENTED) == 1
    assert result.count(STATUS_CHANGED) == 0


def test_per_sheet_breakdown(tmp_path: Path):
    old = _book(tmp_path / "v1.xlsx", _rows(900_000, "Shanxi"))
    new = _book(tmp_path / "v2.xlsx", _rows(950_000, "Shanxi"))
    stats = compare_quote_versions(old, new, "NT", config=_config()).by_sheet()
    assert len(stats) == 1
    entry = stats[0]
    assert entry["sheet"] == "PCCC"
    assert entry["delta"] == 200_000        # 4 cái × chênh 50.000
    assert entry["delta_pct"] is not None
