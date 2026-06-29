from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Iterator, Sequence

import xlsxwriter

from .models import ComparisonResult, ComparedItem, MatchKind, RowType, Severity

EXCEL_MAX_ROWS = 1_048_576


def _safe_text(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _write(ws, row: int, col: int, value: Any, fmt=None) -> None:
    value = _safe_text(value)
    if value is None:
        ws.write_blank(row, col, None, fmt)
    elif isinstance(value, bool):
        ws.write_boolean(row, col, value, fmt)
    elif isinstance(value, (int, float)):
        ws.write_number(row, col, float(value), fmt)
    else:
        ws.write(row, col, value, fmt)


def _formats(wb):
    return {
        "title": wb.add_format({"bold": True, "font_name": "Arial", "font_size": 18, "font_color": "#FFFFFF", "bg_color": "#17365D", "align": "center", "valign": "vcenter"}),
        "section": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#FFFFFF", "bg_color": "#2F75B5", "align": "left"}),
        "header": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "center", "valign": "vcenter", "text_wrap": True, "bottom": 1}),
        "text": wb.add_format({"font_name": "Arial", "valign": "top"}),
        "long": wb.add_format({"font_name": "Arial", "valign": "top", "text_wrap": True}),
        "num": wb.add_format({"font_name": "Arial", "num_format": "#,##0.000;[Red]-#,##0.000", "valign": "top"}),
        "money": wb.add_format({"font_name": "Arial", "num_format": "#,##0;[Red]-#,##0", "valign": "top"}),
        "pct": wb.add_format({"font_name": "Arial", "num_format": "0.00%;[Red]-0.00%", "valign": "top"}),
        "score": wb.add_format({"font_name": "Arial", "num_format": "0.0", "valign": "top"}),
        "label": wb.add_format({"bold": True, "font_name": "Arial", "bg_color": "#D9EAF7", "bottom": 1}),
        "value": wb.add_format({"font_name": "Arial", "bottom": 1, "bottom_color": "#E7E6E6"}),
        "ok": wb.add_format({"font_name": "Arial", "bg_color": "#E2F0D9", "font_color": "#375623"}),
        "info": wb.add_format({"font_name": "Arial", "bg_color": "#DDEBF7", "font_color": "#1F4E78"}),
        "review": wb.add_format({"font_name": "Arial", "bg_color": "#FFF2CC", "font_color": "#7F6000"}),
        "warning": wb.add_format({"font_name": "Arial", "bg_color": "#FCE4D6", "font_color": "#C65911"}),
        "critical": wb.add_format({"font_name": "Arial", "bg_color": "#F4CCCC", "font_color": "#9C0006", "bold": True}),
        "mono": wb.add_format({"font_name": "Consolas", "font_size": 9, "text_wrap": True, "valign": "top"}),
        # Tiền tệ kèm nền cảnh báo — dùng cho ô giá lệch nhiều trong sheet tổng hợp.
        "money_warn": wb.add_format({"font_name": "Arial", "num_format": "#,##0;[Red]-#,##0", "valign": "top", "bg_color": "#FCE4D6", "font_color": "#C65911"}),
        "money_crit": wb.add_format({"font_name": "Arial", "num_format": "#,##0;[Red]-#,##0", "valign": "top", "bg_color": "#F4CCCC", "font_color": "#9C0006", "bold": True}),
        # Tiêu đề nhiều tầng cho bảng tổng hợp chào giá (block từng nhà thầu).
        "grp_klmt": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#FFFFFF", "bg_color": "#7F7F7F", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1}),
        "grp_bidder": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#FFFFFF", "bg_color": "#2E75B6", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1}),
        "grp_sub": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#1F3864", "bg_color": "#DDEBF7", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1}),
        "leaf": wb.add_format({"bold": True, "font_name": "Arial", "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "center", "valign": "vcenter", "text_wrap": True, "border": 1}),
    }


_SEVERITY_STYLE = {
    Severity.OK.value: "ok", Severity.INFO.value: "info", Severity.REVIEW.value: "review",
    Severity.WARNING.value: "warning", Severity.CRITICAL.value: "critical",
}


def export_comparison_report(result: ComparisonResult, output_path: str | Path) -> str:
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(output_path, {
        "constant_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
        "nan_inf_to_errors": True,
    })
    wb.set_properties({
        "title": "Báo cáo so sánh HSDT và phát hiện bất thường",
        "author": "HSMT Enterprise AI — local-only",
        "comments": "Tín hiệu hỗ trợ rà soát; cần kiểm tra hồ sơ gốc trước khi kết luận.",
    })
    f = _formats(wb)
    try:
        _summary(wb, result, f)
        _comparison_sheet(wb, result, f, False)
        _comparison_sheet(wb, result, f, True)
        _matrix(wb, result, f, "price", "Ma trận đơn giá")
        _matrix(wb, result, f, "quantity", "Ma trận khối lượng")
        _differences(wb, result, f)
        _unmatched(wb, result, f)
        _quality(wb, result, f)
        _pl2_requirements(wb, result, f)
        _audit(wb, result, f)
    finally:
        wb.close()
    return output_path


def _summary(wb, result: ComparisonResult, f) -> None:
    ws = wb.add_worksheet("Tổng quan")
    ws.set_tab_color("#2F75B5")
    ws.set_column("A:A", 31); ws.set_column("B:B", 28); ws.set_column("D:D", 32); ws.set_column("E:E", 24)
    package_mode = str(result.audit.get("mode", "")).startswith("PL01_PL02")
    title = "BÁO CÁO ĐỐI CHIẾU PL01, PL02 VÀ SO SÁNH NGANG HÀNG NHÀ THẦU" if package_mode else "BÁO CÁO SO SÁNH HỒ SƠ DỰ THẦU"
    ws.merge_range("A1:E2", title, f["title"])
    s = result.summary
    metrics = [
        (("Nguồn khối lượng chính thức" if package_mode else "Hồ sơ baseline"), s.reference_name), ("Số hồ sơ nhà thầu", s.bidder_count),
        ("Hạng mục chuẩn", s.total_reference_items), ("Dòng đối chiếu", s.total_rows),
        ("Khớp cấu trúc/chính xác", s.exact_matches), ("Khớp fuzzy/model", s.fuzzy_matches),
        ("Thiếu hạng mục", s.missing_items), ("Hạng mục phát sinh", s.extra_items),
        ("Dòng cần kiểm tra", s.review_rows), ("Dòng cảnh báo", s.warning_rows),
        ("Dòng bất thường", s.critical_rows), (("Tổng giá nguồn chuẩn" if not package_mode else "Tổng giá PL01 (nếu có)"), s.total_reference_amount),
        ("Thời điểm tạo", s.generated_at),
    ]
    for row, (label, value) in enumerate(metrics, 3):
        _write(ws, row, 0, label, f["label"])
        _write(ws, row, 1, value, f["money"] if "tổng giá" in label.lower() else f["value"])
    _write(ws, 3, 3, "Tổng giá hồ sơ đối chiếu", f["section"]); _write(ws, 3, 4, "Giá trị", f["section"])
    for row, (bidder, total) in enumerate(sorted(s.bidder_totals.items()), 4):
        _write(ws, row, 3, bidder, f["text"]); _write(ws, row, 4, total, f["money"])
    row = max(18, 5 + len(s.bidder_totals))
    ws.merge_range(row, 0, row, 4, "CÁCH ĐỌC MÀU", f["section"]); row += 1
    for color, meaning, style in [
        ("Xanh", "Khớp trong ngưỡng", "ok"), ("Vàng", "Cần chuyên viên xác nhận", "review"),
        ("Cam", "Sai lệch đáng kể", "warning"), ("Đỏ", "Thiếu/phát sinh hoặc sai lệch nghiêm trọng", "critical"),
    ]:
        _write(ws, row, 0, color, f[style]); ws.merge_range(row, 1, row, 4, meaning, f["text"]); row += 1
    if package_mode:
        row += 1
        ws.merge_range(row, 0, row, 4, "NGUYÊN TẮC SO SÁNH", f["section"]); row += 1
        ws.merge_range(row, 0, row, 4, "Phụ lục 01 là nguồn danh mục/khối lượng; Phụ lục 02 là nguồn yêu cầu vật tư. Các nhà thầu được so sánh ngang hàng, không nhà thầu nào làm chuẩn. File gốc của từng nhà thầu được xuất lại dưới dạng bản sao đã tô màu và ghi lý do.", f["long"]); row += 1
    if result.warnings:
        row += 1; ws.merge_range(row, 0, row, 4, "CẢNH BÁO ĐỌC FILE", f["section"]); row += 1
        for warning in result.warnings[:200]:
            ws.merge_range(row, 0, row, 4, _safe_text(warning), f["review"]); row += 1
    ws.freeze_panes(3, 0)


_DETAIL_HEADERS = [
    "Mức độ", "Điểm bất thường", "Nhà thầu", "Loại dòng",
    "Sheet chuẩn", "Dòng chuẩn", "STT chuẩn", "Mã hiệu chuẩn", "Tên hạng mục chuẩn", "ĐVT chuẩn",
    "KL chuẩn", "Đơn giá chuẩn", "Thành tiền chuẩn",
    "Sheet đối chiếu", "Dòng đối chiếu", "STT đối chiếu", "Mã hiệu đối chiếu", "Tên hạng mục đối chiếu", "ĐVT đối chiếu",
    "KL đối chiếu", "Đơn giá đối chiếu", "Thành tiền đối chiếu",
    "Nhóm vật tư PL02", "Yêu cầu PL02", "Trạng thái PL02", "Điểm ghép PL02",
    "Lệch KL (%)", "Lệch đơn giá (%)", "Lệch thành tiền", "Kiểu khớp", "Điểm khớp", "Robust Z", "Cờ đánh giá", "Ghi chú",
]


def _compact(row: ComparedItem) -> dict[str, Any]:
    r, c = row.reference, row.candidate
    item = r or c
    return {
        "Mức độ": row.severity.value, "Điểm bất thường": row.anomaly_score, "Nhà thầu": row.bidder,
        "Loại dòng": item.row_type.value if item else "",
        "Sheet chuẩn": r.sheet if r else "", "Dòng chuẩn": r.row_number if r else None,
        "STT chuẩn": r.stt if r else "", "Mã hiệu chuẩn": r.item_code if r else "",
        "Tên hạng mục chuẩn": r.item_name if r else "", "ĐVT chuẩn": r.unit if r else "",
        "KL chuẩn": r.quantity if r else None, "Đơn giá chuẩn": r.unit_price_total if r else None,
        "Thành tiền chuẩn": r.amount if r else None,
        "Sheet đối chiếu": c.sheet if c else "", "Dòng đối chiếu": c.row_number if c else None,
        "STT đối chiếu": c.stt if c else "", "Mã hiệu đối chiếu": c.item_code if c else "",
        "Tên hạng mục đối chiếu": c.item_name if c else "", "ĐVT đối chiếu": c.unit if c else "",
        "KL đối chiếu": c.quantity if c else None, "Đơn giá đối chiếu": c.unit_price_total if c else None,
        "Thành tiền đối chiếu": c.amount if c else None,
        "Nhóm vật tư PL02": row.pl2_category, "Yêu cầu PL02": row.pl2_requirement,
        "Trạng thái PL02": row.pl2_status, "Điểm ghép PL02": row.pl2_match_score,
        "Lệch KL (%)": row.quantity_delta_pct, "Lệch đơn giá (%)": row.price_delta_pct,
        "Lệch thành tiền": row.amount_delta, "Kiểu khớp": row.match.kind.value,
        "Điểm khớp": row.match.score, "Robust Z": row.robust_z, "Cờ đánh giá": " | ".join(row.flags),
        "Ghi chú": " | ".join(row.notes),
    }


def _comparison_sheet(wb, result: ComparisonResult, f, anomalies_only: bool) -> None:
    rows = (_compact(row) for row in result.rows if not anomalies_only or row.severity is not Severity.OK)
    count = sum(1 for row in result.rows if not anomalies_only or row.severity is not Severity.OK)
    _stream(wb, "Bất thường" if anomalies_only else "So sánh chi tiết", rows, _DETAIL_HEADERS, count, f, "#C00000" if anomalies_only else "#4472C4")


def _deviation_comment(bidder_name: str, value: float, med: float, delta_pct: float, critical: bool) -> str:
    """Ghi chú đơn giản đính kèm trực tiếp vào ô giá/khối lượng bị lệch.

    Hiển thị khi người dùng rê chuột vào ô trong Excel — không chiếm thêm cột.
    """
    direction = "cao hơn" if delta_pct > 0 else "thấp hơn"
    severity_word = "RẤT NHIỀU" if critical else "khá nhiều"
    return (
        f"{bidder_name} {direction} mặt bằng chung của các nhà thầu {severity_word}.\n"
        f"Giá trị này: {value:,.0f}\n"
        f"Trung vị các nhà thầu: {med:,.0f}\n"
        f"Mức lệch: {delta_pct:+.0%} so với trung vị."
    )


def _matrix(wb, result: ComparisonResult, f, field: str, sheet_name: str) -> None:
    ws = wb.add_worksheet(sheet_name)
    ws.set_tab_color("#70AD47" if field == "price" else "#5B9BD5")
    package_mode = str(result.audit.get("mode", "")).startswith("PL01_PL02")
    bidders = list((result.audit.get("bidder_sha256") or {}).keys())
    baseline = result.audit.get("baseline_bidder") or result.summary.reference_name
    columns = list(bidders)
    if not package_mode:
        if baseline not in columns:
            columns.insert(0, baseline)
    elif field == "quantity":
        columns.insert(0, "PL01 - KLMT")

    thresholds = result.audit.get("thresholds") or {}
    warn_pct = float(thresholds.get(f"{field}_warn_pct", 0.10 if field == "price" else 0.05))
    critical_pct = float(thresholds.get(f"{field}_critical_pct", 0.25 if field == "price" else 0.15))
    # Cột PL01-KLMT không phải một nhà thầu nên không tham gia tính chênh lệch.
    skip_baseline_col = package_mode and field == "quantity"

    grouped: dict[str, dict[str, Any]] = defaultdict(dict)
    meta: dict[str, tuple[str, str, str, str]] = {}
    for row in result.rows:
        item = row.reference or row.candidate
        if not item or item.row_type is not RowType.DETAIL:
            continue
        meta[row.canonical_id] = (item.sheet, item.stt, item.item_name, item.unit)
        if package_mode:
            if field == "quantity" and row.reference and "PL01 - KLMT" not in grouped[row.canonical_id]:
                grouped[row.canonical_id]["PL01 - KLMT"] = row.reference.reference_quantity
            if row.candidate:
                grouped[row.canonical_id][row.bidder] = row.candidate.unit_price_total if field == "price" else row.candidate.bid_quantity
        else:
            if row.reference:
                grouped[row.canonical_id][baseline] = row.reference.unit_price_total if field == "price" else row.reference.quantity
            if row.candidate:
                grouped[row.canonical_id][row.bidder] = row.candidate.unit_price_total if field == "price" else row.candidate.quantity

    headers = ["Mã chuẩn", "Sheet", "STT", "Tên hạng mục", "ĐVT"] + columns + ["Thấp nhất", "Trung vị", "Cao nhất", "Chênh đối xứng %"]
    bidder_start_col = 5
    _header(ws, headers, f); ws.freeze_panes(1, 5)
    ws.set_column(0, 0, 24); ws.set_column(1, 2, 18); ws.set_column(3, 3, 48); ws.set_column(4, len(headers)-1, 17)
    for r_idx, cid in enumerate(sorted(grouped), 1):
        sheet, stt, name, unit = meta[cid]
        vals = [grouped[cid].get(bidder) for bidder in columns]
        # Official PL01 quantity is not a bidder observation when calculating peer spread.
        peer_vals = vals[1:] if package_mode and field == "quantity" else vals
        valid = [v for v in peer_vals if isinstance(v, (int, float))]
        mn = min(valid) if valid else None; mx = max(valid) if valid else None; med = median(valid) if valid else None
        denom = ((abs(mx) + abs(mn)) / 2) if mn is not None and mx is not None else 0
        spread = abs(mx - mn) / denom if denom else (0.0 if mn == mx and mn is not None else None)

        # Mỗi ô giá/khối lượng lệch nhiều so với trung vị các nhà thầu được tô
        # màu VÀ gắn ghi chú (comment) ngay trên chính ô đó — không dùng cột riêng.
        cell_comments: dict[int, tuple[str, str]] = {}
        for col_idx, (bidder_name, value) in enumerate(zip(columns, vals)):
            if skip_baseline_col and col_idx == 0:
                continue
            if not isinstance(value, (int, float)) or med is None or med == 0:
                continue
            delta_pct = (value - med) / abs(med)
            if abs(delta_pct) >= critical_pct:
                cell_comments[col_idx] = ("critical", _deviation_comment(bidder_name, value, med, delta_pct, True))
            elif abs(delta_pct) >= warn_pct:
                cell_comments[col_idx] = ("warning", _deviation_comment(bidder_name, value, med, delta_pct, False))

        record = [cid, sheet, stt, name, unit] + vals + [mn, med, mx, spread]
        for col, value in enumerate(record):
            bidder_col_idx = col - bidder_start_col
            if col == 3:
                style = f["long"]
            elif col < bidder_start_col:
                style = f["text"]
            elif headers[col] == "Chênh đối xứng %":
                style = f["pct"]
            elif bidder_start_col <= col < bidder_start_col + len(columns) and bidder_col_idx in cell_comments:
                style = f[cell_comments[bidder_col_idx][0]]
            else:
                style = f["money"] if field == "price" else f["num"]
            _write(ws, r_idx, col, value, style)
            if bidder_start_col <= col < bidder_start_col + len(columns) and bidder_col_idx in cell_comments:
                ws.write_comment(r_idx, col, cell_comments[bidder_col_idx][1], {"author": "HSMT Enterprise AI", "width": 260, "height": 90})
    if grouped:
        ws.autofilter(0, 0, len(grouped), len(headers)-1)
        col = headers.index("Chênh đối xứng %")
        ws.conditional_format(1, col, len(grouped), col, {"type":"3_color_scale","min_color":"#63BE7B","mid_color":"#FFEB84","max_color":"#F8696B"})


# --- Sheet "Tổng hợp chào giá" (các nhà thầu xếp cạnh nhau theo block) --------
# Mỗi nhà thầu là một block 14 cột, mô phỏng đúng format bảng chào giá tổng hợp.
# Ô "ĐG tổng hợp" và "Thành tiền NT chào" lệch nhiều so với mặt bằng các nhà
# thầu sẽ được tô màu + gắn ghi chú trực tiếp lên chính ô đó.
_BLOCK_LEAVES = [
    ("KL\nNT chào", "num"),
    ("Mô tả/ Quy cách", "long"),
    ("Mã hiệu", "text"),
    ("Thương hiệu", "text"),
    ("Xuất xứ", "text"),
    ("VL chính", "money"),
    ("VL phụ", "money"),
    ("NC&M", "money"),
    ("CF quản lý", "money"),
    ("Lợi nhuận", "money"),
    ("ĐG tổng hợp", "money"),
    ("Thành tiền\nKLMT", "money"),
    ("Thành tiền\nNT chào", "money"),
    ("Ghi chú", "long"),
]
_BLOCK_GROUPS = [
    (None, 0, 0),
    ("THÔNG TIN VỀ VẬT LIỆU CHÍNH", 1, 4),
    ("ĐƠN GIÁ (chưa gồm VAT)", 5, 10),
    ("THÀNH TIỀN", 11, 12),
    (None, 13, 13),
]
_BLOCK_WIDTHS = [10, 30, 14, 16, 13, 14, 14, 14, 14, 14, 16, 18, 18, 26]
_BRAND_IDX = 3
_ORIGIN_IDX = 4
_UNIT_PRICE_IDX = 10
_BID_AMOUNT_IDX = 12
_KLMT_LEAVES = ["STT", "Mã hiệu", "Diễn giải", "ĐVT", "KL\nMời thầu"]
_KLMT_WIDTHS = [6, 16, 46, 9, 13]
_KLMT_COLS = len(_KLMT_LEAVES)
_BLOCK_COLS = len(_BLOCK_LEAVES)


def _build_quote_groups(result: ComparisonResult) -> tuple[dict[str, dict[str, Any]], dict[str, tuple]]:
    """Gom các dòng so sánh theo từng hạng mục (canonical_id).

    Mỗi nhóm giữ lại bản tham chiếu (PL01/đồng thuận) và bản chào của từng nhà
    thầu, kèm metadata để dựng khối KLMT bên trái.
    """
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"ref": None, "bidders": {}, "pl2": {}})
    meta: dict[str, tuple] = {}
    for row in result.rows:
        item = row.reference or row.candidate
        if not item or item.row_type is not RowType.DETAIL:
            continue
        cid = row.canonical_id
        if row.reference is not None and grouped[cid]["ref"] is None:
            grouped[cid]["ref"] = row.reference
        if row.candidate is not None:
            grouped[cid]["bidders"][row.bidder] = row.candidate
            # Thu thập vi phạm Phụ lục 02 (thương hiệu/xuất xứ) của từng nhà thầu
            # để đánh dấu trực tiếp lên ô tương ứng trong bảng tổng hợp.
            pl2_issues: dict[str, tuple[str, bool]] = {}
            for diff in row.differences:
                field = str(diff.field)
                if not field.startswith("Phụ lục 02"):
                    continue
                key = "brand" if "Thương hiệu" in field else ("origin" if "Xuất xứ" in field else "")
                if key:
                    is_critical = str(diff.message).startswith("Thiếu")
                    pl2_issues[key] = (str(diff.message), is_critical)
            if pl2_issues:
                grouped[cid]["pl2"][row.bidder] = pl2_issues
        if cid not in meta:
            ref = row.reference
            anchor = ref or row.candidate
            meta[cid] = (anchor.sheet, anchor.row_number, anchor.stt,
                         (ref.item_code if ref else anchor.item_code),
                         (ref.item_name if ref else anchor.item_name),
                         (ref.unit if ref else anchor.unit),
                         (ref.reference_quantity if ref else None))
    return grouped, meta


