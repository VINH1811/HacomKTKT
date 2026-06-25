from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Optional

import cv2
import numpy as np

from core.excel_reader import file_sha256

from .config import OCRConfig
from .engines import (
    FastCellRecognizer,
    PaddleOCRVLFallback,
    PaddleStructureFallback,
    PaddleTableFallback,
    clean_numeric,
    clean_text,
)
from .exporter import export_ocr_document
from .grid import build_table, crop_cell, detect_grids
from .models import OCRCandidate, OCRCell, OCRDocument, OCRPage, OCRTable
from .pdf_io import load_pages, rotate_image
from .orientation import probe_upright_pair
from .schema import infer_columns, infer_header_fields, infer_header_rows, is_numeric_field
from .verify import assemble_rows, update_cell_status

ProgressCallback = Callable[[int, str], None]


def _emit(callback: ProgressCallback | None, progress: int, message: str) -> None:
    if callback:
        callback(max(0, min(100, int(progress))), message)


def _ink_ratio(image: np.ndarray) -> float:
    if image.size == 0:
        return 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Bỏ viền ngoài để đường kẻ không làm ô trống thành ô có mực.
    h, w = binary.shape
    y1, y2 = max(0, int(h * 0.12)), min(h, int(h * 0.88))
    x1, x2 = max(0, int(w * 0.05)), min(w, int(w * 0.95))
    center = binary[y1:y2, x1:x2] if y2 > y1 and x2 > x1 else binary
    return float(np.count_nonzero(center) / max(center.size, 1))


def _recognize_header(
    table: OCRTable,
    image: np.ndarray,
    recognizer: FastCellRecognizer,
    config: OCRConfig,
) -> float:
    header_cells = [cell for cell in table.cells if cell.row < table.header_rows]
    if not header_cells:
        return table.structure_confidence
    crops = [crop_cell(image, cell) for cell in header_cells]
    outputs = recognizer.recognize_many(crops, [False] * len(crops))
    confidences: list[float] = []
    for cell, (best, candidates) in zip(header_cells, outputs):
        cell.text = best.text
        cell.confidence = best.confidence
        cell.engine = best.engine
        cell.candidates = candidates
        update_cell_status(cell, config, numeric=False)
        if best.text:
            confidences.append(best.confidence)
    semantic_mapping = infer_header_fields(table)
    infer_columns(table)
    # Chỉ trường được đọc thực sự từ tiêu đề mới được dùng để chấm chiều.
    # Positional schema vẫn được giữ để xử lý dữ liệu sau khi đã chọn đúng chiều.
    semantic_fields = len(set(semantic_mapping.values()))
    column_topology = min(1.0, table.n_cols / 18.0)
    meaningful_cells = sum(
        bool(cell.text) and any(char.isalpha() for char in cell.text)
        for cell in header_cells
    )
    return (
        table.structure_confidence * 1.0
        + semantic_fields * 0.42
        + min(0.50, meaningful_cells * 0.025)
        + column_topology * 0.30
        + (float(np.mean(confidences)) * 0.20 if confidences else 0.0)
    )


def _candidate_tables(
    page_number: int,
    image: np.ndarray,
    recognizer: FastCellRecognizer,
    config: OCRConfig,
    rotation_label: int,
) -> tuple[list[OCRTable], float]:
    detections = detect_grids(image, config)
    tables: list[OCRTable] = []
    total_score = 0.0
    for index, detection in enumerate(detections, start=1):
        debug_dir = ""
        if config.debug_dir:
            debug_dir = str(Path(config.debug_dir) / f"page_{page_number:03d}_rot_{rotation_label}_table_{index:02d}")
        table = build_table(page_number, index, image, detection, config, debug_dir=debug_dir)
        table.header_rows = infer_header_rows(table)
        score = _recognize_header(table, image, recognizer, config)
        tables.append(table)
        total_score += score + min(0.5, table.n_rows / 100.0)
    return tables, total_score


