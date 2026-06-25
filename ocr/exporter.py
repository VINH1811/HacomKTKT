from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import Any

import cv2
import xlsxwriter

from .models import OCRDocument, OCRTable
from .schema import FIELD_LABELS


def _safe_text(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _sheet_name(value: str, used: set[str]) -> str:
    base = re.sub(r"[\[\]:*?/\\]", "_", value).strip()[:31] or "Sheet"
    candidate = base
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = base[:31 - len(suffix)] + suffix
        index += 1
    used.add(candidate)
    return candidate


def _write_title(worksheet, title: str, columns: int, title_format) -> None:
    worksheet.merge_range(0, 0, 0, max(0, columns - 1), title, title_format)
    worksheet.set_row(0, 28)


def _row_headers() -> list[tuple[str, str]]:
    return [
        ("page", "Trang"),
        ("table", "Bảng"),
        ("table_row", "Dòng bảng"),
        ("stt", "STT"),
        ("item_code", "Mã công tác"),
        ("item_name", "Mô tả công việc mời thầu"),
        ("unit", "ĐVT"),
        ("invited_quantity", "KL theo KLMT"),
        ("bid_quantity", "KL nhà thầu chào"),
        ("material", "Mô tả quy cách"),
        ("product_code", "Mã hiệu/Model"),
        ("brand", "Thương hiệu"),
        ("origin", "Xuất xứ"),
        ("main_material", "VL chính"),
        ("aux_material", "VL phụ"),
        ("labor_machine", "NC & máy TC"),
        ("management_cost", "CP quản lý"),
        ("profit", "Lợi nhuận"),
        ("unit_price", "Đơn giá tổng hợp"),
        ("amount_invited", "Thành tiền theo KLMT"),
        ("computed_amount_invited", "TT theo KLMT tính lại"),
        ("amount_bid", "Thành tiền nhà thầu chào"),
        ("computed_amount_bid", "TT nhà thầu tính lại"),
        ("computed_unit_price", "Đơn giá 5 thành phần tính lại"),
        ("note", "Ghi chú"),
        ("ocr_confidence", "Độ tin cậy OCR"),
        ("table_source", "Nguồn nhận dạng"),
        ("ocr_status", "Trạng thái OCR"),
        ("ocr_flags", "Lý do kiểm tra"),
    ]


def _cell_image(document: OCRDocument, page_number: int, bbox: tuple[int, int, int, int]) -> bytes | None:
    if page_number < 1 or page_number > len(document.pages):
        return None
    x, y, width, height = bbox
    if width <= 0 or height <= 0:
        return None
    image = document.pages[page_number - 1].image
    crop = image[max(0, y):max(0, y) + height, max(0, x):max(0, x) + width]
    if crop.size == 0:
        return None
    max_width = 900
    if crop.shape[1] > max_width:
        scale = max_width / crop.shape[1]
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".png", crop)
    return encoded.tobytes() if ok else None


