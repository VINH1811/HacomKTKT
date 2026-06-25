from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from .excel_io import list_sheets_fast, read_workbook_matrices, scan_xlsx_issues
from .models import DocumentRole, ItemRecord, RowType, WorkbookData
from .number_parser import math_error, parse_number, safe_amount
from .text_normalizer import (
    canonical_id,
    normalize_code,
    normalize_name,
    normalize_stt,
    normalize_text,
    normalize_unit,
    strip_accents,
)

COLUMN_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "item_code": [("ma hieu", 10), ("mã hiệu", 10), ("ma cong tac", 9), ("mã công tác", 9), ("ky hieu", 7), ("code", 6)],
    "item_name": [("ten hang muc", 12), ("tên hạng mục", 12), ("noi dung cong viec", 11), ("nội dung công việc", 11), ("dien giai", 10), ("diễn giải", 10), ("mo ta", 8), ("mô tả", 8), ("ten vat tu", 8), ("tên vật tư", 8)],
    "unit": [("don vi tinh", 12), ("đơn vị tính", 12), ("dvt", 10), ("đvt", 10), ("don vi", 7)],
    "quantity": [("khoi luong nha thau", 14), ("khối lượng nhà thầu", 14), ("khoi luong moi thau", 13), ("khối lượng mời thầu", 13), ("khoi luong", 10), ("khối lượng", 10), ("so luong", 8), ("số lượng", 8)],
    "unit_price": [("don gia du thau", 14), ("đơn giá dự thầu", 14), ("don gia nha thau", 14), ("đơn giá nhà thầu", 14), ("don gia tong hop", 12), ("đơn giá tổng hợp", 12), ("don gia", 10), ("đơn giá", 10), ("price", 7)],
    "amount": [("thanh tien sau thue", 15), ("thành tiền sau thuế", 15), ("thanh tien truoc thue", 14), ("thành tiền trước thuế", 14), ("thanh tien", 11), ("thành tiền", 11), ("gia tri", 8), ("giá trị", 8)],
    "material": [("ma hieu quy cach", 13), ("mã hiệu quy cách", 13), ("quy cach", 10), ("quy cách", 10), ("vat tu", 9), ("vật tư", 9), ("vat lieu", 8), ("vật liệu", 8)],
    "brand": [("thuong hieu", 12), ("thương hiệu", 12), ("nhan hieu", 10), ("hãng", 8)],
    "origin": [("xuat xu", 12), ("xuất xứ", 12), ("nuoc san xuat", 9), ("country", 7)],
    "note": [("ghi chu", 10), ("ghi chú", 10), ("remark", 7)],
}

SKIP_SHEETS = {
    "tong hop", "tổng hợp", "dieu khoan", "điều khoản", "bia", "bìa",
    "muc luc", "mục lục", "chart", "dashboard",
}

_HEADER_TERMS = (
    "stt", "dien giai", "diễn giải", "noi dung cong viec", "nội dung công việc",
    "don vi", "đơn vị", "khoi luong", "khối lượng", "kl moi thau", "kl nhà thầu",
    "don gia", "đơn giá", "thanh tien", "thành tiền", "thuong hieu", "thương hiệu",
    "xuat xu", "xuất xứ", "ma hieu", "mã hiệu", "mo ta", "mô tả",
    "ten hang muc", "tên hạng mục", "dvt", "đvt",
)

_FORMULA_ERROR = re.compile(r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A|NUM!|NULL!)", re.I)
_ROMAN = re.compile(r"^(?:[IVXLCDM]+)(?:[.\-]|$)", re.I)
_ALPHA = re.compile(r"^[A-Z](?:[.\-]|$)", re.I)
_NUM_SECTION = re.compile(r"^\d+(?:\.\d+)*(?:[.\-]|$)")


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()

def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _row_is_empty(row: list[Any]) -> bool:
    return not any(_as_text(v) for v in row)


def _flatten_header(rows: list[list[Any]], column_count: int) -> list[str]:
    """Flatten two/three level headers and approximate horizontal merged cells."""
    inherited = [""] * column_count
    parts: list[list[str]] = [[] for _ in range(column_count)]
    for row in rows:
        current = ""
        for col in range(column_count):
            text = _as_text(row[col] if col < len(row) else "")
            if text:
                current = text
                inherited[col] = text
            elif current:
                inherited[col] = current
            inherited_text = inherited[col]
            if inherited_text:
                norm = normalize_text(inherited_text)
                if norm and all(normalize_text(existing) != norm for existing in parts[col]):
                    parts[col].append(inherited_text)
    return [" | ".join(values) for values in parts]