def _select_orientation_and_tables(
    page: OCRPage,
    recognizer: FastCellRecognizer,
    config: OCRConfig,
) -> list[OCRTable]:
    """Chọn chiều đọc 0/180 bằng ngữ nghĩa, sau đó mới OCR toàn bộ bảng.

    Hình học lưới hoàn toàn đối xứng khi xoay 180 độ. Tesseract OSD cũng thường
    nhận sai bảng có chữ rất nhỏ. Vì vậy vùng đầu trang được OCR nhanh để tìm
    các cụm như STT, Diễn giải, Khối lượng, Đơn giá, Thành tiền...
    """
    images = {0: page.image, 180: rotate_image(page.image, 180)}
    probes = probe_upright_pair(page.image, config)
    page.orientation_scores = {angle: round(probe.score, 3) for angle, probe in probes.items()}
    page.orientation_keywords = {angle: list(probe.keyword_hits) for angle, probe in probes.items()}

    available = all(probe.available for probe in probes.values())
    gap = abs(probes[0].score - probes[180].score) if available else 0.0
    if available and gap >= config.orientation_probe_min_gap:
        preferred = max(probes, key=lambda angle: probes[angle].score)
        order = [preferred, 180 if preferred == 0 else 0]
        page.orientation_method = "semantic-header-probe"
    else:
        order = [0, 180]
        page.orientation_method = "table-header-score"

    best_tables: list[OCRTable] = []
    best_image = page.image
    best_extra_rotation = 0
    best_score = -1.0
    for index, extra_rotation in enumerate(order):
        image = images[extra_rotation]
        tables, table_score = _candidate_tables(page.page, image, recognizer, config, extra_rotation)
        semantic_bonus = probes[extra_rotation].score * 0.08 if probes[extra_rotation].available else 0.0
        score = table_score + semantic_bonus
        if tables and score > best_score:
            best_tables = tables
            best_image = image
            best_extra_rotation = extra_rotation
            best_score = score
        # Khi probe có khoảng cách rõ và chiều ưu tiên đã phát hiện được bảng,
        # không OCR tiêu đề toàn bộ lần thứ hai. Điều này vừa nhanh vừa tránh
        # confidence giả của chữ lộn ngược lật ngược quyết định đúng.
        if index == 0 and best_tables and available and gap >= config.orientation_probe_min_gap:
            break

    if best_tables:
        page.image = best_image
        page.rotation = (page.rotation + best_extra_rotation) % 360
    return best_tables


def _recognize_data_cells(
    page: OCRPage,
    table: OCRTable,
    recognizer: FastCellRecognizer,
    config: OCRConfig,
) -> None:
    cells = [cell for cell in table.cells if cell.row >= table.header_rows]
    work_cells: list[OCRCell] = []
    crops: list[np.ndarray] = []
    numeric_flags: list[bool] = []
    for cell in cells:
        crop = crop_cell(page.image, cell)
        if _ink_ratio(crop) < 0.0045:
            cell.text = ""
            cell.confidence = 1.0
            cell.engine = "blank-detector"
            cell.status = "empty"
            cell.review_reason = ""
            continue
        field = table.column_fields.get(cell.col, f"col_{cell.col + 1}")
        cell.field = field
        work_cells.append(cell)
        crops.append(crop)
        numeric_flags.append(is_numeric_field(field))

    outputs = recognizer.recognize_many(crops, numeric_flags)
    for cell, numeric, (best, candidates) in zip(work_cells, numeric_flags, outputs):
        cell.text = best.text
        cell.confidence = best.confidence
        cell.engine = best.engine
        cell.candidates = candidates
        update_cell_status(cell, config, numeric=numeric)



def _reconcile_grid_with_vl(table: OCRTable, matrix: list[list[str]], config: OCRConfig) -> int:
    """Use PaddleOCR-VL-1.6 as an independent judge for weak/empty grid cells.

    The geometry remains from OpenCV, so VLM never moves rows or columns. It may
    fill an empty cell or flag disagreement, which is safer for financial tables.
    """
    rows = len(matrix)
    cols = max((len(row) for row in matrix), default=0)
    if cols != table.n_cols or abs(rows - table.n_rows) > max(4, int(table.n_rows * 0.08)):
        return 0
    by_pos = {(cell.row, cell.col): cell for cell in table.cells}
    changed = 0
    usable_rows = min(rows, table.n_rows)
    for row_index in range(usable_rows):
        padded = matrix[row_index] + [""] * (cols - len(matrix[row_index]))
        for col_index, raw in enumerate(padded):
            vl_text = str(raw or "").strip()
            if not vl_text:
                continue
            cell = by_pos.get((row_index, col_index))
            if cell is None or row_index < table.header_rows:
                continue
            numeric = is_numeric_field(table.column_fields.get(col_index, ""))
            normalize = clean_numeric if numeric else lambda value: clean_text(value).casefold()
            current_key = normalize(cell.text)
            vl_key = normalize(vl_text)
            if not vl_key:
                continue
            cell.candidates.append(OCRCandidate(vl_text, 0.74, "PaddleOCR-VL-1.6-local", "full-page-reconcile"))
            threshold = config.min_numeric_confidence if numeric else config.min_text_confidence
            if not current_key or cell.confidence < 0.50:
                cell.text = clean_numeric(vl_text) if numeric else clean_text(vl_text)
                cell.confidence = 0.74
                cell.engine = "PaddleOCR-VL-1.6-local"
                cell.reconciled = True
                update_cell_status(cell, config, numeric=numeric)
                cell.review_reason = "PaddleOCR-VL-1.6 đã điền ô trống/ô rất yếu; cần xác nhận ảnh gốc"
                changed += 1
            elif current_key != vl_key:
                reason = "PP-OCRv6 và PaddleOCR-VL-1.6 đọc khác nhau"
                cell.review_reason = f"{cell.review_reason}; {reason}".strip("; ")
                cell.status = "review"
                changed += 1
            elif cell.confidence < threshold:
                cell.confidence = min(0.99, cell.confidence + 0.08)
                cell.reconciled = True
                changed += 1
    if changed:
        table.warnings.append(f"PaddleOCR-VL-1.6 đã kiểm tra chéo {changed} ô; các ô bất đồng được giữ trong danh sách cần duyệt.")
    return changed