def export_ocr_document(
    document: OCRDocument,
    output_path: str | Path,
    include_review_images: bool = True,
) -> str:
    output_path = str(output_path)
    workbook = xlsxwriter.Workbook(
        output_path,
        {
            "constant_memory": True,
            "strings_to_formulas": False,
            "strings_to_urls": False,
            "nan_inf_to_errors": True,
        },
    )
    title = workbook.add_format({
        "bold": True, "font_size": 16, "font_color": "#FFFFFF",
        "bg_color": "#17365D", "align": "center", "valign": "vcenter",
    })
    header = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78",
        "border": 1, "text_wrap": True, "align": "center", "valign": "vcenter",
    })
    subheader = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "align": "center", "valign": "vcenter",
    })
    text = workbook.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    centered = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
    number = workbook.add_format({"border": 1, "num_format": "#,##0.####;[Red]-#,##0.####"})
    money = workbook.add_format({"border": 1, "num_format": "#,##0;[Red]-#,##0"})
    percent = workbook.add_format({"border": 1, "num_format": "0.0%"})
    ok = workbook.add_format({"border": 1, "bg_color": "#E2F0D9", "font_color": "#375623"})
    review = workbook.add_format({
        "border": 1, "bg_color": "#FFF2CC", "font_color": "#7F6000", "text_wrap": True,
    })
    critical = workbook.add_format({
        "border": 1, "bg_color": "#F4CCCC", "font_color": "#9C0006", "text_wrap": True,
    })
    mono = workbook.add_format({
        "font_name": "Consolas", "font_size": 9, "text_wrap": True,
        "valign": "top", "border": 1,
    })

    used_names: set[str] = set()

    # 1) Tổng quan chất lượng.
    summary_ws = workbook.add_worksheet(_sheet_name("Tổng quan OCR", used_names))
    summary_ws.set_column("A:A", 34)
    summary_ws.set_column("B:B", 26)
    summary_ws.set_column("C:C", 86)
    _write_title(summary_ws, "TỔNG QUAN KẾT QUẢ OCR", 3, title)
    summary_ws.write_row(2, 0, ["Chỉ số", "Giá trị", "Giải thích"], header)
    summary_rows = [
        ("Tệp nguồn", document.source_path.name, "File PDF/ảnh đã xử lý"),
        ("Số trang", document.summary.get("pages", len(document.pages)), "Tổng số trang ảnh/PDF"),
        ("Số bảng", document.summary.get("tables", 0), "Bảng được phát hiện hoặc trích xuất"),
        ("Số dòng dữ liệu", document.summary.get("rows", len(document.rows)), "Không tính dòng tiêu đề"),
        ("Số ô có nội dung", document.summary.get("nonblank_cells", 0), "Ô OCR không trống"),
        ("Ô cần kiểm tra", document.summary.get("review_cells", 0), "Confidence thấp, không đọc được hoặc model không có confidence cấp ô"),
        ("Dòng cần kiểm tra", document.summary.get("review_rows", 0), "Dòng thiếu dữ liệu hoặc sai kiểm tra nghiệp vụ"),
        ("Confidence trung bình", document.summary.get("average_confidence", 0.0), "Chỉ là tín hiệu hỗ trợ, không thay cho kiểm tra ảnh gốc"),
        ("Chế độ bảo mật", document.audit.get("privacy_mode", "LOCAL"), "Không gửi tài liệu ra dịch vụ cloud"),
        ("SHA-256", document.audit.get("source_sha256", ""), "Dùng để truy vết đúng file nguồn"),
    ]
    for row_index, (metric, value, explanation) in enumerate(summary_rows, start=3):
        summary_ws.write(row_index, 0, metric, text)
        if metric == "Confidence trung bình":
            summary_ws.write(row_index, 1, value, percent)
        else:
            summary_ws.write(row_index, 1, _safe_text(value), text)
        summary_ws.write(row_index, 2, explanation, text)
    warning_row = 3 + len(summary_rows) + 1
    summary_ws.write(warning_row, 0, "Cảnh báo", header)
    summary_ws.merge_range(warning_row, 1, warning_row, 2, "\n".join(document.warnings) or "Không có", review if document.warnings else ok)
    summary_ws.freeze_panes(3, 0)

    # 2) Dữ liệu chuẩn hóa.
    data_ws = workbook.add_worksheet(_sheet_name("Dữ liệu OCR", used_names))
    fields = _row_headers()
    _write_title(data_ws, "DỮ LIỆU OCR ĐÃ CHUẨN HÓA", len(fields), title)
    data_ws.write_row(1, 0, [label for _, label in fields], header)
    data_ws.set_row(1, 46)
    for column, (key, label) in enumerate(fields):
        width = 16
        if key in {"item_name", "material", "note", "ocr_flags"}:
            width = 42 if key != "ocr_flags" else 58
        elif key in {"brand", "origin", "product_code", "table_source"}:
            width = 24
        data_ws.set_column(column, column, width)
    for row_index, row in enumerate(document.rows, start=2):
        flags = " | ".join(row.get("ocr_flags", []))
        for column, (key, _) in enumerate(fields):
            value = flags if key == "ocr_flags" else row.get(key, "")
            cell_format = text
            if key in {
                "invited_quantity", "bid_quantity", "main_material", "aux_material",
                "labor_machine", "management_cost", "profit",
            }:
                cell_format = number
            elif key in {
                "unit_price", "amount_invited", "computed_amount_invited",
                "amount_bid", "computed_amount_bid", "computed_unit_price",
            }:
                cell_format = money
            elif key == "ocr_confidence":
                cell_format = percent
            elif key in {"ocr_status", "ocr_flags"}:
                cell_format = review if flags else ok
            data_ws.write(row_index, column, _safe_text(value), cell_format)
    data_ws.freeze_panes(2, 0)
    data_ws.autofilter(1, 0, max(2, len(document.rows) + 1), len(fields) - 1)

    # 3) Một sheet thô cho từng bảng, giữ đúng hàng/cột OCR.
    for page in document.pages:
        for table_index, table in enumerate(page.tables, start=1):
            raw_ws = workbook.add_worksheet(_sheet_name(f"P{page.page}_B{table_index}_THO", used_names))
            matrix = table.matrix()
            max_cols = max((len(row) for row in matrix), default=1)
            _write_title(
                raw_ws,
                f"TRANG {page.page} – BẢNG {table.table_index} – {table.source}",
                max_cols,
                title,
            )
            raw_ws.set_default_row(22)
            for column in range(max_cols):
                width = 13
                if column < table.n_cols and table.x_lines and len(table.x_lines) > column + 1:
                    pixel_width = table.x_lines[column + 1] - table.x_lines[column]
                    width = min(42, max(8, pixel_width / 7.2))
                raw_ws.set_column(column, column, width)
            cells = {(cell.row, cell.col): cell for cell in table.cells}
            for row_number, row in enumerate(matrix, start=1):
                for column, value in enumerate(row):
                    cell = cells.get((row_number - 1, column))
                    fmt = text
                    if row_number - 1 < table.header_rows:
                        fmt = subheader
                    elif cell and cell.review_reason:
                        fmt = review
                    raw_ws.write(row_number, column, _safe_text(value), fmt)
            raw_ws.freeze_panes(1 + table.header_rows, 0)

    # 4) Danh sách ô cần kiểm tra, có ảnh crop đặt cạnh kết quả.
    review_ws = workbook.add_worksheet(_sheet_name("Ô cần kiểm tra", used_names))
    review_headers = [
        "Trang", "Bảng", "Hàng", "Cột", "Trường", "Nội dung OCR",
        "Confidence", "Engine", "Lý do", "BBox", "Ảnh ô gốc",
    ]
    _write_title(review_ws, "Ô CẦN NGƯỜI DÙNG XÁC NHẬN", len(review_headers), title)
    review_ws.write_row(1, 0, review_headers, header)
    widths = [9, 9, 9, 9, 24, 42, 14, 26, 55, 24, 42]
    for column, width in enumerate(widths):
        review_ws.set_column(column, column, width)
    output_row = 2
    for page in document.pages:
        for table in page.tables:
            for cell in table.cells:
                if not cell.review_reason:
                    continue
                values = [
                    cell.page, cell.table_index, cell.row, cell.col,
                    FIELD_LABELS.get(cell.field, cell.field), cell.text,
                    cell.confidence, cell.engine, cell.review_reason,
                    str(cell.bbox), "",
                ]
                review_ws.set_row(output_row, 72)
                for column, value in enumerate(values):
                    fmt = review if column in {5, 8} else (percent if column == 6 else text)
                    review_ws.write(output_row, column, _safe_text(value), fmt)
                if include_review_images:
                    image = _cell_image(document, cell.page, cell.bbox)
                    if image:
                        review_ws.insert_image(
                            output_row, 10, "cell.png",
                            {"image_data": io.BytesIO(image), "x_scale": 0.45, "y_scale": 0.45, "object_position": 1},
                        )
                output_row += 1
    review_ws.freeze_panes(2, 0)
    if output_row > 2:
        review_ws.autofilter(1, 0, output_row - 1, len(review_headers) - 1)

    # 5) Nhật ký truy vết.
    audit_ws = workbook.add_worksheet(_sheet_name("Nhật ký OCR", used_names))
    audit_ws.set_column("A:A", 34)
    audit_ws.set_column("B:B", 110)
    _write_title(audit_ws, "NHẬT KÝ VÀ BẢO MẬT OCR", 2, title)
    audit_ws.write_row(1, 0, ["Thuộc tính", "Giá trị"], header)
    entries = {
        "Tệp nguồn": document.source_path.name,
        "Số trang": len(document.pages),
        "Số dòng trích xuất": len(document.rows),
        "Tóm tắt": json.dumps(document.summary, ensure_ascii=False, indent=2),
        "Cảnh báo": json.dumps(document.warnings, ensure_ascii=False, indent=2),
        "Audit": json.dumps(document.audit, ensure_ascii=False, indent=2),
        "Nguyên tắc": (
            "OCR hỗ trợ số hóa, không tự thay thế kiểm tra nghiệp vụ. Ô confidence thấp, "
            "ô tự hiệu chỉnh theo phép tính hoặc kết quả model fallback phải được xác nhận bằng ảnh gốc."
        ),
    }
    for row_index, (key, value) in enumerate(entries.items(), start=2):
        audit_ws.write(row_index, 0, key, text)
        audit_ws.write(row_index, 1, _safe_text(value), mono)
    audit_ws.freeze_panes(2, 0)

    workbook.close()
    return output_path