def _header_score(flat: list[str]) -> int:
    joined = " | ".join(normalize_text(value) for value in flat)
    score = sum(3 for term in _HEADER_TERMS if normalize_text(term) in joined)
    populated = sum(bool(normalize_text(v)) for v in flat)
    if "stt" in joined:
        score += 8
    if "dien giai" in joined or "noi dung cong viec" in joined or "danh muc" in joined:
        score += 8
    if "don gia" in joined or "thanh tien" in joined:
        score += 6
    return score + min(populated, 20)


def detect_header(buffer: list[list[Any]], max_header_depth: int = 3) -> tuple[int, int, list[str]]:
    if not buffer:
        raise ValueError("Sheet không có dữ liệu")
    max_cols = max(len(row) for row in buffer)
    best: tuple[int, int, int, list[str]] | None = None
    scan_limit = min(len(buffer), 60)
    for start in range(scan_limit):
        if sum(bool(_as_text(v)) for v in buffer[start]) < 2:
            continue
        for depth in range(1, max_header_depth + 1):
            end = start + depth
            if end > scan_limit:
                break
            flat = _flatten_header(buffer[start:end], max_cols)
            score = _header_score(flat)
            # Prefer deeper two-level headers when the extra row adds useful labels.
            candidate = (score, -depth, -start, flat)
            if best is None or candidate[:3] > best[:3]:
                best = candidate
    if best is None or best[0] < 16:
        raise ValueError("Không tự nhận diện được hàng tiêu đề")
    depth, start = -best[1], -best[2]
    return start, start + depth - 1, best[3]


def _has(text: str, *parts: str) -> bool:
    norm = normalize_name(text)
    return all(normalize_name(part) in norm for part in parts)