def _matrix_quality(matrix: list[list[str]]) -> tuple[int, int, int]:
    rows = len(matrix)
    cols = max((len(row) for row in matrix), default=0)
    nonblank = sum(bool(str(cell).strip()) for row in matrix for cell in row)
    return rows, cols, nonblank


def _table_from_matrix(
    page: OCRPage,
    table_index: int,
    matrix: list[list[str]],
    source: str,
    confidence: float,
) -> OCRTable:
    rows = len(matrix)
    cols = max((len(row) for row in matrix), default=0)
    table = OCRTable(
        page=page.page,
        table_index=table_index,
        bbox=(0, 0, page.image.shape[1], page.image.shape[0]),
        x_lines=list(range(cols + 1)),
        y_lines=list(range(rows + 1)),
        header_rows=min(4, max(1, 2 if rows > 3 else 1)),
        structure_confidence=confidence,
        source=source,
    )
    for row_index, row in enumerate(matrix):
        padded = row + [""] * (cols - len(row))
        for col_index, value in enumerate(padded):
            text = str(value or "").strip()
            cell = OCRCell(
                page=page.page,
                table_index=table_index,
                row=row_index,
                col=col_index,
                bbox=(0, 0, 0, 0),
                text=text,
                confidence=confidence if text else 1.0,
                engine=source,
                status="ok" if text else "empty",
            )
            if text and confidence < 0.80:
                cell.review_reason = f"Kết quả từ {source}, không có confidence cấp ô; cần kiểm tra"
            table.cells.append(cell)
    infer_columns(table)
    return table


def _best_structured_fallback(
    page: OCRPage,
    start_index: int,
    table_fallback: PaddleTableFallback,
    structure_fallback: PaddleStructureFallback,
    vl_fallback: PaddleOCRVLFallback,
) -> list[OCRTable]:
    candidates: list[tuple[tuple[int, int, int], str, float, list[list[list[str]]]]] = []
    if table_fallback.available:
        matrices = table_fallback.predict_matrices(page.image)
        score = max((_matrix_quality(matrix) for matrix in matrices), default=(0, 0, 0))
        candidates.append((score, table_fallback.name, 0.76, matrices))
    if structure_fallback.available:
        matrices = structure_fallback.predict_matrices(page.image)
        score = max((_matrix_quality(matrix) for matrix in matrices), default=(0, 0, 0))
        candidates.append((score, structure_fallback.name, 0.72, matrices))
    if vl_fallback.available:
        matrices = vl_fallback.predict_matrices(page.image)
        score = max((_matrix_quality(matrix) for matrix in matrices), default=(0, 0, 0))
        candidates.append((score, vl_fallback.name, 0.70, matrices))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    quality, source, confidence, matrices = candidates[0]
    if quality[0] < 2 or quality[1] < 3:
        return []
    return [
        _table_from_matrix(page, start_index + offset, matrix, source, confidence)
        for offset, matrix in enumerate(matrices)
    ]


def _needs_structured_fallback(tables: list[OCRTable], config: OCRConfig) -> bool:
    if not tables:
        return True
    best = max(tables, key=lambda table: (table.structure_confidence, table.n_cols, table.n_rows))
    if best.structure_confidence < config.min_structure_confidence:
        return True
    if config.document_profile == "dense_boq" and best.n_cols < 12:
        return True
    if len(best.column_fields) < 4:
        return True
    return False


