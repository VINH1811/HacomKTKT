"""So sánh HAI PHIÊN BẢN chào giá của CÙNG MỘT nhà thầu (V1 → V2).

Sau các vòng làm rõ, nhà thầu nộp bản chào giá cập nhật. Chức năng này trả lời
câu hỏi của chuyên viên chấm thầu: "so với bản trước, nhà thầu đã THAY ĐỔI gì?"

- Ghép hạng mục giữa hai phiên bản bằng chính bộ ghép cặp của hệ thống (mã hiệu,
  STT, tên...), nên chịu được việc nhà thầu xáo thứ tự dòng giữa hai bản.
- Báo cáo theo 4 trạng thái: GIỮ NGUYÊN / THAY ĐỔI (kèm từng trường đổi và mức
  chênh) / THÊM MỚI (chỉ có ở bản mới) / ĐÃ XOÁ (chỉ có ở bản cũ).
- Tổng hợp thành tiền hai bản và mức tăng giảm.
- Đối chiếu lỗi tự mâu thuẫn giá bên trong từng bản (cùng hạng mục chào nhiều
  đơn giá): lỗi ở bản cũ ĐÃ SỬA chưa, hay CÒN, hay bản mới MỚI PHÁT SINH thêm.
  Sau vòng làm rõ, đây là câu hỏi chuyên viên cần trả lời trước khi chấm tiếp.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import xlsxwriter

from .config import EnterpriseConfig
from .env_config import env_float
from .excel_reader import load_workbook_items
from .internal_consistency import PriceInconsistency, find_price_inconsistencies
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
STATUS_SUPPLEMENTED = "BỔ SUNG THÔNG TIN"

# Trạng thái của lỗi tự mâu thuẫn giá khi đối chiếu hai phiên bản.
PRICE_ISSUE_FIXED = "ĐÃ SỬA"
PRICE_ISSUE_REMAINS = "CÒN LỖI"
PRICE_ISSUE_NEW = "MỚI PHÁT SINH"

# Hai ban lech qua nguong nay ve tien, trong khi so hang muc chenh khong dang ke
# -> nghi mot ban bi doc thieu.
COUNT_GAP_LIMIT = env_float("HSMT_VERSION_COUNT_GAP", 0.20, 0.0, 1.0)
MONEY_GAP_ALERT = env_float("HSMT_VERSION_MONEY_GAP", 0.40, 0.0, 10.0)


@dataclass
class VersionChange:
    field: str
    old_value: Any
    new_value: Any
    delta: Optional[float] = None
    delta_pct: Optional[float] = None
    # Ban cu bo trong, ban moi dien vao: day la BO SUNG thong tin chu khong phai
    # sua doi. Gop chung se thoi phong con so "hang muc thay doi" — mot ho so
    # that co 1.574 dong chi vi ban moi moi dien cot thuong hieu.
    is_addition: bool = False


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
class PriceIssueRow:
    """Một hạng mục tự mâu thuẫn giá, soi qua cả hai phiên bản."""
    status: str                              # ĐÃ SỬA | CÒN LỖI | MỚI PHÁT SINH
    key_label: str
    matched_by: str
    old: Optional[PriceInconsistency]
    new: Optional[PriceInconsistency]

    @property
    def current(self) -> PriceInconsistency:
        """Bản đang còn lỗi; nếu đã sửa thì lấy bản cũ để biết lỗi từng là gì."""
        issue = self.new or self.old
        assert issue is not None
        return issue


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
    price_issues: list[PriceIssueRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_delta(self) -> float:
        return self.total_new - self.total_old

    def count(self, status: str) -> int:
        return sum(1 for row in self.rows if row.status == status)

    def count_price_issues(self, status: str) -> int:
        return sum(1 for issue in self.price_issues if issue.status == status)

    def by_sheet(self) -> list[dict[str, Any]]:
        """Thống kê theo từng sheet.

        Tổng cả file chỉ nói được "tăng bao nhiêu"; muốn biết tăng ở ĐÂU thì
        phải tách theo sheet — hạng mục điện tăng hay phần nước tăng là hai câu
        chuyện khác nhau khi đàm phán.
        """
        stats: dict[str, dict[str, Any]] = {}
        for row in self.rows:
            entry = stats.setdefault(row.sheet, {
                "sheet": row.sheet, "total_old": 0.0, "total_new": 0.0,
                STATUS_UNCHANGED: 0, STATUS_CHANGED: 0, STATUS_SUPPLEMENTED: 0,
                STATUS_ADDED: 0, STATUS_REMOVED: 0,
            })
            entry[row.status] = entry.get(row.status, 0) + 1
            if row.old is not None:
                entry["total_old"] += _num(row.old.bid_amount) or 0.0
            if row.new is not None:
                entry["total_new"] += _num(row.new.bid_amount) or 0.0
        for entry in stats.values():
            entry["delta"] = entry["total_new"] - entry["total_old"]
            entry["delta_pct"] = (entry["delta"] / entry["total_old"]) if entry["total_old"] else None
        # Sheet biến động nhiều tiền nhất lên đầu.
        return sorted(stats.values(), key=lambda e: -abs(e["delta"]))


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
            changes.append(VersionChange(
                field=label, old_value=old_raw, new_value=new_raw,
                is_addition=not str(old_raw or "").strip() and bool(str(new_raw or "").strip()),
            ))
    return changes


def _total_amount(items: list[ItemRecord]) -> float:
    return sum(_num(item.bid_amount) or 0.0 for item in items if item.is_comparable)


def _issue_key(issue: PriceInconsistency) -> tuple[str, str]:
    """Khóa nhận dạng một lỗi lệch giá xuyên suốt hai phiên bản.

    Dùng nhãn đã chuẩn hóa chứ không dùng số dòng, vì giữa hai bản nhà thầu
    thường chèn/xoá dòng làm số dòng lệch hết.
    """
    return (issue.matched_by, normalize_name(issue.key_label))


def _compare_price_issues(
    old_items: list[ItemRecord],
    new_items: list[ItemRecord],
) -> list[PriceIssueRow]:
    """Đối chiếu lỗi tự mâu thuẫn giá giữa hai phiên bản.

    Trả lời đúng câu hỏi của vòng làm rõ: lỗi cũ đã sửa chưa, và bản mới có
    làm phát sinh lỗi nào không.
    """
    old_map = {_issue_key(i): i for i in find_price_inconsistencies(old_items)}
    new_map = {_issue_key(i): i for i in find_price_inconsistencies(new_items)}

    rows: list[PriceIssueRow] = []
    for key in old_map.keys() | new_map.keys():
        old_issue, new_issue = old_map.get(key), new_map.get(key)
        if new_issue is None:
            status = PRICE_ISSUE_FIXED
        elif old_issue is None:
            status = PRICE_ISSUE_NEW
        else:
            status = PRICE_ISSUE_REMAINS
        source = new_issue or old_issue
        assert source is not None
        rows.append(PriceIssueRow(
            status=status,
            key_label=source.key_label,
            matched_by=source.matched_by,
            old=old_issue,
            new=new_issue,
        ))

    # Việc còn phải xử lý lên trước: mới phát sinh, rồi còn lỗi, rồi đã sửa.
    order = {PRICE_ISSUE_NEW: 0, PRICE_ISSUE_REMAINS: 1, PRICE_ISSUE_FIXED: 2}
    rows.sort(key=lambda r: (order[r.status], -r.current.spread_pct))
    return rows


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
    # match_items CHI ghep cac hang muc so sanh duoc, va chi so trong ket qua
    # tro vao danh sach DA LOC. Tra vao danh sach goc thi lech dung bang so dong
    # nhom/tieu de dung truoc — moi cap ghep deu tro sang hang muc khac, keo theo
    # so sai thuong hieu, sai chenh lech don gia va sai so hang muc thay doi.
    old_items = [item for item in old_wb.items if item.is_comparable]
    new_items = [item for item in new_wb.items if item.is_comparable]

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
            if not changes:
                status = STATUS_UNCHANGED
            elif all(c.is_addition for c in changes):
                # Chi dien them thong tin con thieu, khong sua gi da co.
                status = STATUS_SUPPLEMENTED
            else:
                status = STATUS_CHANGED
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
    # Hai ban co so hang muc tuong duong ma tong tien lech qua lon thi rat co
    # the MOT BAN BI DOC THIEU (sheet doi ten, cot don gia khong nhan ra...),
    # chu khong phai nha thau tang gia. Bao ro con hon dua ra con so ao.
    warnings: list[str] = []
    n_old = len([i for i in old_items if i.is_comparable])
    n_new = len([i for i in new_items if i.is_comparable])
    total_old_value = _total_amount(old_items)
    total_new_value = _total_amount(new_items)
    if n_old and n_new and min(total_old_value, total_new_value) > 0:
        count_gap = abs(n_new - n_old) / max(n_old, n_new)
        money_gap = abs(total_new_value - total_old_value) / max(total_old_value, total_new_value)
        if count_gap <= COUNT_GAP_LIMIT and money_gap >= MONEY_GAP_ALERT:
            thin = old_label if total_old_value < total_new_value else new_label
            warnings.append(
                f"Hai bản có số hạng mục gần bằng nhau ({n_old} và {n_new}) nhưng tổng thành "
                f"tiền lệch {money_gap:.0%}. Rất có thể {thin} bị ĐỌC THIẾU (nhà thầu đổi tên "
                f"sheet, hoặc một sheet không nhận ra cột đơn giá) chứ không phải giá thay đổi "
                f"thật. Xem bảng 'Theo sheet' để biết mất ở đâu."
            )
    warnings.extend(w for w in old_wb.warnings if "không nhận ra cột" in w or "BỎ QUA các sheet" in w)
    warnings.extend(w for w in new_wb.warnings if "không nhận ra cột" in w or "BỎ QUA các sheet" in w)

    return VersionCompareResult(
        bidder=bidder,
        warnings=warnings,
        old_label=old_label,
        new_label=new_label,
        old_path=str(old_path),
        new_path=str(new_path),
        rows=rows,
        total_old=_total_amount(old_items),
        total_new=_total_amount(new_items),
        price_issues=_compare_price_issues(old_items, new_items),
    )


# ---------------------------------------------------------------------------
# Xuất báo cáo Excel
# ---------------------------------------------------------------------------

_STATUS_FILL = {
    STATUS_CHANGED: "#FCE4D6",
    STATUS_ADDED: "#E2EFDA",
    STATUS_REMOVED: "#F4CCCC",
    # Chỉ điền thêm thông tin còn thiếu — nhẹ hơn "thay đổi", tô xanh nhạt.
    STATUS_SUPPLEMENTED: "#DDEBF7",
}

_PRICE_ISSUE_FILL = {
    PRICE_ISSUE_NEW: "#F4CCCC",       # đỏ: nhà thầu vừa làm hỏng thêm
    PRICE_ISSUE_REMAINS: "#FCE4D6",   # cam: đã nhắc mà chưa sửa
    PRICE_ISSUE_FIXED: "#E2EFDA",     # xanh: đã xử lý xong
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
    f_status_issue: dict[str, Any] = {}
    for status, color in _PRICE_ISSUE_FILL.items():
        f_status_issue[status] = wb.add_format({"bold": True, "bg_color": color, "valign": "top"})

    # ---- Sheet Tổng quan ----
    ws = wb.add_worksheet("Tổng quan")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 3, 22)
    ws.merge_range(0, 0, 0, 3, f"SO SÁNH PHIÊN BẢN CHÀO GIÁ — {result.bidder}", f_title)
    ws.set_row(0, 26)
    if result.warnings:
        f_warn = wb.add_format({"bold": True, "bg_color": "#FCE4D6", "font_color": "#9C0006",
                                "text_wrap": True, "valign": "top"})
        ws.write(1, 0, "CẢNH BÁO", f_label)
        row_warn = 1
        for message in result.warnings[:10]:
            ws.merge_range(row_warn, 1, row_warn, 3, message, f_warn)
            ws.set_row(row_warn, 30)
            row_warn += 1

    meta = [
        (result.old_label, Path(result.old_path).name),
        (result.new_label, Path(result.new_path).name),
    ]
    r = 2 + (len(result.warnings[:10]) if result.warnings else 0)
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

    # Tự mâu thuẫn giá bên trong từng bản: đây là thứ chuyên viên cần thấy ngay
    # ở trang đầu, vì nó quyết định có chấp nhận bản chào mới hay phải làm rõ tiếp.
    if result.price_issues:
        r += 1
        ws.write(r, 0, "TỰ MÂU THUẪN ĐƠN GIÁ BÊN TRONG HỒ SƠ", f_label)
        r += 1
        for status in (PRICE_ISSUE_NEW, PRICE_ISSUE_REMAINS, PRICE_ISSUE_FIXED):
            count_ = result.count_price_issues(status)
            if not count_:
                continue
            ws.write(r, 0, f"Số hạng mục {status}", f_status_issue[status])
            ws.write_number(r, 1, count_)
            r += 1
        ws.write(r, 0, "Chi tiết xem sheet 'Lệch đơn giá nội bộ'", f_text)
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

    # ---- Sheet Theo sheet ----
    # Tổng cả file chỉ nói "tăng bao nhiêu"; muốn biết tăng Ở ĐÂU thì phải tách
    # theo sheet. Bảng này cũng làm lộ ngay việc nhà thầu ĐỔI TÊN SHEET giữa hai
    # bản — khi đó một sheet mất trắng còn sheet kia phình lên, dễ bị đọc nhầm
    # thành tăng giá đột biến.
    ws_sheet = wb.add_worksheet("Theo sheet")
    sheet_headers = ["Sheet", f"Tổng {result.old_label}", f"Tổng {result.new_label}",
                     "Chênh lệch", "Chênh (%)", "Giữ nguyên", "Thay đổi",
                     "Bổ sung thông tin", "Thêm mới", "Đã xoá"]
    for col, (head, width) in enumerate(zip(sheet_headers, [30, 20, 20, 18, 11, 11, 11, 17, 11, 10])):
        ws_sheet.set_column(col, col, width)
        ws_sheet.write(0, col, head, f_head)
    ws_sheet.freeze_panes(1, 0)
    ws_sheet.autofilter(0, 0, 0, len(sheet_headers) - 1)
    r = 1
    for entry in result.by_sheet():
        ws_sheet.write(r, 0, entry["sheet"], f_text)
        ws_sheet.write_number(r, 1, entry["total_old"], f_money)
        ws_sheet.write_number(r, 2, entry["total_new"], f_money)
        ws_sheet.write_number(r, 3, entry["delta"], f_money_b)
        if entry["delta_pct"] is not None:
            ws_sheet.write_number(r, 4, entry["delta_pct"], f_pct)
        for col, status in enumerate((STATUS_UNCHANGED, STATUS_CHANGED, STATUS_SUPPLEMENTED,
                                      STATUS_ADDED, STATUS_REMOVED), start=5):
            ws_sheet.write_number(r, col, entry.get(status, 0))
        r += 1
    ws_sheet.write(r + 1, 0, "Lưu ý", f_label)
    ws_sheet.write(r + 1, 1,
                   "Một sheet về 0 và một sheet khác phình lên thường là do nhà thầu ĐỔI TÊN "
                   "sheet giữa hai bản, không phải bỏ hạng mục rồi chào thêm.", f_text)

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

    # ---- Sheet Lệch đơn giá nội bộ ----
    if result.price_issues:
        pw = wb.add_worksheet("Lệch đơn giá nội bộ")
        ph = ["Trạng thái", "Hạng mục", "Ghép theo", "Phạm vi",
              f"Chênh % {result.old_label}", f"Chênh % {result.new_label}",
              "Giá thấp nhất", "Giá cao nhất", "Số lần chào", "Chi tiết dòng"]
        pwidths = [15, 46, 14, 20, 16, 16, 16, 16, 11, 76]
        for col, (head, width) in enumerate(zip(ph, pwidths)):
            pw.set_column(col, col, width)
            pw.write(0, col, head, f_head)
        pw.freeze_panes(1, 0)
        pw.autofilter(0, 0, 0, len(ph) - 1)

        r = 1
        for issue in result.price_issues:
            cur = issue.current
            pw.write(r, 0, issue.status, f_status_issue[issue.status])
            pw.write(r, 1, issue.key_label, f_text)
            pw.write(r, 2, issue.matched_by, f_text)
            pw.write(r, 3, "cùng sheet" if cur.same_sheet
                     else f"{len(cur.sheets)} sheet khác nhau", f_text)
            if issue.old is not None:
                pw.write_number(r, 4, issue.old.spread_pct, f_pct)
            if issue.new is not None:
                pw.write_number(r, 5, issue.new.spread_pct, f_pct)
            pw.write_number(r, 6, cur.min_price, f_money)
            pw.write_number(r, 7, cur.max_price, f_money)
            pw.write_number(r, 8, len(cur.occurrences))
            # Dòng đã sửa thì chỉ ra vị trí Ở BẢN CŨ; các dòng còn lỗi chỉ ra
            # vị trí ở bản mới để chuyên viên mở đúng file đang cần kiểm.
            detail = "; ".join(
                f"{o.sheet}!dòng {o.row_number}: {o.unit_price:,.0f}"
                for o in sorted(cur.occurrences, key=lambda o: (o.sheet, o.row_number))[:8]
            )
            if len(cur.occurrences) > 8:
                detail += f"; ... (+{len(cur.occurrences) - 8} dòng nữa)"
            pw.write(r, 9, detail, f_text)
            r += 1

        r += 1
        pw.write(r, 0, "Ghi chú", f_label)
        pw.write(r, 1,
                 f"'{PRICE_ISSUE_NEW}' và '{PRICE_ISSUE_REMAINS}' đọc theo {result.new_label}; "
                 f"'{PRICE_ISSUE_FIXED}' đọc theo {result.old_label} (bản mới đã hết lỗi này).",
                 f_text)

    wb.close()
    return str(output_path)