def map_columns(flat_headers: list[str], role: DocumentRole) -> tuple[dict[int, str], dict[int, str]]:
    """Return fixed field mapping and dynamic technical columns.

    Multiple quantity/amount columns are retained explicitly. This is essential
    for real bidding sheets where KL mời thầu and KL nhà thầu chào coexist.
    """
    fixed: dict[int, str] = {}
    candidates: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for col, raw in enumerate(flat_headers):
        text = strip_accents(normalize_text(raw))
        if not text:
            continue
        material_group = "thong tin ve vat lieu chinh" in text

        if re.search(r"\bstt\b", text):
            candidates["stt"].append((100, col)); continue
        if any(term in text for term in ("dien giai", "noi dung cong viec", "danh muc quat thong gio", "ten hang muc")):
            candidates["item_name"].append((100, col)); continue
        if ("don vi" in text or re.search(r"\bdvt\b", text)) and "don gia" not in text:
            candidates["unit"].append((95, col)); continue

        if "kl nha thau" in text or "khoi luong nha thau" in text:
            candidates["bid_quantity"].append((110, col)); continue
        if "kl moi thau" in text or "khoi luong moi thau" in text:
            priority = 110 if "lan 2" in text else (90 if "bim" in text else 80)
            candidates["reference_quantity"].append((priority, col)); continue

        if material_group and ("mo ta quy cach" in text or text.endswith("quy cach")):
            candidates["material"].append((110, col)); continue
        if material_group and "ma hieu" in text:
            candidates["item_code"].append((110, col)); continue
        if material_group and "thuong hieu" in text:
            candidates["brand"].append((110, col)); continue
        if material_group and "xuat xu" in text:
            candidates["origin"].append((110, col)); continue

        if "vl chinh" in text and "don gia" in text:
            candidates["price_main"].append((110, col)); continue
        if "vl phu" in text and "don gia" in text:
            candidates["price_aux"].append((110, col)); continue
        if ("nc m" in text or "nhan cong" in text) and "don gia" in text:
            candidates["price_labor"].append((110, col)); continue
        if "cf quan ly" in text or "chi phi quan ly" in text:
            candidates["price_management"].append((110, col)); continue
        if "loi nhuan" in text:
            candidates["price_profit"].append((110, col)); continue
        if "dg tong hop" in text or "don gia tong hop" in text:
            candidates["unit_price_total"].append((120, col)); continue

        if "thanh tien" in text and ("nha thau" in text or "hsdt" in text):
            candidates["bid_amount"].append((120, col)); continue
        if "thanh tien" in text and ("klmt" in text or "moi thau" in text or "boq" in text):
            # BOQ is a group parent, but row 7 differentiates KLMT/HSDT.
            priority = 115 if "klmt" in text or "moi thau" in text else 70
            candidates["reference_amount"].append((priority, col)); continue

        if "ghi chu" in text:
            candidates["note"].append((70 if col < 10 else 60, col)); continue

        # Generic files without the Hacom multi-level header.
        if "ma hieu" in text or "ma cong tac" in text:
            candidates["item_code"].append((70, col)); continue
        if "don gia" in text and not any(x in text for x in ("vl chinh", "vl phu", "nc m", "quan ly", "loi nhuan")):
            candidates["unit_price_total"].append((70, col)); continue
        if "thanh tien" in text:
            field = "bid_amount" if role is DocumentRole.HSDT else "reference_amount"
            candidates[field].append((60, col)); continue
        if "khoi luong" in text or re.search(r"\bkl\b", text):
            field = "bid_quantity" if role is DocumentRole.HSDT else "reference_quantity"
            candidates[field].append((50, col)); continue
        if "quy cach" in text or "vat tu" in text or "vat lieu" in text:
            candidates["material"].append((50, col)); continue
        if "thuong hieu" in text or "nhan hieu" in text:
            candidates["brand"].append((60, col)); continue
        if "xuat xu" in text:
            candidates["origin"].append((60, col)); continue

    used_cols: set[int] = set()
    for field, values in candidates.items():
        score, col = max(values, key=lambda pair: (pair[0], -pair[1]))
        if col not in used_cols:
            fixed[col] = field
            used_cols.add(col)

    technical: dict[int, str] = {}
    noise = (
        "cong ty", "lien danh", "khoi luong moi thau", "thong tin ve vat lieu chinh",
        "don gia chua bao gom vat", "thanh tien boq",
    )
    for col, raw in enumerate(flat_headers):
        if col in fixed:
            continue
        text = strip_accents(normalize_text(raw))
        if not text or any(text == value or text.endswith(value) for value in noise):
            continue
        if any(term in text for term in ("cong suat", "luu luong", "cot ap", "dien ap", "nguon dien", "moi chat", "do on", "hieu suat", "toc do", "nhiet do", "ky hieu", "quy cach", "tang h", "tang1", "tang2", "tang3", "tang4", "tang5", "tang23")):
            label = raw.split("|")[-1].strip() or raw.strip()
            technical[col] = label
    return fixed, technical


def _is_numbering_row(row: list[Any]) -> bool:
    """Detect the column-number legend, never ordinary priced rows."""
    values = [_as_text(value) for value in row if _as_text(value)]
    if len(values) < 4:
        return False
    first_four = []
    for value in values[:4]:
        match = re.match(r"^(\d+)", value)
        first_four.append(int(match.group(1)) if match else None)
    if first_four != [1, 2, 3, 4]:
        return False
    labels = sum(bool(re.match(r"^\d+(?:\s*=.*)?$", value)) for value in values)
    return labels / len(values) >= 0.70


def _section_level(stt: str, name: str) -> int:
    value = normalize_stt(stt)
    if _ALPHA.match(value):
        return 0
    if _ROMAN.match(value):
        return 1
    if _NUM_SECTION.match(value):
        return min(2 + value.count("."), 5)
    # Unnumbered headings are nested under the current top-level section.
    return 3 if len(name) < 160 else 4


def _looks_group(
    stt: str,
    name: str,
    unit: str,
    ref_qty: Optional[float],
    bid_qty: Optional[float],
    unit_price: Optional[float],
    ref_amount: Optional[float],
    bid_amount: Optional[float],
) -> bool:
    if not name:
        return False
    if any(value is not None for value in (ref_qty, bid_qty, unit_price, ref_amount, bid_amount)) or unit:
        return False
    return len(name.strip()) < 220



def list_sheets(path: str | Path, *, engine: str = "calamine") -> list[dict[str, Any]]:
    return list_sheets_fast(path, engine=engine)