def _write_quote_header(ws, f, bidders: list[str], title: str) -> None:
    """Dựng tiêu đề 3 tầng đúng format bảng chào giá tổng hợp.

    constant_memory yêu cầu ghi theo thứ tự dòng tăng dần, nên chỉ merge ngang
    trong từng dòng (không merge dọc).
    """
    total_cols = _KLMT_COLS + _BLOCK_COLS * len(bidders)
    for idx in range(_KLMT_COLS):
        ws.set_column(idx, idx, _KLMT_WIDTHS[idx])
    for b_idx in range(len(bidders)):
        base = _KLMT_COLS + b_idx * _BLOCK_COLS
        for j, width in enumerate(_BLOCK_WIDTHS):
            ws.set_column(base + j, base + j, width)

    ws.merge_range(0, 0, 0, total_cols - 1, title, f["title"])
    ws.set_row(0, 28)

    ws.merge_range(1, 0, 1, _KLMT_COLS - 1, "KHỐI LƯỢNG MỜI THẦU", f["grp_klmt"])
    for b_idx, bidder in enumerate(bidders):
        base = _KLMT_COLS + b_idx * _BLOCK_COLS
        ws.merge_range(1, base, 1, base + _BLOCK_COLS - 1, f"NHÀ THẦU: {bidder}", f["grp_bidder"])
    ws.set_row(1, 26)

    for idx in range(_KLMT_COLS):
        ws.write_blank(2, idx, None, f["grp_klmt"])
    for b_idx in range(len(bidders)):
        base = _KLMT_COLS + b_idx * _BLOCK_COLS
        for label, start, end in _BLOCK_GROUPS:
            if label is None:
                ws.write_blank(2, base + start, None, f["grp_sub"])
            elif start == end:
                ws.write(2, base + start, label, f["grp_sub"])
            else:
                ws.merge_range(2, base + start, 2, base + end, label, f["grp_sub"])
    ws.set_row(2, 22)

    for idx, name in enumerate(_KLMT_LEAVES):
        ws.write(3, idx, name, f["leaf"])
    for b_idx in range(len(bidders)):
        base = _KLMT_COLS + b_idx * _BLOCK_COLS
        for j, (name, _kind) in enumerate(_BLOCK_LEAVES):
            ws.write(3, base + j, name, f["leaf"])
    ws.set_row(3, 30)
    ws.freeze_panes(4, _KLMT_COLS)


