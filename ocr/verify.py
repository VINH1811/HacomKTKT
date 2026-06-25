from __future__ import annotations

import itertools
from collections import defaultdict
from typing import Any

from core.number_parser import math_error, parse_number, safe_amount

from .config import OCRConfig
from .models import OCRCandidate, OCRCell, OCRTable
from .schema import NUMERIC_FIELDS, label_for


REQUIRED_ITEM_FIELDS = {"item_name", "unit_price"}
COMPONENT_FIELDS = ["main_material", "aux_material", "labor_machine", "management_cost", "profit"]


def _candidate_numbers(cell: OCRCell, limit: int = 5) -> list[tuple[float, float, str]]:
    values: dict[float, tuple[float, str]] = {}
    source = list(cell.candidates)
    if cell.text:
        source.append(OCRCandidate(cell.text, cell.confidence, cell.engine, "selected"))
    for candidate in source:
        value = parse_number(candidate.text)
        if value is None:
            continue
        previous = values.get(value)
        if previous is None or candidate.confidence > previous[0]:
            values[value] = (candidate.confidence, candidate.text)
    ranked = sorted(
        ((value, confidence, text) for value, (confidence, text) in values.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:limit]


def _relative_error(expected: float, actual: float) -> float:
    return abs(expected - actual) / max(abs(expected), abs(actual), 1.0)


def _reconcile_equation(
    fields: tuple[str, str, str],
    cells: dict[str, OCRCell],
    tolerance: float,
) -> tuple[dict[str, float], float] | None:
    options: list[list[tuple[float, float, str]]] = []
    for field in fields:
        cell = cells.get(field)
        if cell is None:
            return None
        candidates = _candidate_numbers(cell)
        if not candidates:
            return None
        options.append(candidates)

    best: tuple[float, dict[str, float]] | None = None
    for combo in itertools.product(*options):
        first, second, result = combo
        error = _relative_error(first[0] * second[0], result[0])
        confidence_penalty = sum(1.0 - value[1] for value in combo) / len(combo)
        score = error * 5.0 + confidence_penalty * 0.15
        values = {field: combo[index][0] for index, field in enumerate(fields)}
        if best is None or score < best[0]:
            best = (score, values)
    if best is None:
        return None
    values = best[1]
    error = _relative_error(values[fields[0]] * values[fields[1]], values[fields[2]])
    if error <= max(tolerance * 2.0, 0.015):
        return values, error
    return None


def _apply_reconciliation(record: dict[str, Any], cells: dict[str, OCRCell], config: OCRConfig) -> None:
    equations = [
        ("invited_quantity", "unit_price", "amount_invited"),
        ("bid_quantity", "unit_price", "amount_bid"),
    ]
    for equation in equations:
        present = all(record.get(field) is not None for field in equation)
        current_error = None
        if present:
            current_error = _relative_error(
                float(record[equation[0]]) * float(record[equation[1]]),
                float(record[equation[2]]),
            )
        if present and current_error is not None and current_error <= config.math_tolerance_pct:
            continue
        repaired = _reconcile_equation(equation, cells, config.math_tolerance_pct)
        if repaired is None:
            continue
        values, error = repaired
        changed: list[str] = []
        for field, value in values.items():
            old = record.get(field)
            if old is None or abs(float(old) - value) > max(1e-9, abs(value) * 1e-9):
                record[field] = value
                cell = cells[field]
                cell.numeric_value = value
                cell.reconciled = True
                changed.append(label_for(field))
        if changed:
            record["ocr_flags"].append(
                "Tự chọn lại ứng viên OCR theo phép tính "
                f"{label_for(equation[0])} × {label_for(equation[1])} = {label_for(equation[2])}; "
                f"đã đổi: {', '.join(changed)}. Cần xác nhận bằng ảnh gốc."
            )


def _verify_components(record: dict[str, Any], config: OCRConfig) -> None:
    components = [record.get(field) for field in COMPONENT_FIELDS]
    if record.get("unit_price") is None or not any(value is not None for value in components):
        return
    total = sum(float(value or 0.0) for value in components)
    error = _relative_error(total, float(record["unit_price"]))
    record["computed_unit_price"] = total
    if error > config.component_tolerance_pct:
        record["ocr_flags"].append(
            f"Tổng 5 thành phần đơn giá = {total:,.0f}, khác đơn giá tổng hợp "
            f"{float(record['unit_price']):,.0f} ({error:.2%})."
        )


def assemble_rows(table: OCRTable, config: OCRConfig) -> list[dict[str, Any]]:
    grouped: dict[int, list[OCRCell]] = defaultdict(list)
    for cell in table.cells:
        if cell.row >= table.header_rows:
            grouped[cell.row].append(cell)

    rows: list[dict[str, Any]] = []
    for row_index in sorted(grouped):
        row_cells = sorted(grouped[row_index], key=lambda cell: cell.col)
        record: dict[str, Any] = {
            "page": table.page,
            "table": table.table_index,
            "table_row": row_index,
            "ocr_confidence": 1.0,
            "ocr_status": "OK",
            "ocr_flags": [],
            "raw_columns": {},
            "table_source": table.source,
        }
        cells_by_field: dict[str, OCRCell] = {}
        nonblank_confidences: list[float] = []
        for cell in row_cells:
            field = table.column_fields.get(cell.col, f"col_{cell.col + 1}")
            cell.field = field
            cells_by_field[field] = cell
            record["raw_columns"][field] = cell.text
            if field in NUMERIC_FIELDS:
                cell.numeric_value = parse_number(cell.text)
                record[field] = cell.numeric_value
            else:
                record[field] = cell.text
            if cell.text:
                nonblank_confidences.append(cell.confidence)
            if cell.review_reason:
                record["ocr_flags"].append(f"{label_for(field)}: {cell.review_reason}")

        record["ocr_confidence"] = min(nonblank_confidences) if nonblank_confidences else 0.0
        meaningful = any(
            (value is not None and value != "")
            for key, value in record.items()
            if key not in {"raw_columns", "ocr_flags", "ocr_status", "ocr_confidence", "table_source"}
        )
        if not meaningful:
            continue

        name = str(record.get("item_name", "") or "").strip()
        financial_values = [record.get(field) for field in NUMERIC_FIELDS]
        record["is_group"] = bool(name and not any(value is not None for value in financial_values))

        if not record["is_group"]:
            for field in REQUIRED_ITEM_FIELDS:
                value = record.get(field)
                if value is None or (isinstance(value, str) and not value.strip()):
                    record["ocr_flags"].append(f"Thiếu trường bắt buộc: {label_for(field)}")

            if config.use_arithmetic_reconciliation:
                _apply_reconciliation(record, cells_by_field, config)

            for quantity, amount in (
                ("invited_quantity", "amount_invited"),
                ("bid_quantity", "amount_bid"),
            ):
                q, p, a = record.get(quantity), record.get("unit_price"), record.get(amount)
                error = math_error(q, p, a, config.math_tolerance_pct)
                if error is not None:
                    record["ocr_flags"].append(
                        f"Sai {label_for(quantity)} × Đơn giá = {label_for(amount)}, lệch {error:,.0f}."
                    )
                record[f"computed_{amount}"] = safe_amount(q, p, None)
            # Tương thích cột generic của phiên bản cũ.
            record["quantity"] = (
                record.get("invited_quantity")
                if record.get("invited_quantity") is not None
                else record.get("bid_quantity")
            )
            record["amount"] = (
                record.get("amount_bid")
                if record.get("amount_bid") is not None
                else record.get("amount_invited")
            )
            record["computed_amount"] = (
                record.get("computed_amount_bid")
                if record.get("computed_amount_bid") is not None
                else record.get("computed_amount_invited")
            )
            _verify_components(record, config)

        if record["ocr_flags"]:
            record["ocr_status"] = "CẦN KIỂM TRA"
        rows.append(record)
    return rows


def update_cell_status(cell: OCRCell, config: OCRConfig, numeric: bool) -> None:
    if not cell.text:
        cell.status = "empty"
        cell.review_reason = "Ô trống/không đọc được"
        return
    threshold = config.min_numeric_confidence if numeric else config.min_text_confidence
    if cell.confidence < threshold:
        cell.status = "low_confidence"
        cell.review_reason = f"Độ tin cậy thấp {cell.confidence:.1%}"
    else:
        cell.status = "ok"
        cell.review_reason = ""
    if numeric and parse_number(cell.text) is None:
        cell.status = "invalid_number"
        cell.review_reason = f"Không chuẩn hóa được số: {cell.text}"
