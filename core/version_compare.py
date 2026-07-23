"""So sánh HAI PHIÊN BẢN chào giá của CÙNG MỘT nhà thầu (V1 → V2).

Sau các vòng làm rõ, nhà thầu nộp bản chào giá cập nhật. Chức năng này trả lời
câu hỏi của chuyên viên chấm thầu: "so với bản trước, nhà thầu đã THAY ĐỔI gì?"

- Ghép hạng mục giữa hai phiên bản bằng chính bộ ghép cặp của hệ thống (mã hiệu,
  STT, tên...), nên chịu được việc nhà thầu xáo thứ tự dòng giữa hai bản.
- Báo cáo theo 4 trạng thái: GIỮ NGUYÊN / THAY ĐỔI (kèm từng trường đổi và mức
  chênh) / THÊM MỚI (chỉ có ở bản mới) / ĐÃ XOÁ (chỉ có ở bản cũ).
- Tổng hợp thành tiền hai bản và mức tăng giảm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import xlsxwriter

from .config import EnterpriseConfig
from .excel_reader import load_workbook_items
from .matcher import match_items_cached
from .models import DocumentRole, ItemRecord, MatchKind, UserFacingError
from .text_normalizer import normalize_name

# (nhãn hiển thị, thuộc tính ItemRecord, kiểu) — kiểu "num" so bằng dung sai,
# "text" so sau khi chuẩn hóa khoảng trắng/hoa thường, "name" so theo normalize_name.
_TRACKED_FIELDS: list[tuple[str, str, str]] = [
    ("Tên hạng mục", "item_name", "name"),
    ("Đơn vị tính", "unit", "text"),
    ("Mã hiệu", "item_code", "text"),
    ("KL mời thầu (KLMT)", "reference_quantity", "num"),
    ("Khối lượng chào", "bid_quantity", "num"),
    ("Mô tả/Quy cách", "material", "name"),
    ("Thương hiệu", "brand", "text"),
    ("Xuất xứ", "origin", "text"),
    ("VL chính", "price_main", "num"),
    ("VL phụ", "price_aux", "num"),
    ("NC & máy TC", "price_labor", "num"),
    ("Chi phí quản lý", "price_management", "num"),
    ("Lợi nhuận", "price_profit", "num"),
    ("Đơn giá tổng hợp", "unit_price_total", "num"),
    ("Thành tiền", "bid_amount", "num"),
]

STATUS_UNCHANGED = "GIỮ NGUYÊN"
STATUS_CHANGED = "THAY ĐỔI"
STATUS_ADDED = "THÊM MỚI"
STATUS_REMOVED = "ĐÃ XOÁ"


@dataclass
class VersionChange:
    field: str
    old_value: Any
    new_value: Any
    delta: Optional[float] = None
    delta_pct: Optional[float] = None


@dataclass
class VersionRow:
    status: str
    sheet: str
    stt: str
    item_name: str
    unit: str
    old: Optional[ItemRecord]
    new: Optional[ItemRecord]
    changes: list[VersionChange] = field(default_factory=list)


@dataclass
class VersionCompareResult:
    bidder: str
    old_label: str
    new_label: str
    old_path: str
    new_path: str
    rows: list[VersionRow]
    total_old: float
    total_new: float

    @property
    def total_delta(self) -> float:
        return self.total_new - self.total_old

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows if row.status == status)


def _num(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _num_changed(old: Optional[float], new: Optional[float]) -> bool:
    if old is None and new is None:
        return False
    if old is None or new is None:
        # Một bên bỏ trống: chỉ coi là thay đổi khi bên kia khác 0.
        present = old if old is not None else new
        return abs(present) > 1e-9
    return abs(new - old) > max(0.5, abs(old) * 1e-9)


def _text_key(value: Any, kind: str) -> str:
    text = str(value or "").strip()
    if kind == "name":
        return normalize_name(text)
    return " ".join(text.lower().split())


def _diff_items(old: ItemRecord, new: ItemRecord) -> list[VersionChange]:
    changes: list[VersionChange] = []
    for label, attr, kind in _TRACKED_FIELDS:
        old_raw, new_raw = getattr(old, attr, None), getattr(new, attr, None)
        if kind == "num":
            old_num, new_num = _num(old_raw), _num(new_raw)
            if not _num_changed(old_num, new_num):
                continue
            delta = (new_num or 0.0) - (old_num or 0.0)
            base = abs(old_num) if old_num else 0.0
            changes.append(VersionChange(
                field=label,
                old_value=old_num,
                new_value=new_num,
                delta=delta,
                delta_pct=(delta / base) if base else None,
            ))
        else:
            if _text_key(old_raw, kind) == _text_key(new_raw, kind):
                continue
            changes.append(VersionChange(field=label, old_value=old_raw, new_value=new_raw))
    return changes


def _total_amount(items: list[ItemRecord]) -> float:
    return sum(_num(item.bid_amount) or 0.0 for item in items if item.is_comparable)


def compare_quote_versions(
    old_path: str | Path,
    new_path: str | Path,
    bidder: str,
    config: Optional[EnterpriseConfig] = None,
    old_label: str = "Bản cũ (V1)",
    new_label: str = "Bản mới (V2)",
) -> VersionCompareResult:
    """So sánh hai phiên bản chào giá của cùng một nhà thầu."""
    config = config or EnterpriseConfig.from_env()
    old_path, new_path = Path(old_path), Path(new_path)

    old_wb = load_workbook_items(old_path, DocumentRole.HSDT, bidder=bidder)
    new_wb = load_workbook_items(new_path, DocumentRole.HSDT, bidder=bidder)
    for wb, label in ((old_wb, old_label), (new_wb, new_label)):
        if not any(item.is_comparable for item in wb.items):
            raise UserFacingError(
                f"Không đọc được hạng mục nào từ {label} ('{Path(wb.path).name}'). "
                "File có thể không chứa bảng khối lượng (BOQ)."
            )

    matches = match_items_cached(old_wb, new_wb, config)
    old_items, new_items = old_wb.items, new_wb.items

    rows: list[VersionRow] = []
    for match in matches:
        old_item = old_items[match.reference_index] if match.reference_index is not None else None
        new_item = new_items[match.candidate_index] if match.candidate_index is not None else None
        shown = new_item or old_item
        if shown is None or not shown.is_comparable:
            continue
        if match.kind is MatchKind.MISSING or new_item is None:
            status, changes = STATUS_REMOVED, []
        elif match.kind is MatchKind.EXTRA or old_item is None:
            status, changes = STATUS_ADDED, []
        else:
            changes = _diff_items(old_item, new_item)
            status = STATUS_CHANGED if changes else STATUS_UNCHANGED
        rows.append(VersionRow(
            status=status,
            sheet=shown.sheet,
            stt=shown.stt or "",
            item_name=shown.item_name or "",
            unit=shown.unit or "",
            old=old_item,
            new=new_item,
            changes=changes,
        ))

    # Giữ thứ tự tài liệu của BẢN MỚI; dòng đã xoá xếp theo vị trí bản cũ ở cuối sheet.
    rows.sort(key=lambda r: (
        r.sheet,
        0 if r.new is not None else 1,
        (r.new or r.old).row_number,
    ))
    return VersionCompareResult(
        bidder=bidder,
        old_label=old_label,
        new_label=new_label,
        old_path=str(old_path),
        new_path=str(new_path),
        rows=rows,
        total_old=_total_amount(old_items),
        total_new=_total_amount(new_items),
    )


# ---------------------------------------------------------------------------
# Xuất báo cáo Excel
# ---------------------------------------------------------------------------

_STATUS_FILL = {
    STATUS_CHANGED: "#FCE4D6",
    STATUS_ADDED: "#E2EFDA",
    STATUS_REMOVED: "#F4CCCC",
}


def export_version_report(result: VersionCompareResult, output_path: str | Path) -> str:
    """Xuất báo cáo so sánh phiên bản: sheet Tổng quan + sheet Thay đổi chi tiết."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(str(output_path), {"nan_inf_to_errors": True})

    f_title = wb.add_format({"bold": True, "font_size": 14, "font_color": "#FFFFFF", "bg_color": "#17365D", "align": "center", "valign": "vcenter"})
    f_head = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1})
    f_label = wb.add_format({"bold": True})
    f_money = wb.add_format({"num_format": "#,##0"})
    f_money_b = wb.add_format({"num_format": "#,##0", "bold": True})
    f_pct = wb.add_format({"num_format": "+0.00%;-0.00%"})
    f_text = wb.add_format({"valign": "top", "text_wrap": True})
    f_num = wb.add_format({"num_format": "#,##0.###", "valign": "top"})
    f_status: dict[str, Any] = {}
    for status, color in _STATUS_FILL.items():
        f_status[status] = wb.add_format({"bold": True, "bg_color": color, "valign": "top"})

    # ---- Sheet Tổng quan ----
    ws = wb.add_worksheet("Tổng quan")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 3, 22)
    ws.merge_range(0, 0, 0, 3, f"SO SÁNH PHIÊN BẢN CHÀO GIÁ — {result.bidder}", f_title)
    ws.set_row(0, 26)
    meta = [
        (result.old_label, Path(result.old_path).name),
        (result.new_label, Path(result.new_path).name),
    ]
    r = 2
    for label, value in meta:
        ws.write(r, 0, label, f_label)
        ws.write(r, 1, value)
        r += 1
    r += 1
    ws.write(r, 0, "Tổng thành tiền " + result.old_label, f_label)
    ws.write_number(r, 1, result.total_old, f_money)
    r += 1
    ws.write(r, 0, "Tổng thành tiền " + result.new_label, f_label)
    ws.write_number(r, 1, result.total_new, f_money)
    r += 1
    ws.write(r, 0, "Chênh lệch (mới - cũ)", f_label)
    ws.write_number(r, 1, result.total_delta, f_money_b)
    if result.total_old:
        ws.write_number(r, 2, result.total_delta / result.total_old, f_pct)
    r += 2
    for status in (STATUS_CHANGED, STATUS_ADDED, STATUS_REMOVED, STATUS_UNCHANGED):
        ws.write(r, 0, f"Số hạng mục {status}", f_label)
        ws.write_number(r, 1, result.count(status))
        r += 1

    # Hồ sơ thay đổi theo trường — cho biết ngay thay đổi thuộc loại nào
    # (ví dụ KLMT đổi hàng loạt = CĐT sửa khối lượng mời thầu lần 2).
    field_counts: dict[str, int] = {}
    for row_ in result.rows:
        for change in row_.changes:
            field_counts[change.field] = field_counts.get(change.field, 0) + 1
    if field_counts:
        r += 1
        ws.write(r, 0, "SỐ LẦN THAY ĐỔI THEO TRƯỜNG", f_label)
        r += 1
        for field_name, count_ in sorted(field_counts.items(), key=lambda kv: -kv[1]):
            ws.write(r, 0, field_name)
            ws.write_number(r, 1, count_)
            r += 1

    # Top thay đổi thành tiền lớn nhất
    money_changes: list[tuple[float, VersionRow, VersionChange]] = []
    for row in result.rows:
        for change in row.changes:
            if change.field == "Thành tiền" and change.delta is not None:
                money_changes.append((abs(change.delta), row, change))
    money_changes.sort(key=lambda x: -x[0])
    if money_changes:
        r += 1
        ws.write(r, 0, "TOP THAY ĐỔI THÀNH TIỀN LỚN NHẤT", f_label)
        r += 1
        for col, head in enumerate(["Hạng mục", "Cũ", "Mới", "Chênh lệch"]):
            ws.write(r, col, head, f_head)
        r += 1
        for _, row, change in money_changes[:15]:
            ws.write(r, 0, f"[{row.sheet}] {row.item_name[:80]}", f_text)
            ws.write_number(r, 1, change.old_value or 0.0, f_money)
            ws.write_number(r, 2, change.new_value or 0.0, f_money)
            ws.write_number(r, 3, change.delta or 0.0, f_money_b)
            r += 1

    # ---- Sheet Thay đổi chi tiết ----
    det = wb.add_worksheet("Thay đổi chi tiết")
    headers = ["Trạng thái", "Sheet", "STT", "Hạng mục", "ĐVT", "Trường thay đổi",
               result.old_label, result.new_label, "Chênh lệch", "Chênh (%)"]
    widths = [13, 16, 8, 52, 8, 20, 22, 22, 16, 10]
    for col, (head, width) in enumerate(zip(headers, widths)):
        det.set_column(col, col, width)
        det.write(0, col, head, f_head)
    det.freeze_panes(1, 0)
    det.autofilter(0, 0, 0, len(headers) - 1)

    r = 1
    for row in result.rows:
        if row.status == STATUS_UNCHANGED:
            continue
        base = [row.status, row.sheet, row.stt, row.item_name, row.unit]
        if row.status in (STATUS_ADDED, STATUS_REMOVED):
            item = row.new or row.old
            det.write(r, 0, row.status, f_status[row.status])
            for col, value in enumerate(base[1:], 1):
                det.write(r, col, value, f_text)
            det.write(r, 5, "Thành tiền", f_text)
            amount = _num(item.bid_amount) if item else None
            if row.status == STATUS_REMOVED and amount is not None:
                det.write_number(r, 6, amount, f_num)
                det.write_number(r, 8, -amount, f_num)
            elif amount is not None:
                det.write_number(r, 7, amount, f_num)
                det.write_number(r, 8, amount, f_num)
            r += 1
            continue
        for change in row.changes:
            det.write(r, 0, row.status, f_status[row.status])
            for col, value in enumerate(base[1:], 1):
                det.write(r, col, value, f_text)
            det.write(r, 5, change.field, f_text)
            if isinstance(change.old_value, (int, float)) or isinstance(change.new_value, (int, float)):
                if change.old_value is not None:
                    det.write_number(r, 6, float(change.old_value), f_num)
                if change.new_value is not None:
                    det.write_number(r, 7, float(change.new_value), f_num)
                if change.delta is not None:
                    det.write_number(r, 8, change.delta, f_num)
                if change.delta_pct is not None:
                    det.write_number(r, 9, change.delta_pct, f_pct)
            else:
                det.write(r, 6, str(change.old_value or ""), f_text)
                det.write(r, 7, str(change.new_value or ""), f_text)
            r += 1

    wb.close()
    return str(output_path)