def _write_quote_row(ws, f, r: int, bidders: list[str], cid: str,
                     grouped: dict, meta: dict, warn_pct: float, critical_pct: float) -> None:
    """Ghi một dòng hạng mục: khối KLMT + block từng nhà thầu, đánh dấu ô lệch."""
    _sheet, _row, stt, code, name, unit, ref_qty = meta[cid]
    for col, value in enumerate([stt, code, name, unit, ref_qty]):
        style = f["long"] if col == 2 else (f["num"] if col == 4 else f["text"])
        _write(ws, r, col, value, style)

    bidder_cands = grouped[cid]["bidders"]
    prices = [c.unit_price_total for c in bidder_cands.values() if isinstance(c.unit_price_total, (int, float))]
    amounts = [c.bid_amount for c in bidder_cands.values() if isinstance(c.bid_amount, (int, float))]
    price_med = median(prices) if len(prices) >= 2 else None
    amount_med = median(amounts) if len(amounts) >= 2 else None

    for b_idx, bidder in enumerate(bidders):
        base = _KLMT_COLS + b_idx * _BLOCK_COLS
        cand = bidder_cands.get(bidder)
        leaf_values = [
            cand.bid_quantity if cand else None,
            cand.material if cand else "",
            cand.item_code if cand else "",
            cand.brand if cand else "",
            cand.origin if cand else "",
            cand.price_main if cand else None,
            cand.price_aux if cand else None,
            cand.price_labor if cand else None,
            cand.price_management if cand else None,
            cand.price_profit if cand else None,
            cand.unit_price_total if cand else None,
            cand.reference_amount if cand else None,
            cand.bid_amount if cand else None,
            cand.note if cand else "",
        ]
        comments: dict[int, str] = {}
        styles: dict[int, str] = {}
        for leaf_idx, med, value in (
            (_UNIT_PRICE_IDX, price_med, leaf_values[_UNIT_PRICE_IDX]),
            (_BID_AMOUNT_IDX, amount_med, leaf_values[_BID_AMOUNT_IDX]),
        ):
            if med is None or med == 0 or not isinstance(value, (int, float)):
                continue
            delta = (value - med) / abs(med)
            if abs(delta) >= critical_pct:
                styles[leaf_idx] = "money_crit"
                comments[leaf_idx] = _deviation_comment(bidder, value, med, delta, True)
            elif abs(delta) >= warn_pct:
                styles[leaf_idx] = "money_warn"
                comments[leaf_idx] = _deviation_comment(bidder, value, med, delta, False)

        # Đánh dấu vi phạm Phụ lục 02 trực tiếp lên ô Thương hiệu/Xuất xứ.
        pl2_issues = grouped[cid]["pl2"].get(bidder, {})
        for key, leaf_idx in (("brand", _BRAND_IDX), ("origin", _ORIGIN_IDX)):
            issue = pl2_issues.get(key)
            if issue:
                msg, is_critical = issue
                styles[leaf_idx] = "critical" if is_critical else "warning"
                comments[leaf_idx] = f"Phụ lục 02 — {msg}"

        for j, value in enumerate(leaf_values):
            kind = _BLOCK_LEAVES[j][1]
            style = f[styles[j]] if j in styles else f[kind]
            _write(ws, r, base + j, value, style)
            if j in comments:
                ws.write_comment(r, base + j, comments[j], {"author": "HSMT Enterprise AI", "width": 260, "height": 96})


