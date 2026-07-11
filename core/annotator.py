from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.comments import Comment
from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import ComparedItem, FieldDifference, RowType, Severity, WorkbookData

_FILL = {
    Severity.INFO: PatternFill("solid", fgColor="DDEBF7"),
    Severity.REVIEW: PatternFill("solid", fgColor="FFF2CC"),
    Severity.WARNING: PatternFill("solid", fgColor="FCE4D6"),
    Severity.CRITICAL: PatternFill("solid", fgColor="F4CCCC"),
}
_FONT = {
    Severity.INFO: "1F4E78",
    Severity.REVIEW: "7F6000",
    Severity.WARNING: "C65911",
    Severity.CRITICAL: "9C0006",
}
_THIN = Side(style="thin", color="D9E1F2")


def _sheet_meta(workbook: WorkbookData) -> dict[str, dict]:
    return {str(info.get("sheet")): info for info in workbook.sheet_info}


def _field_key(diff: FieldDifference) -> str | None:
    field = diff.field.lower()
    if "tên hạng mục" in field or field == "hạng mục":
        return "item_name"
    if "mã hiệu" in field:
        return "item_code"
    if "đơn vị" in field:
        return "unit"
    if "khối lượng mời thầu" in field:
        return "reference_quantity"
    if "khối lượng nhà thầu" in field:
        return "bid_quantity"
    if "đơn giá tổng hợp" in field:
        return "unit_price_total"
    if "thành tiền theo klmt" in field:
        return "reference_amount"
    if "thành tiền nhà thầu" in field:
        return "bid_amount"
    if "vl chính" in field:
        return "price_main"
    if "vl phụ" in field:
        return "price_aux"
    if "nc & máy" in field or "nc&m" in field:
        return "price_labor"
    if "quản lý" in field:
        return "price_management"
    if "lợi nhuận" in field:
        return "price_profit"
    if "vật tư" in field or "quy cách" in field:
        return "material"
    if "thương hiệu" in field:
        return "brand"
    if "xuất xứ" in field:
        return "origin"
    return None


def _comment_text(row: ComparedItem, max_chars: int = 6000) -> str:
    lines = [
        f"AI đánh dấu: {row.severity.value}",
        f"Điểm bất thường: {row.anomaly_score:.1f}/100",
        f"Ghép với PL01: {row.match.kind.value}, độ tin cậy {row.match.score:.1%}",
    ]
    if row.pl2_category:
        lines.append(f"Nhóm PL02: {row.pl2_category}")
        lines.append(f"Yêu cầu PL02: {row.pl2_requirement}")
        lines.append(f"Trạng thái PL02: {row.pl2_status}")
    if row.flags:
        lines.append("Lý do:")
        lines.extend(f"- {flag}" for flag in row.flags)
    text = "\n".join(lines)
    return text[:max_chars]


def _append_comment(cell, text: str) -> None:
    if cell.comment and cell.comment.text:
        text = cell.comment.text + "\n\n--- HSMT Enterprise AI ---\n" + text
    cell.comment = Comment(text, "HSMT Enterprise AI")


_SORTED_SUFFIX = " — sắp xếp"
_GOC_SUFFIX = " — gốc"


def _phatsinh_block_rows(rows: list[ComparedItem]) -> dict[str, set[int]]:
    """Xác định các dòng thuộc KHỐI phát sinh theo từng sheet nhà thầu.

    Đi theo thứ tự tài liệu: một dòng cha (DETAIL) không ghép được PL01 mở một
    khối phát sinh; các vật tư con phía sau kế thừa. Vật tư con dưới hạng mục cha
    ĐÃ KHỚP thì KHÔNG bị coi là phát sinh (không bị dời).
    """
    by_sheet: dict[str, list[ComparedItem]] = defaultdict(list)
    for row in rows:
        if row.candidate is not None:
            by_sheet[row.candidate.sheet].append(row)
    result: dict[str, set[int]] = defaultdict(set)
    for sheet_name, sheet_rows in by_sheet.items():
        sheet_rows.sort(key=lambda r: r.candidate.row_number)
        block_extra = False
        for row in sheet_rows:
            if row.candidate.row_type is RowType.DETAIL:
                block_extra = row.reference is None
            if block_extra:
                result[sheet_name].add(row.candidate.row_number)
    return result