def load_workbook_items(
    path: str | Path,
    role: DocumentRole,
    bidder: str = "",
    selected_sheets: Optional[list[str]] = None,
    max_rows: int = 1_000_000,
    *,
    read_engine: str = "calamine",
    fallback_openpyxl: bool = True,
    scan_formulas: bool = True,
    scan_external_links: bool = True,
) -> WorkbookData:
    path = Path(path)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Hệ thống nhận file .xlsx. Hãy Save As file .xls/.xlsb thành .xlsx trước khi chạy.")

    source_id = file_sha256(path)[:16]
    bidder_name = bidder or ("HSMT" if role is DocumentRole.HSMT else path.stem)
    matrices = read_workbook_matrices(
        path,
        engine=read_engine,
        selected_sheets=selected_sheets,
        max_rows=max_rows,
        fallback_openpyxl=fallback_openpyxl,
    )
    scan = scan_xlsx_issues(
        path,
        selected_sheets=selected_sheets,
        scan_formulas=scan_formulas,
        scan_external_links=scan_external_links,
    )
    issues_by_row = scan.issues_by_row

    items: list[ItemRecord] = []
    warnings: list[str] = list(matrices.warnings) + list(scan.warnings)
    sheet_info: list[dict[str, Any]] = []
    totals: dict[str, float] = defaultdict(float)
    skipped_normalized = {normalize_name(value) for value in SKIP_SHEETS}

    if scan.issues:
        formula_count = sum(issue.kind == "FORMULA_ERROR" for issue in scan.issues)
        external_formula_count = sum(issue.kind == "EXTERNAL_LINK" for issue in scan.issues)
        if formula_count:
            warnings.append(f"Phát hiện {formula_count} ô lỗi công thức (#REF!, #DIV/0!, #VALUE!, ...); các dòng liên quan được đánh dấu BẤT THƯỜNG.")
        if scan.external_link_count or external_formula_count:
            warnings.append(
                f"Phát hiện liên kết workbook bên ngoài: {scan.external_link_count} externalLink và "
                f"{external_formula_count} công thức tham chiếu ngoài; cần xác nhận file nguồn."
            )
        for issue in scan.issues[:100]:
            warnings.append(f"{issue.sheet}!{issue.cell}: {issue.message}")
        if len(scan.issues) > 100:
            warnings.append(f"Còn {len(scan.issues) - 100} lỗi/liên kết khác; xem sheet AI_KIEM_TRA trong file đã đánh dấu.")

    for sheet in matrices.sheets:
        sheet_norm = normalize_name(sheet.name)
        if selected_sheets is not None and sheet.name not in selected_sheets:
            continue
        if selected_sheets is None and sheet_norm in skipped_normalized:
            continue
        if not sheet.rows:
            continue

        buffer_rows = sheet.rows[:90]
        try:
            start, end, flat_headers = detect_header(buffer_rows)
            mapping, technical_columns = map_columns(flat_headers, role)
        except ValueError as exc:
            warnings.append(f"Sheet '{sheet.name}': {exc}")
            continue

        if "item_name" not in mapping.values():
            warnings.append(f"Sheet '{sheet.name}': không xác định được cột tên hạng mục")
            continue

        field_columns = {field: col + 1 for col, field in mapping.items()}
        sheet_info.append({
            "sheet": sheet.name,
            "header_start": start + 1,
            "header_end": end + 1,
            "mapped_columns": {flat_headers[col]: field for col, field in mapping.items()},
            "field_columns": field_columns,
            "technical_columns": {flat_headers[col]: label for col, label in technical_columns.items()},
            "technical_field_columns": {label: col + 1 for col, label in technical_columns.items()},
            "max_column": len(flat_headers),
            "read_engine": matrices.engine,
            "source_rows": sheet.row_count,
            "source_columns": sheet.col_count,
        })

        section_stack: list[str] = []
        section_code_stack: list[str] = []
        current_parent_detail = ""
        current_parent_code = ""
        empty_streak = 0
        processed = 0
        has_unit_price_column = "unit_price_total" in field_columns
        has_amount_column = "reference_amount" in field_columns or "bid_amount" in field_columns

        for row_index in range(end + 1, len(sheet.rows)):
            row_number = row_index + 1
            row = sheet.rows[row_index]
            if _is_numbering_row(row):
                continue
            if _row_is_empty(row):
                empty_streak += 1
                if empty_streak > 250:
                    break
                continue
            empty_streak = 0
            processed += 1
            if processed > max_rows:
                warnings.append(f"Sheet '{sheet.name}' vượt giới hạn {max_rows:,} dòng")
                break

            values: dict[str, Any] = {field: (row[col] if col < len(row) else None) for col, field in mapping.items()}
            stt = _as_text(values.get("stt"))
            name = _as_text(values.get("item_name"))
            code = _as_text(values.get("item_code"))
            unit = _as_text(values.get("unit"))
            if not name and not code:
                continue

            ref_qty = parse_number(values.get("reference_quantity"))
            bid_qty = parse_number(values.get("bid_quantity"))
            price_main = parse_number(values.get("price_main"))
            price_aux = parse_number(values.get("price_aux"))
            price_labor = parse_number(values.get("price_labor"))
            price_management = parse_number(values.get("price_management"))
            price_profit = parse_number(values.get("price_profit"))
            unit_price_total = parse_number(values.get("unit_price_total"))
            if unit_price_total is None:
                components = [price_main, price_aux, price_labor, price_management, price_profit]
                if any(value is not None for value in components):
                    unit_price_total = sum(value or 0.0 for value in components)

            raw_ref_amount = parse_number(values.get("reference_amount"))
            raw_bid_amount = parse_number(values.get("bid_amount"))
            reference_amount = safe_amount(ref_qty, unit_price_total, raw_ref_amount)
            bid_amount = safe_amount(bid_qty, unit_price_total, raw_bid_amount)

            summary = (
                not unit
                and not stt
                and any(token in normalize_name(name) for token in ("tong cong", "tong truoc thue", "thue vat", "tong sau thue"))
                and (raw_ref_amount is not None or raw_bid_amount is not None)
            )
            group = _looks_group(stt, name, unit, ref_qty, bid_qty, unit_price_total, raw_ref_amount, raw_bid_amount)
            normalized_stt = normalize_stt(stt)

            if summary:
                row_type = RowType.SUMMARY
                current_parent_detail = ""
                current_parent_code = ""
            elif group:
                level = _section_level(stt, name)
                if len(section_stack) <= level:
                    section_stack.extend([""] * (level + 1 - len(section_stack)))
                    section_code_stack.extend([""] * (level + 1 - len(section_code_stack)))
                section_stack[level] = name
                section_code_stack[level] = normalized_stt
                del section_stack[level + 1:]
                del section_code_stack[level + 1:]
                current_parent_detail = ""
                current_parent_code = ""
                row_type = RowType.GROUP
            else:
                row_type = RowType.DETAIL if normalized_stt else RowType.COMPONENT
                if row_type is RowType.DETAIL:
                    current_parent_detail = name
                    current_parent_code = normalized_stt or normalize_code(code)

            path_parts = tuple(value for value in section_stack if value)
            code_parts = tuple(value for value in section_code_stack if value)
            if row_type is RowType.COMPONENT and current_parent_detail:
                path_parts = path_parts + (current_parent_detail,)
                code_parts = code_parts + (current_parent_code,)

            technical_specs: dict[str, Any] = {}
            for col, label in technical_columns.items():
                value = row[col] if col < len(row) else None
                if _as_text(value):
                    technical_specs[label] = value

            quality: list[str] = list(issues_by_row.get((sheet.name, row_number), []))
            for col, value in enumerate(row[:len(flat_headers)], start=1):
                if isinstance(value, str) and _FORMULA_ERROR.search(value):
                    quality.append(f"Lỗi dữ liệu tại cột {col}: {value}")

            if row_type in {RowType.DETAIL, RowType.COMPONENT}:
                quantity = bid_qty if role is DocumentRole.HSDT else ref_qty
                amount = bid_amount if role is DocumentRole.HSDT else reference_amount
                if row_type is RowType.DETAIL:
                    if quantity is None:
                        quality.append("Thiếu khối lượng")
                    if has_unit_price_column and unit_price_total is None:
                        quality.append("Thiếu đơn giá tổng hợp")
                    if has_amount_column and amount is None:
                        quality.append("Thiếu thành tiền")
                elif unit and quantity is None:
                    quality.append("Thiếu khối lượng cấu thành")

                if has_unit_price_column and has_amount_column:
                    err = math_error(quantity, unit_price_total, amount)
                    if err is not None:
                        quality.append(f"Sai phép tính KL×ĐG, lệch {err:,.0f}")
                component_values = [price_main, price_aux, price_labor, price_management, price_profit]
                if unit_price_total is not None and any(v is not None for v in component_values):
                    component_sum = sum(v or 0.0 for v in component_values)
                    scale = max(abs(unit_price_total), abs(component_sum), 1.0)
                    if abs(component_sum - unit_price_total) / scale > 0.005:
                        quality.append(f"Tổng 5 thành phần giá lệch ĐG tổng hợp {component_sum - unit_price_total:+,.0f}")

            normalized_path = normalize_name(" | ".join(path_parts))
            normalized_name = normalize_name(name)
            structural_key = "::".join(filter(None, [
                normalize_name(sheet.name),
                normalized_path,
                normalized_stt or normalize_code(code),
                normalized_name if row_type is RowType.COMPONENT else "",
                row_type.value,
            ]))

            item = ItemRecord(
                source_id=source_id,
                role=role,
                bidder=bidder_name,
                workbook=path.name,
                sheet=sheet.name,
                row_number=row_number,
                stt=stt,
                item_code=code,
                item_name=name,
                unit=unit,
                reference_quantity=ref_qty,
                bid_quantity=bid_qty,
                price_main=price_main,
                price_aux=price_aux,
                price_labor=price_labor,
                price_management=price_management,
                price_profit=price_profit,
                unit_price_total=unit_price_total,
                reference_amount=reference_amount,
                bid_amount=bid_amount,
                material=_as_text(values.get("material")),
                brand=_as_text(values.get("brand")),
                origin=_as_text(values.get("origin")),
                note=_as_text(values.get("note")),
                technical_specs=technical_specs,
                section_path=path_parts,
                section_codes=code_parts,
                row_type=row_type,
                raw={flat_headers[col]: _as_text(row[col] if col < len(row) else None) for col in range(len(flat_headers))},
                normalized_stt=normalized_stt,
                normalized_code=normalize_code(code),
                normalized_name=normalized_name,
                normalized_unit=normalize_unit(unit),
                normalized_path=normalized_path,
                structural_key=structural_key,
                data_quality_flags=list(dict.fromkeys(quality)),
            )
            items.append(item)
            if row_type is RowType.DETAIL and item.amount is not None:
                totals[sheet.name] += item.amount

    by_code: dict[tuple[str, str], list[ItemRecord]] = defaultdict(list)
    for item in items:
        if item.is_comparable and item.normalized_code:
            by_code[(normalize_name(item.sheet), item.normalized_code)].append(item)
    for (_, code), duplicated in by_code.items():
        distinct_names = {item.normalized_name for item in duplicated if item.normalized_name}
        if len(duplicated) > 1 and len(distinct_names) > 1:
            rows = ", ".join(str(item.row_number) for item in duplicated[:20])
            flag = f"Mã hiệu trùng nhưng mô tả khác nhau ({code}), các dòng: {rows}"
            for item in duplicated:
                item.data_quality_flags.append(flag)
            warnings.append(f"Sheet '{duplicated[0].sheet}': {flag}")

    by_structure: dict[str, list[ItemRecord]] = defaultdict(list)
    for item in items:
        if item.is_comparable and item.structural_key:
            by_structure[item.structural_key].append(item)
    for key, duplicated in by_structure.items():
        if len(duplicated) > 1:
            warnings.append(
                f"Sheet '{duplicated[0].sheet}': khóa cấu trúc lặp {len(duplicated)} lần; "
                f"giữ nguyên từng dòng ({', '.join(str(x.row_number) for x in duplicated[:10])})"
            )

    if not items:
        warnings.append("Không đọc được hạng mục dữ liệu nào từ workbook")
    return WorkbookData(
        path=path,
        role=role,
        bidder=bidder_name,
        items=items,
        warnings=warnings,
        sheet_info=sheet_info,
        totals=dict(totals),
        read_engine=matrices.engine,
        read_seconds=matrices.elapsed_seconds,
        formula_issues=[issue.to_dict() for issue in scan.issues],
        external_link_count=scan.external_link_count,
    )