_INVALID_SHEET = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet_name(name: str, used: set[str]) -> str:
    clean = _INVALID_SHEET.sub(" ", str(name or "")).strip() or "Hạng mục"
    clean = clean[:31]
    base = clean
    suffix = 2
    while clean.lower() in used:
        tail = f" ({suffix})"
        clean = base[:31 - len(tail)] + tail
        suffix += 1
    used.add(clean.lower())
    return clean


def export_consolidated_summary(result: ComparisonResult, output_path: str | Path) -> str:
    """Xuất file tổng hợp độc lập theo đúng format bảng chào giá tổng hợp.

    Mỗi hạng mục (sheet gốc) là một worksheet riêng; các nhà thầu xếp cạnh nhau
    theo block; ô "ĐG tổng hợp"/"Thành tiền NT chào" lệch nhiều được tô màu và
    gắn ghi chú trực tiếp. File KHÔNG chứa cột phân tích (Mức độ, Điểm bất thường).
    """
    output_path = str(output_path)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb = xlsxwriter.Workbook(output_path, {
        "constant_memory": True,
        "strings_to_formulas": False,
        "strings_to_urls": False,
        "nan_inf_to_errors": True,
    })
    f = _formats(wb)
    try:
        bidders = list((result.audit.get("bidder_sha256") or {}).keys())
        thresholds = result.audit.get("thresholds") or {}
        warn_pct = float(thresholds.get("price_warn_pct", 0.10))
        critical_pct = float(thresholds.get("price_critical_pct", 0.25))
        grouped, meta = _build_quote_groups(result)

        if not bidders or not grouped:
            ws = wb.add_worksheet("Tổng hợp chào giá")
            ws.write(0, 0, "Không có dữ liệu hạng mục để tổng hợp.", f["text"])
            return output_path

        # Gom hạng mục theo từng sheet gốc, giữ thứ tự xuất hiện theo dòng.
        by_sheet: dict[str, list[str]] = defaultdict(list)
        for cid in sorted(grouped, key=lambda c: (meta[c][0], meta[c][1])):
            by_sheet[meta[cid][0]].append(cid)

        used_names: set[str] = set()
        for sheet_name, cids in by_sheet.items():
            ws = wb.add_worksheet(_safe_sheet_name(sheet_name, used_names))
            ws.set_tab_color("#1F4E78")
            _write_quote_header(ws, f, bidders, f"BẢNG CHÀO GIÁ TỔNG HỢP — {sheet_name}")
            r = 4
            for cid in cids:
                _write_quote_row(ws, f, r, bidders, cid, grouped, meta, warn_pct, critical_pct)
                r += 1
    finally:
        wb.close()
    return output_path