def _suffixed_sheet_name(base: str, suffix: str, used: set[str]) -> str:
    limit = 31
    name = base + suffix
    if len(name) > limit:
        name = base[: limit - len(suffix)] + suffix
    final, index = name, 2
    while final.lower() in used:
        tail = f" ({index})"
        final = name[: limit - len(tail)] + tail
        index += 1
    used.add(final.lower())
    return final


_CELL_REF = re.compile(r"^(\$?)([A-Za-z]{1,3})(\$?)(\d+)$")
_NAME_REF = re.compile(r"^[A-Za-z_\\][A-Za-z0-9_.\\]*$")


def _same_row_formula(formula: str, row: int) -> bool:
    """True nếu công thức chỉ tham chiếu ô CÙNG DÒNG, cùng sheet, dòng tương đối.

    Các công thức này (ví dụ Thành tiền = KL × Đơn giá cùng dòng) dời dòng được
    an toàn bằng cách dịch lại địa chỉ. Mọi trường hợp khác (tham chiếu dòng
    khác, dòng tuyệt đối $5, sheet khác, vùng nhiều dòng) trả False.
    """
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return False
    for tok in tokens:
        if tok.type != Token.OPERAND or tok.subtype != Token.RANGE:
            continue
        ref = tok.value
        if "!" in ref:
            return False
        for part in ref.split(":"):
            m = _CELL_REF.match(part)
            if not m:
                # Defined name (độc lập vị trí) thì cho phép; còn lại từ chối.
                if _NAME_REF.match(part):
                    continue
                return False
            if m.group(3) == "$" or int(m.group(4)) != row:
                return False
    return True


def _translate_row_formula(formula: str, col_letter: str, src_row: int, dst_row: int):
    try:
        return Translator(formula, origin=f"{col_letter}{src_row}").translate_formula(f"{col_letter}{dst_row}")
    except Exception:
        return None


def _rewrite_sheet_references(wb, renames: dict[str, str]) -> None:
    """Đổi mọi tham chiếu `'tên cũ'!` sang `'tên mới'!` trong toàn workbook.

    openpyxl không tự cập nhật tham chiếu khi đổi tên sheet (khác Excel), nên
    phải tự sửa: công thức, hyperlink nội bộ, defined names và chart series —
    để sheet `Tổng hợp`/biểu đồ tiếp tục trỏ đúng bản `— gốc` còn nguyên bố cục.
    """
    if not renames:
        return

    def fix(text: str) -> str:
        for old, new in renames.items():
            oq, nq = old.replace("'", "''"), new.replace("'", "''")
            text = text.replace(f"'{oq}'!", f"'{nq}'!")
        return text

    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if isinstance(v, str) and v.startswith("=") and "!" in v:
                    nv = fix(v)
                    if nv != v:
                        c.value = nv
                hl = getattr(c, "hyperlink", None)
                if hl is not None:
                    for attr in ("target", "location"):
                        val = getattr(hl, attr, None)
                        if isinstance(val, str) and "!" in val:
                            nv = fix(val)
                            if nv != val:
                                setattr(hl, attr, nv)
    try:
        names = wb.defined_names
        for key in list(names.keys()):
            dn = names[key]
            if isinstance(getattr(dn, "value", None), str):
                nv = fix(dn.value)
                if nv != dn.value:
                    dn.value = nv
    except Exception:
        pass
    try:
        for ws in list(wb.worksheets) + list(getattr(wb, "chartsheets", [])):
            for chart in list(getattr(ws, "_charts", []) or []):
                for ser in list(getattr(chart, "series", []) or []):
                    for holder in (getattr(ser, "val", None), getattr(ser, "cat", None), getattr(ser, "tx", None)):
                        if holder is None:
                            continue
                        for kind in ("numRef", "strRef", "multiLvlStrRef"):
                            ref = getattr(holder, kind, None)
                            f = getattr(ref, "f", None)
                            if isinstance(f, str):
                                nf = fix(f)
                                if nf != f:
                                    ref.f = nf
    except Exception:
        pass