def _process_page(
    page: OCRPage,
    recognizer: FastCellRecognizer,
    table_fallback: PaddleTableFallback,
    structure_fallback: PaddleStructureFallback,
    vl_fallback: PaddleOCRVLFallback,
    config: OCRConfig,
) -> list[dict]:
    tables = _select_orientation_and_tables(page, recognizer, config) if config.use_grid_first else []

    force_structured = not recognizer.available
    if force_structured or _needs_structured_fallback(tables, config):
        fallback_tables = _best_structured_fallback(
            page,
            start_index=len(tables) + 1,
            table_fallback=table_fallback,
            structure_fallback=structure_fallback,
            vl_fallback=vl_fallback,
        )
        if fallback_tables:
            # Dùng fallback khi nó có cấu trúc tốt hơn, hoặc bổ sung khi trang có
            # nhiều bảng. Không trộn cell OCR và VLM theo vị trí khi không có bbox.
            best_grid_cols = max((table.n_cols for table in tables), default=0)
            best_fallback_cols = max((table.n_cols for table in fallback_tables), default=0)
            if force_structured or not tables or best_fallback_cols > best_grid_cols + 2:
                tables = fallback_tables
            else:
                page.warnings.append(
                    f"Có kết quả fallback {fallback_tables[0].source} nhưng giữ grid-first vì cấu trúc lưới ổn định hơn."
                )

    if not tables:
        page.warnings.append("Không trích xuất được bảng bằng grid-first hoặc model fallback local.")
        return []

    # Ultra mode always asks the strongest document model to independently
    # review the page, while preserving the deterministic OpenCV grid geometry.
    vl_matrices: list[list[list[str]]] = []
    if config.accuracy_mode == "ultra" and config.ultra_vl_reconcile_tables and vl_fallback.available:
        vl_matrices = vl_fallback.predict_matrices(page.image)

    rows: list[dict] = []
    for table in tables:
        if table.source == "opencv-grid":
            if len(table.column_fields) < 4:
                table.warnings.append("Nhận diện tiêu đề yếu: xác định dưới 4 trường chuẩn.")
            _recognize_data_cells(page, table, recognizer, config)
            if vl_matrices:
                compatible = [
                    matrix for matrix in vl_matrices
                    if max((len(row) for row in matrix), default=0) == table.n_cols
                ]
                if compatible:
                    matrix = min(compatible, key=lambda value: abs(len(value) - table.n_rows))
                    _reconcile_grid_with_vl(table, matrix, config)
        page.tables.append(table)
        rows.extend(assemble_rows(table, config))
    return rows


def _document_summary(document: OCRDocument) -> dict:
    cells = [cell for page in document.pages for table in page.tables for cell in table.cells]
    nonblank = [cell for cell in cells if cell.text]
    review_cells = [cell for cell in cells if cell.review_reason]
    average_confidence = (
        sum(cell.confidence for cell in nonblank) / len(nonblank)
        if nonblank else 0.0
    )
    return {
        "pages": len(document.pages),
        "tables": sum(len(page.tables) for page in document.pages),
        "rows": len(document.rows),
        "cells": len(cells),
        "nonblank_cells": len(nonblank),
        "review_cells": len(review_cells),
        "review_rows": sum(bool(row.get("ocr_flags")) for row in document.rows),
        "average_confidence": average_confidence,
    }