_DIFF_HEADERS = ["Mức độ", "Nhà thầu", "Sheet", "STT", "Tên hạng mục", "Thông số", "Giá trị chuẩn", "Giá trị đối chiếu", "Sai lệch", "Sai lệch (%)", "Độ tương đồng", "Nhận xét", "Mã chuẩn"]


def _difference_rows(result: ComparisonResult) -> Iterator[dict[str, Any]]:
    for row in result.rows:
        item = row.reference or row.candidate
        for diff in row.differences:
            yield {
                "Mức độ": diff.severity.value, "Nhà thầu": row.bidder, "Sheet": item.sheet if item else "",
                "STT": item.stt if item else "", "Tên hạng mục": item.item_name if item else "", "Thông số": diff.field,
                "Giá trị chuẩn": diff.reference_value, "Giá trị đối chiếu": diff.candidate_value,
                "Sai lệch": diff.delta, "Sai lệch (%)": diff.delta_pct, "Độ tương đồng": diff.similarity,
                "Nhận xét": diff.message, "Mã chuẩn": row.canonical_id,
            }


def _differences(wb, result: ComparisonResult, f) -> None:
    _stream(wb, "So sánh thông số", _difference_rows(result), _DIFF_HEADERS, sum(len(r.differences) for r in result.rows), f, "#8064A2")