def _add_sorted_companion_sheets(
    wb,
    source_path: Path,
    rows: list[ComparedItem],
    bidder_workbook: WorkbookData,
    meta: dict[str, dict],
) -> None:
    """Với mỗi sheet có hạng mục phát sinh, dựng bản SẮP XẾP mang TÊN GỐC.

    - Bản gốc được đổi tên thành '<tên> — gốc' và GIỮ NGUYÊN toàn bộ công thức;
      mọi tham chiếu chéo (sheet Tổng hợp, hyperlink AI_KIEM_TRA, chart) được
      viết lại để tiếp tục trỏ đúng bản gốc.
    - Bản sắp xếp: giữ dòng đầu mục (A, I, II...); hạng mục khớp theo thứ tự tài
      liệu; khối phát sinh (cha + vật tư con) dồn xuống cuối sau dòng phân cách.
    - Công thức TRONG-DÒNG (thành tiền = KL × đơn giá...) được dịch địa chỉ theo
      dòng mới nên vẫn "sống"; công thức tham chiếu dòng khác/sheet khác chuyển
      thành giá trị tĩnh. Dòng tổng phụ cũ được thay bằng tổng dựng lại theo
      nhóm mới + tổng riêng cho phần phát sinh.
    """
    ps_rows = _phatsinh_block_rows(rows)
    cand_by_sheet: dict[str, dict[int, object]] = defaultdict(dict)
    for row in rows:
        cand = row.candidate
        if cand is not None:
            cand_by_sheet[cand.sheet].setdefault(cand.row_number, cand)

    # Dòng đầu mục (GROUP) lấy từ items của workbook; payload tiến trình con chỉ
    # giữ các dòng GROUP nên lọc lại ở đây cho cả hai đường chạy như nhau.
    group_rows_by_sheet: dict[str, dict[int, str]] = defaultdict(dict)
    for it in bidder_workbook.items:
        if it.row_type is RowType.GROUP:
            group_rows_by_sheet[it.sheet][it.row_number] = it.item_name

    targets = [s for s in cand_by_sheet if ps_rows.get(s) and s in wb.sheetnames]
    if not targets:
        return

    value_wb = load_workbook(source_path, data_only=True)
    used = {name.lower() for name in wb.sheetnames}
    bold = Font(name="Arial", bold=True)
    fill_total = PatternFill("solid", fgColor="DDEBF7")
    fill_ps = PatternFill("solid", fgColor="FCE4D6")
    promotions: list[tuple[str, object]] = []

    try:
        for sheet_name in targets:
            src = wb[sheet_name]
            vsrc = value_wb[sheet_name] if sheet_name in value_wb.sheetnames else None
            info = meta.get(sheet_name) or {}
            fields = {str(k): int(v) for k, v in (info.get("field_columns") or {}).items()}
            header_end = int(info.get("header_end") or 1)
            name_col = fields.get("item_name", 2)
            amount_cols = [fields[k] for k in ("reference_amount", "bid_amount") if k in fields]
            ncol = src.max_column
            new = wb.create_sheet(_suffixed_sheet_name(sheet_name, _SORTED_SUFFIX, used))

            for col in range(1, ncol + 1):
                letter = get_column_letter(col)
                dim = src.column_dimensions.get(letter)
                if dim is not None and dim.width:
                    new.column_dimensions[letter].width = dim.width

            def copy_row(dst_row: int, src_row: int, *, with_comment: bool = True, translate: bool = True) -> None:
                for col in range(1, ncol + 1):
                    s = src.cell(src_row, col)
                    v = s.value
                    if isinstance(v, str) and v.startswith("="):
                        translated = None
                        if translate and _same_row_formula(v, src_row):
                            translated = _translate_row_formula(v, get_column_letter(col), src_row, dst_row)
                        if translated is not None:
                            v = translated
                        else:
                            v = vsrc.cell(src_row, col).value if vsrc is not None else None
                    elif type(v).__name__ in ("ArrayFormula", "DataTableFormula"):
                        v = vsrc.cell(src_row, col).value if vsrc is not None else None
                    d = new.cell(dst_row, col, v)
                    d._style = s._style
                    if with_comment and s.comment is not None:
                        d.comment = Comment(s.comment.text, s.comment.author or "HSMT Enterprise AI")
                if src.row_dimensions[src_row].height is not None:
                    new.row_dimensions[dst_row].height = src.row_dimensions[src_row].height

            def write_label_row(dst_row: int, label: str, fill: PatternFill, sums: dict[int, object] | None = None) -> None:
                for col in range(1, ncol + 1):
                    cell = new.cell(dst_row, col)
                    cell.fill = fill
                    cell.font = bold
                new.cell(dst_row, name_col, label)
                for col, value in (sums or {}).items():
                    cell = new.cell(dst_row, col, value)
                    cell.number_format = "#,##0"

            def sum_over(col: int, pairs: list[tuple[int, int]]):
                """=SUM(ô các dòng DETAIL mới); quá dài thì trả tổng tĩnh."""
                if not pairs:
                    return None
                letter = get_column_letter(col)
                if len(pairs) <= 150:
                    return "=SUM(" + ",".join(f"{letter}{new_row}" for _, new_row in pairs) + ")"
                total, seen = 0.0, False
                if vsrc is not None:
                    for src_row, _ in pairs:
                        value = vsrc.cell(src_row, col).value
                        if isinstance(value, (int, float)):
                            total += float(value)
                            seen = True
                return total if seen else None

            items = cand_by_sheet[sheet_name]
            groups = group_rows_by_sheet.get(sheet_name, {})
            ps = ps_rows.get(sheet_name, set())
            all_rows = sorted(set(items) | set(groups))

            out = 1
            for r in range(1, header_end + 1):
                copy_row(out, r, with_comment=False, translate=False)
                out += 1

            group_subtotal_refs: dict[int, list[str]] = {c: [] for c in amount_cols}
            current_details: list[tuple[int, int]] = []
            current_label = ""

            def close_group() -> None:
                nonlocal out, current_details
                if current_details and amount_cols:
                    sums: dict[int, object] = {}
                    for c in amount_cols:
                        value = sum_over(c, current_details)
                        if value is not None:
                            sums[c] = value
                    if sums:
                        label = f"Cộng: {current_label}" if current_label else "Cộng"
                        write_label_row(out, label, fill_total, sums)
                        for c in sums:
                            group_subtotal_refs[c].append(f"{get_column_letter(c)}{out}")
                        out += 1
                current_details = []

            for r in all_rows:
                if r in groups:
                    close_group()
                    current_label = groups[r]
                    copy_row(out, r, with_comment=False, translate=False)
                    out += 1
                    continue
                if r in ps:
                    continue
                copy_row(out, r)
                cand = items[r]
                if getattr(cand, "row_type", None) is RowType.DETAIL:
                    current_details.append((r, out))
                out += 1
            close_group()

            pl01_total_ref: dict[int, str] = {}
            if any(group_subtotal_refs.get(c) for c in amount_cols):
                sums = {}
                for c in amount_cols:
                    refs = group_subtotal_refs[c]
                    if refs and len(refs) <= 150:
                        sums[c] = "=SUM(" + ",".join(refs) + ")"
                if sums:
                    write_label_row(out, "CỘNG THEO DANH MỤC ĐỐI CHIẾU", fill_total, sums)
                    pl01_total_ref = {c: f"{get_column_letter(c)}{out}" for c in sums}
                    out += 1

            if ps:
                write_label_row(out, "HẠNG MỤC PHÁT SINH NGOÀI DANH MỤC (nhà thầu tự thêm)", fill_ps)
                out += 1
                ps_details: list[tuple[int, int]] = []
                for r in sorted(ps):
                    copy_row(out, r)
                    cand = items.get(r)
                    if cand is not None and getattr(cand, "row_type", None) is RowType.DETAIL:
                        ps_details.append((r, out))
                    out += 1
                if amount_cols:
                    sums = {}
                    for c in amount_cols:
                        value = sum_over(c, ps_details)
                        if value is not None:
                            sums[c] = value
                    if sums:
                        write_label_row(out, "CỘNG PHÁT SINH", fill_ps, sums)
                        ps_total_ref = {c: f"{get_column_letter(c)}{out}" for c in sums}
                        out += 1
                        grand: dict[int, object] = {}
                        for c in amount_cols:
                            a, b = pl01_total_ref.get(c), ps_total_ref.get(c)
                            if a and b:
                                grand[c] = f"={a}+{b}"
                            elif a or b:
                                grand[c] = f"={a or b}"
                        if grand:
                            write_label_row(out, "TỔNG CỘNG SAU SẮP XẾP", fill_total, grand)
                            out += 1

            new.freeze_panes = new.cell(header_end + 1, 1)
            promotions.append((sheet_name, new))
    finally:
        value_wb.close()

    # Bản sắp xếp mang TÊN GỐC; bản gốc đổi thành '— gốc' và mọi tham chiếu chéo
    # được viết lại để tiếp tục trỏ đúng bản gốc (openpyxl không tự làm như Excel).
    renames: dict[str, str] = {}
    used_names = {name.lower() for name in wb.sheetnames}
    for original, sorted_ws in promotions:
        old_ws = wb[original]
        goc_name = _suffixed_sheet_name(original, _GOC_SUFFIX, used_names)
        renames[original] = goc_name
        index = wb._sheets.index(old_ws)
        old_ws.title = goc_name
        sorted_ws.title = original
        wb._sheets.remove(sorted_ws)
        wb._sheets.insert(index, sorted_ws)
    _rewrite_sheet_references(wb, renames)