def run_ocr(
    input_path: str | Path,
    output_path: str | Path | None = None,
    config: Optional[OCRConfig] = None,
    progress_callback: ProgressCallback | None = None,
) -> OCRDocument:
    config = config or OCRConfig.from_env()
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if input_path.stat().st_size > config.max_file_gb * 1024**3:
        raise ValueError(f"Tệp vượt giới hạn an toàn {config.max_file_gb:g} GB.")

    _emit(progress_callback, 3, "Đang đọc PDF/ảnh và chuẩn hóa chiều trang")
    pages = load_pages(input_path, config)
    recognizer = FastCellRecognizer(config)
    table_fallback = PaddleTableFallback(config)
    structure_fallback = PaddleStructureFallback(config)
    vl_fallback = PaddleOCRVLFallback(config)

    if not recognizer.available and not any((table_fallback.available, structure_fallback.available, vl_fallback.available)):
        raise RuntimeError(
            "Không có OCR engine local. Cấu hình PP-OCRv6-medium/PaddleOCR-VL-1.6 local "
            "hoặc cài Tesseract trên máy nội bộ."
        )
    if (
        config.accuracy_mode == "high"
        and config.document_profile == "dense_boq"
        and not config.allow_tesseract_only
        and not recognizer.has_primary_model
        and not any((table_fallback.available, structure_fallback.available, vl_fallback.available))
    ):
        raise RuntimeError(
            "Chế độ chính xác cao cho bảng BOQ không cho phép chỉ dùng Tesseract. "
            "Hãy cấu hình PP-OCRv6-medium, PP-TableMagic/PP-StructureV3 hoặc PaddleOCR-VL-1.6 local. "
            "Chỉ bật HSMT_OCR_ALLOW_TESSERACT_ONLY=1 khi chấp nhận độ chính xác và tốc độ thấp hơn."
        )

    all_rows: list[dict] = []
    warnings = config.validate_local_models()
    total_pages = max(len(pages), 1)
    for index, page in enumerate(pages, start=1):
        start = 8 + int((index - 1) / total_pages * 78)
        _emit(progress_callback, start, f"Đang nhận dạng trang {index}/{total_pages}")
        all_rows.extend(_process_page(
            page,
            recognizer,
            table_fallback,
            structure_fallback,
            vl_fallback,
            config,
        ))
        warnings.extend(f"Trang {page.page}: {warning}" for warning in page.warnings)
        for table in page.tables:
            warnings.extend(f"Trang {page.page}, bảng {table.table_index}: {warning}" for warning in table.warnings)

    audit = {
        "privacy_mode": "STRICT_LOCAL" if config.strict_privacy else "LOCAL",
        "network_calls": 0,
        "source_sha256": file_sha256(input_path),
        "device": config.device,
        "accuracy_mode": config.accuracy_mode,
        "document_profile": config.document_profile,
        "render_dpi": config.render_dpi,
        "upscale_factor": config.effective_upscale(),
        "gpu_vram_gb": config.gpu_vram_gb,
        "precision": config.precision,
        "ultra_vl_reconcile_tables": config.ultra_vl_reconcile_tables,
        "text_engines": recognizer.engines,
        "table_engines": [
            name for available, name in [
                (table_fallback.available, table_fallback.name),
                (structure_fallback.available, structure_fallback.name),
                (vl_fallback.available, vl_fallback.name),
            ] if available
        ],
        "paddle_vl_pipeline_version": config.paddle_vl_pipeline_version,
        "table_method": "OpenCV grid-first → PP-OCRv6-medium theo ô → kiểm tra chéo toàn trang PaddleOCR-VL-1.6 → PP-TableMagic/PP-StructureV3 fallback",
        "pages": len(pages),
        "page_sources": [
            {
                "page": page.page,
                "source": page.source,
                "rotation": page.rotation,
                "estimated_dpi": round(page.estimated_dpi, 1),
                "orientation_method": page.orientation_method,
                "orientation_scores": page.orientation_scores,
                "orientation_keywords": page.orientation_keywords,
            }
            for page in pages
        ],
    }
    document = OCRDocument(input_path, pages, all_rows, warnings=warnings, audit=audit)
    document.summary = _document_summary(document)

    if output_path:
        _emit(progress_callback, 90, "Đang tạo Excel và chèn ảnh ô cần kiểm tra")
        export_ocr_document(document, output_path, include_review_images=config.save_review_images)
    _emit(progress_callback, 100, "Hoàn tất OCR")
    return document


def run_ocr_batch(
    files: Iterable[str | Path],
    output_dir: str | Path,
    config: Optional[OCRConfig] = None,
    progress_callback: ProgressCallback | None = None,
) -> list[OCRDocument]:
    paths = [Path(path) for path in files]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    documents: list[OCRDocument] = []
    for index, path in enumerate(paths, start=1):
        def nested(page_progress: int, message: str, *, file_index=index) -> None:
            overall = int(((file_index - 1) + page_progress / 100.0) / max(len(paths), 1) * 100)
            _emit(progress_callback, overall, f"[{file_index}/{len(paths)}] {message}")

        output = output_dir / f"{path.stem}_OCR.xlsx"
        documents.append(run_ocr(path, output, config=config, progress_callback=nested))
    return documents


def create_ocr_package(
    documents: list[OCRDocument],
    output_dir: str | Path,
    package_name: str = "Ket_qua_OCR_PDF_sang_Excel.zip",
) -> Path:
    output_dir = Path(output_dir)
    package_path = output_dir / package_name
    manifest = {
        "kind": "ocr",
        "files": [
            {
                "source": document.source_path.name,
                "output": f"{document.source_path.stem}_OCR.xlsx",
                "summary": document.summary,
                "warnings": document.warnings,
                "sha256": document.audit.get("source_sha256"),
            }
            for document in documents
        ],
    }
    manifest_path = output_dir / "ocr_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.write(manifest_path, manifest_path.name)
        for document in documents:
            output = output_dir / f"{document.source_path.stem}_OCR.xlsx"
            if output.exists():
                archive.write(output, output.name)
    manifest_path.unlink(missing_ok=True)
    return package_path