_UNMATCHED_HEADERS = ["Mức độ", "Nhà thầu", "Kiểu khớp", "Sheet", "Dòng", "STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá", "Thành tiền", "Lý do"]


def _unmatched_rows(result: ComparisonResult) -> Iterator[dict[str, Any]]:
    for row in result.rows:
        if row.match.kind not in {MatchKind.MISSING, MatchKind.EXTRA}: continue
        item = row.reference or row.candidate
        yield {
            "Mức độ": row.severity.value, "Nhà thầu": row.bidder, "Kiểu khớp": row.match.kind.value,
            "Sheet": item.sheet if item else "", "Dòng": item.row_number if item else None,
            "STT": item.stt if item else "", "Mã hiệu": item.item_code if item else "",
            "Tên hạng mục": item.item_name if item else "", "ĐVT": item.unit if item else "",
            "Khối lượng": item.quantity if item else None, "Đơn giá": item.unit_price_total if item else None,
            "Thành tiền": item.amount if item else None, "Lý do": " | ".join(row.flags) or row.match.reason,
        }


def _unmatched(wb, result: ComparisonResult, f) -> None:
    count = sum(r.match.kind in {MatchKind.MISSING, MatchKind.EXTRA} for r in result.rows)
    _stream(wb, "Thiếu và phát sinh", _unmatched_rows(result), _UNMATCHED_HEADERS, count, f, "#C65911")