def _prepare_review_sheet(wb, bidder: str):
    for name in ("AI_TONG_QUAN", "AI_KIEM_TRA"):
        if name in wb.sheetnames:
            del wb[name]
    summary = wb.create_sheet("AI_TONG_QUAN", 0)
    review = wb.create_sheet("AI_KIEM_TRA", 1)

    summary["A1"] = "KẾT QUẢ KIỂM TRA HỒ SƠ CHÀO GIÁ"
    summary["A2"] = f"Nhà thầu: {bidder}"
    summary["A4"] = "Màu"
    summary["B4"] = "Ý nghĩa"
    legend = [
        (Severity.REVIEW, "Cần chuyên viên xác nhận"),
        (Severity.WARNING, "Sai lệch đáng kể"),
        (Severity.CRITICAL, "Thiếu, sai công thức hoặc chênh lệch nghiêm trọng"),
    ]
    for index, (severity, meaning) in enumerate(legend, 5):
        summary.cell(index, 1, severity.value)
        summary.cell(index, 1).fill = _FILL[severity]
        summary.cell(index, 1).font = Font(name="Arial", bold=True, color=_FONT[severity])
        summary.cell(index, 2, meaning)
    summary["A10"] = "Lưu ý"
    summary["B10"] = (
        "Các đánh dấu là tín hiệu hỗ trợ rà soát. Thương hiệu ngoài Phụ lục 02 không tự động bị loại; "
        "cần kiểm tra tài liệu chứng minh tương đương hoặc tốt hơn. Khác tên sheet chỉ được ghi chú, "
        "không được tính là cảnh báo khi hạng mục đã khớp."
    )
    summary.column_dimensions["A"].width = 25
    summary.column_dimensions["B"].width = 95
    summary.merge_cells("A1:H1")
    summary["A1"].font = Font(name="Arial", bold=True, size=16, color="FFFFFF")
    summary["A1"].fill = PatternFill("solid", fgColor="17365D")
    summary["A1"].alignment = Alignment(horizontal="center")

    headers = [
        "Mức độ", "Sheet gốc", "Dòng gốc", "STT", "Hạng mục PL01", "Hạng mục nhà thầu",
        "Thông số", "Giá trị yêu cầu/nhóm", "Giá trị nhà thầu", "Chênh lệch", "Chênh lệch (%)",
        "Lý do", "Liên kết tới dòng gốc",
    ]
    for col, header in enumerate(headers, 1):
        cell = review.cell(1, col, header)
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.font = Font(name="Arial", bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=_THIN)
    widths = [18, 24, 12, 14, 48, 48, 30, 35, 35, 18, 18, 80, 22]
    for col, width in enumerate(widths, 1):
        review.column_dimensions[get_column_letter(col)].width = width
    review.freeze_panes = "A2"
    review.auto_filter.ref = f"A1:M1"
    return summary, review