_QUALITY_HEADERS = ["Hồ sơ", "Phía", "File", "Sheet", "Dòng", "STT", "Tên hạng mục", "Cảnh báo dữ liệu"]


def _quality_rows(result: ComparisonResult) -> Iterator[dict[str, Any]]:
    seen = set()
    for compared in result.rows:
        for side, item in (("Chuẩn", compared.reference), ("Đối chiếu", compared.candidate)):
            if not item: continue
            for flag in item.data_quality_flags:
                key = (item.workbook, item.sheet, item.row_number, flag)
                if key in seen: continue
                seen.add(key)
                yield {"Hồ sơ": item.bidder, "Phía": side, "File": item.workbook, "Sheet": item.sheet, "Dòng": item.row_number, "STT": item.stt, "Tên hạng mục": item.item_name, "Cảnh báo dữ liệu": flag}


def _quality(wb, result: ComparisonResult, f) -> None:
    count = len({(item.workbook, item.sheet, item.row_number, flag) for row in result.rows for item in (row.reference, row.candidate) if item for flag in item.data_quality_flags})
    _stream(wb, "Chất lượng dữ liệu", _quality_rows(result), _QUALITY_HEADERS, count, f, "#FFC000")


def _stream(wb, base_name: str, rows: Iterable[dict[str, Any]], headers: Sequence[str], expected: int, f, tab_color: str) -> None:
    iterator = iter(rows); capacity = EXCEL_MAX_ROWS - 2; total = 0; part = 1
    while total < max(expected, 1):
        name = base_name if part == 1 else f"{base_name[:25]}_{part}"
        ws = wb.add_worksheet(name[:31]); ws.set_tab_color(tab_color); _header(ws, headers, f); _widths(ws, headers); ws.freeze_panes(1,0)
        written = 0
        for record in iterator:
            row_index = written + 1
            for col, header in enumerate(headers): _write(ws, row_index, col, record.get(header), _cell_style(header, record, f))
            written += 1; total += 1
            if written >= capacity: break
        if written == 0: _write(ws, 1, 0, "Không có dữ liệu", f["text"])
        else:
            ws.autofilter(0, 0, written, len(headers)-1)
            if "Điểm bất thường" in headers:
                col = headers.index("Điểm bất thường")
                ws.conditional_format(1, col, written, col, {"type":"3_color_scale","min_color":"#63BE7B","mid_color":"#FFEB84","max_color":"#F8696B"})
        part += 1
        if written < capacity: break


def _header(ws, headers: Sequence[str], f) -> None:
    ws.set_row(0, 34)
    for col, header in enumerate(headers): _write(ws, 0, col, header, f["header"])


def _cell_style(header: str, record: dict[str, Any], f):
    if header == "Mức độ": return f[_SEVERITY_STYLE.get(str(record.get(header, "")), "text")]
    lower = header.lower()
    if "(%)" in header or header in {"Điểm khớp", "Độ tương đồng"}: return f["pct"]
    if any(k in lower for k in ("đơn giá", "thành tiền", "trung vị", "vl chính", "vl phụ", "nc&m", "quản lý", "lợi nhuận")): return f["money"]
    if header in {"Khối lượng", "KL chuẩn", "KL đối chiếu", "Sai lệch"}: return f["num"]
    if header in {"Robust Z", "Điểm bất thường"}: return f["score"]
    if any(k in lower for k in ("tên hạng mục", "cờ đánh giá", "ghi chú", "nhận xét", "giá trị chuẩn", "giá trị đối chiếu", "cảnh báo", "lý do")): return f["long"]
    return f["text"]


def _widths(ws, headers: Sequence[str]) -> None:
    for col, header in enumerate(headers):
        lower = header.lower()
        if any(k in lower for k in ("tên hạng mục", "cờ đánh giá", "ghi chú", "nhận xét", "cảnh báo", "lý do")): width = 46
        elif any(k in lower for k in ("giá trị chuẩn", "giá trị đối chiếu")): width = 30
        elif "sheet" in lower or "nhà thầu" in lower: width = 22
        elif "mã" in lower or "stt" in lower or "kiểu khớp" in lower or "mức độ" in lower: width = 18
        else: width = 15
        ws.set_column(col, col, width)


def _pl2_requirements(wb, result: ComparisonResult, f) -> None:
    requirements = result.audit.get("pl2_requirements") or []
    if not requirements:
        return
    headers = ["Hệ thống", "Vật tư thiết bị", "Yêu cầu thương hiệu - xuất xứ", "Thương hiệu cho phép", "Xuất xứ cho phép", "Ghi chú", "Sheet PL02", "Dòng PL02"]
    rows = []
    for req in requirements:
        rows.append({
            "Hệ thống": req.get("system", ""), "Vật tư thiết bị": req.get("item_name", ""),
            "Yêu cầu thương hiệu - xuất xứ": req.get("requirement", ""),
            "Thương hiệu cho phép": " / ".join(req.get("brands") or []),
            "Xuất xứ cho phép": " / ".join(req.get("origins") or []),
            "Ghi chú": req.get("note", ""), "Sheet PL02": req.get("sheet", ""), "Dòng PL02": req.get("row"),
        })
    _stream(wb, "Yêu cầu Phụ lục 02", rows, headers, len(rows), f, "#7030A0")


def _audit(wb, result: ComparisonResult, f) -> None:
    ws = wb.add_worksheet("Nhật ký và bảo mật"); ws.set_column("A:A", 34); ws.set_column("B:B", 110)
    _write(ws, 0, 0, "Thuộc tính", f["header"]); _write(ws, 0, 1, "Giá trị", f["header"])
    entries = {
        "Chế độ xử lý": result.audit.get("mode"), "Nguồn danh mục/khối lượng": result.summary.reference_name,
        "Nguyên tắc": result.audit.get("comparison_principle", "So sánh theo nguồn chuẩn/baseline"),
        "Mức bảo mật": result.audit.get("privacy"), "Cho phép mạng": result.audit.get("network_allowed"),
        "Mô hình embedding local": result.audit.get("embedding_model"), "Mô hình reranker local": result.audit.get("reranker_model"),
        "SHA-256 nguồn chuẩn": result.audit.get("reference_sha256"),
        "SHA-256 Phụ lục 01": result.audit.get("pl1_sha256"),
        "SHA-256 Phụ lục 02": result.audit.get("pl2_sha256"),
        "Thống kê PL02": json.dumps(result.audit.get("pl2_stats", {}), ensure_ascii=False, indent=2),
        "Thống kê so sánh ngang hàng": json.dumps(result.audit.get("peer_stats", {}), ensure_ascii=False, indent=2),
        "SHA-256 các file": json.dumps(result.audit.get("bidder_sha256", {}), ensure_ascii=False, indent=2),
        "Ngưỡng đánh giá": json.dumps(result.audit.get("thresholds", {}), ensure_ascii=False, indent=2),
        "Mapping cột": json.dumps(result.audit.get("sheet_mappings", {}), ensure_ascii=False, indent=2, default=str),
        "Lưu ý": "Điểm bất thường là tín hiệu hỗ trợ rà soát. Chuyên viên phải xem hồ sơ gốc trước khi kết luận.",
    }
    for row, (key, value) in enumerate(entries.items(), 1): _write(ws, row, 0, key, f["label"]); _write(ws, row, 1, value, f["mono"])