def annotate_bidder_workbook(
    source_path: str | Path,
    output_path: str | Path,
    bidder_workbook: WorkbookData,
    rows: list[ComparedItem],
) -> str:
    """Create an annotated copy while preserving original formulas and layout.

    The original workbook is never overwritten. Problematic cells are marked IN
    PLACE with a fill colour and a hover comment (chú thích) — NO extra columns
    are added next to the data. Two front sheets (AI_TONG_QUAN overview and
    AI_KIEM_TRA linked findings) are still provided.
    """
    source_path, output_path = Path(source_path), Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = load_workbook(source_path, data_only=False, keep_links=True)
    try:
        summary_ws, review_ws = _prepare_review_sheet(wb, bidder_workbook.bidder)
        meta = _sheet_meta(bidder_workbook)
        # CHỈ đánh dấu các dòng có sai lệch (severity khác OK). Hạng mục khớp —
        # kể cả khớp nhưng khác tên sheet (chỉ là ghi chú, không phải lỗi) — KHÔNG
        # được tô màu hay gắn chú thích trong file nhà thầu.
        grouped_by_location: dict[tuple[str, int], list[ComparedItem]] = defaultdict(list)
        for compared in rows:
            if compared.candidate is None or compared.severity is Severity.OK:
                continue
            location = (compared.candidate.sheet, compared.candidate.row_number)
            grouped_by_location[location].append(compared)

        review_row = 2
        counts = defaultdict(int)
        for compared in rows:
            if compared.severity is Severity.OK:
                continue
            counts[compared.severity.value] += 1
            candidate, reference = compared.candidate, compared.reference
            diffs = compared.differences
            fields = list(dict.fromkeys(diff.field for diff in diffs))
            ref_values = list(dict.fromkeys(str(diff.reference_value) for diff in diffs if diff.reference_value not in (None, "")))
            cand_values = list(dict.fromkeys(str(diff.candidate_value) for diff in diffs if diff.candidate_value not in (None, "")))
            deltas = [diff.delta for diff in diffs if isinstance(diff.delta, (int, float))]
            delta_pcts = [diff.delta_pct for diff in diffs if isinstance(diff.delta_pct, (int, float))]
            reasons = list(dict.fromkeys(compared.flags or [compared.match.reason]))
            values = [
                compared.severity.value,
                candidate.sheet if candidate else "",
                candidate.row_number if candidate else None,
                candidate.stt if candidate else (reference.stt if reference else ""),
                reference.item_name if reference else "",
                candidate.item_name if candidate else "",
                " | ".join(fields),
                " | ".join(ref_values)[:8000],
                " | ".join(cand_values)[:8000],
                max(deltas, key=abs) if deltas else None,
                max(delta_pcts, key=abs) if delta_pcts else None,
                " | ".join(reasons)[:30000],
                "Mở dòng gốc" if candidate else "Không có dòng để mở",
            ]
            for col, value in enumerate(values, 1):
                cell = review_ws.cell(review_row, col, value)
                cell.alignment = Alignment(vertical="top", wrap_text=col in {5, 6, 7, 8, 9, 12})
                if col == 1:
                    cell.fill = _FILL.get(compared.severity, PatternFill())
                    cell.font = Font(name="Arial", bold=True, color=_FONT.get(compared.severity, "000000"))
                if col == 11 and isinstance(value, (int, float)):
                    cell.number_format = "0.00%"
                if col == 10 and isinstance(value, (int, float)):
                    cell.number_format = "#,##0.000;[Red]-#,##0.000"
            if candidate:
                escaped = candidate.sheet.replace("'", "''")
                review_ws.cell(review_row, 13).hyperlink = f"#'{escaped}'!A{candidate.row_number}"
                review_ws.cell(review_row, 13).style = "Hyperlink"
            review_row += 1

        # Add exact spreadsheet formula/external-link issues, including cells
        # outside parsed BOQ rows. These are detected by direct OOXML scanning.
        for issue in bidder_workbook.formula_issues:
            kind = str(issue.get("kind", ""))
            severity = Severity.CRITICAL if kind == "FORMULA_ERROR" else Severity.REVIEW
            counts[severity.value] += 1
            sheet_name = str(issue.get("sheet", ""))
            row_number = int(issue.get("row", 0) or 0)
            cell_ref = str(issue.get("cell", ""))
            message = str(issue.get("message", ""))
            formula = str(issue.get("formula", ""))
            values = [
                severity.value, sheet_name, row_number, "", "", "",
                f"Lỗi Excel tại ô {cell_ref}", formula, str(issue.get("value", "")),
                None, None, message, "Mở ô lỗi",
            ]
            for col, value in enumerate(values, 1):
                cell = review_ws.cell(review_row, col, value)
                cell.alignment = Alignment(vertical="top", wrap_text=col in {7, 8, 9, 12})
                if col == 1:
                    cell.fill = _FILL[severity]
                    cell.font = Font(name="Arial", bold=True, color=_FONT[severity])
            if sheet_name and cell_ref and sheet_name in wb.sheetnames:
                escaped = sheet_name.replace("'", "''")
                review_ws.cell(review_row, 13).hyperlink = f"#'{escaped}'!{cell_ref}"
                review_ws.cell(review_row, 13).style = "Hyperlink"
            review_row += 1

        summary_ws["A12"] = "Số dòng cần kiểm tra"
        summary_ws["B12"] = counts.get(Severity.REVIEW.value, 0)
        summary_ws["A13"] = "Số dòng cảnh báo"
        summary_ws["B13"] = counts.get(Severity.WARNING.value, 0)
        summary_ws["A14"] = "Số dòng bất thường"
        summary_ws["B14"] = counts.get(Severity.CRITICAL.value, 0)
        summary_ws["A16"] = "Tổng dòng trong AI_KIEM_TRA"
        summary_ws["B16"] = max(0, review_row - 2)
        summary_ws["A17"] = "Lỗi công thức/liên kết Excel"
        summary_ws["B17"] = len(bidder_workbook.formula_issues)
        summary_ws["A18"] = "External links trong workbook"
        summary_ws["B18"] = bidder_workbook.external_link_count

        # Bản đồ cột cho từng sheet — KHÔNG thêm bất kỳ cột nào vào file dữ liệu.
        # Chỉ dùng để biết ô giá trị nào cần tô màu và gắn chú thích trực tiếp.
        sheet_fields: dict[str, dict[str, int]] = {}
        for sheet_name, info in meta.items():
            if sheet_name not in wb.sheetnames:
                continue
            sheet_fields[sheet_name] = {str(k): int(v) for k, v in (info.get("field_columns") or {}).items()}

        # CHỈ tô màu + gắn CHÚ THÍCH lên ĐÚNG những ô có sai lệch. Mỗi sai lệch chỉ
        # đánh dấu đúng ô của nó (tên hạng mục khác -> bôi ô tên; khối lượng khác ->
        # bôi ô khối lượng...). KHÔNG bôi ô tên hạng mục nếu tên không sai. Sai lệch
        # không gắn với ô cụ thể (ví dụ một số thông số kỹ thuật) chỉ được liệt kê ở
        # sheet AI_KIEM_TRA, không tô màu bừa lên dòng.
        for (sheet_name, row_number), location_rows in grouped_by_location.items():
            if sheet_name not in wb.sheetnames or sheet_name not in sheet_fields:
                continue
            ws = wb[sheet_name]
            fields = sheet_fields[sheet_name]
            for compared in location_rows:
                for diff in compared.differences:
                    fill = _FILL.get(diff.severity)
                    if fill is None:
                        continue  # sai lệch mức OK -> không đánh dấu
                    key = _field_key(diff)
                    col = fields.get(key) if key else None
                    if not col:
                        continue  # không xác định được ô -> để AI_KIEM_TRA liệt kê
                    cell = ws.cell(row_number, col)
                    cell.fill = fill
                    _append_comment(cell, f"{diff.field}: {diff.message}"[:2000])

        # Highlight exact error cells and also write the AI reason on that row.
        for issue in bidder_workbook.formula_issues:
            sheet_name = str(issue.get("sheet", ""))
            cell_ref = str(issue.get("cell", ""))
            kind = str(issue.get("kind", ""))
            message = str(issue.get("message", ""))
            severity = Severity.CRITICAL if kind == "FORMULA_ERROR" else Severity.REVIEW
            if sheet_name not in wb.sheetnames or not cell_ref:
                continue
            ws = wb[sheet_name]
            target = ws[cell_ref]
            target.fill = _FILL[severity]
            target.font = Font(
                name="Arial", size=target.font.sz, bold=True,
                italic=target.font.italic, color=_FONT[severity], underline=target.font.underline,
            )
            _append_comment(target, message)

        review_ws.auto_filter.ref = f"A1:M{max(1, review_row - 1)}"

        # Với mỗi sheet có hạng mục phát sinh: dựng bản sắp xếp mang TÊN GỐC (dồn
        # phát sinh xuống cuối, công thức trong-dòng sống, tổng dựng lại); bản gốc
        # đổi tên '— gốc' giữ nguyên công thức và mọi tham chiếu được trỏ lại đúng.
        _add_sorted_companion_sheets(wb, source_path, rows, bidder_workbook, meta)

        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.save(output_path)
    finally:
        wb.close()
    return str(output_path)

