from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .config import OCRConfig
from .models import OCRCell, OCRTable


@dataclass(slots=True)
class GridDetection:
    bbox: tuple[int, int, int, int]
    x_lines: list[int]
    y_lines: list[int]
    confidence: float
    horizontal_mask: np.ndarray
    vertical_mask: np.ndarray


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image.copy()


def _binarize(image: np.ndarray) -> np.ndarray:
    gray = _gray(image)
    # CLAHE nhẹ bảo toàn dấu chấm/phẩy và nét mảnh của số nhỏ.
    clahe = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(10, 10)).apply(gray)
    return cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 31, 11,
    )


def _merge_positions(values: Iterable[int], tolerance: int = 4) -> list[int]:
    values = sorted(int(v) for v in values)
    if not values:
        return []
    groups = [[values[0]]]
    for value in values[1:]:
        if value - groups[-1][-1] <= tolerance:
            groups[-1].append(value)
        else:
            groups.append([value])
    return [int(round(sum(group) / len(group))) for group in groups]


def _projection_lines(mask: np.ndarray, axis: int, min_ratio: float) -> list[int]:
    projection = np.count_nonzero(mask, axis=axis)
    span = mask.shape[axis]
    threshold = max(3, int(span * min_ratio))
    indexes = np.where(projection >= threshold)[0]
    tolerance = max(2, int(min(mask.shape) * 0.0018))
    return _merge_positions(indexes.tolist(), tolerance=tolerance)


def _line_masks(bw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = bw.shape
    # Các kernel dài vừa đủ để bắt bảng dày đặc nhưng không nuốt chữ.
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(28, w // 48), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(24, h // 48)))
    horizontal = cv2.morphologyEx(bw, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, vertical_kernel, iterations=1)
    horizontal = cv2.morphologyEx(horizontal, cv2.MORPH_CLOSE, np.ones((1, 5), np.uint8))
    vertical = cv2.morphologyEx(vertical, cv2.MORPH_CLOSE, np.ones((5, 1), np.uint8))
    return horizontal, vertical


def _make_detection(
    image_shape: tuple[int, int],
    bbox: tuple[int, int, int, int],
    horizontal: np.ndarray,
    vertical: np.ndarray,
    config: OCRConfig,
) -> GridDetection | None:
    full_h, full_w = image_shape
    x, y, w, h = bbox
    pad = max(2, int(min(full_w, full_h) * 0.0025))
    x = max(0, x - pad)
    y = max(0, y - pad)
    w = min(full_w - x, w + 2 * pad)
    h = min(full_h - y, h + 2 * pad)
    h_roi = horizontal[y:y + h, x:x + w]
    v_roi = vertical[y:y + h, x:x + w]

    x_lines = _projection_lines(v_roi, axis=0, min_ratio=0.22)
    y_lines = _projection_lines(h_roi, axis=1, min_ratio=0.10)
    if x_lines and x_lines[0] > 12:
        x_lines.insert(0, 0)
    if x_lines and w - x_lines[-1] > 12:
        x_lines.append(w - 1)
    if y_lines and y_lines[0] > 12:
        y_lines.insert(0, 0)
    if y_lines and h - y_lines[-1] > 12:
        y_lines.append(h - 1)

    # Không bỏ các cột nhỏ quá sớm; tài liệu BOQ có nhiều cột số rất hẹp.
    x_lines = [p for i, p in enumerate(x_lines) if i == 0 or p - x_lines[i - 1] >= config.min_cell_width]
    y_lines = [p for i, p in enumerate(y_lines) if i == 0 or p - y_lines[i - 1] >= config.min_cell_height]
    if len(x_lines) < 4 or len(y_lines) < 4:
        return None

    grid_roi = cv2.bitwise_or(h_roi, v_roi)
    topology_cols = min(1.0, (len(x_lines) - 1) / 18.0)
    topology_rows = min(1.0, (len(y_lines) - 1) / 35.0)
    density = np.count_nonzero(grid_roi) / max(w * h, 1)
    border_hits = 0
    for xx in x_lines:
        border_hits += int(np.count_nonzero(v_roi[:, max(0, xx - 1):min(w, xx + 2)]) > h * 0.25)
    for yy in y_lines:
        border_hits += int(np.count_nonzero(h_roi[max(0, yy - 1):min(h, yy + 2), :]) > w * 0.12)
    border_quality = border_hits / max(len(x_lines) + len(y_lines), 1)
    confidence = float(np.clip(
        0.30 * topology_cols + 0.25 * topology_rows + 0.25 * min(1.0, density / 0.075) + 0.20 * border_quality,
        0.0, 1.0,
    ))
    return GridDetection((x, y, w, h), x_lines, y_lines, confidence, h_roi, v_roi)


def detect_grids(image: np.ndarray, config: OCRConfig) -> list[GridDetection]:
    """Phát hiện một hoặc nhiều bảng có đường kẻ trên trang."""
    bw = _binarize(image)
    h, w = bw.shape
    horizontal, vertical = _line_masks(bw)
    grid = cv2.bitwise_or(horizontal, vertical)
    grid = cv2.morphologyEx(grid, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, ww, hh = cv2.boundingRect(contour)
        area_ratio = (ww * hh) / max(w * h, 1)
        if area_ratio >= 0.035 and ww >= 0.25 * w and hh >= 0.12 * h:
            boxes.append((x, y, ww, hh))

    # Nếu các đường bị ngắt làm bảng vỡ thành nhiều contour, dùng toàn bộ vùng line pixels.
    if not boxes:
        points = cv2.findNonZero(grid)
        if points is not None:
            boxes = [cv2.boundingRect(points)]

    # Hợp nhất các box chồng lấn/gần nhau theo chiều dọc.
    boxes.sort(key=lambda b: (b[1], b[0]))
    merged: list[list[int]] = []
    for x, y, ww, hh in boxes:
        if not merged:
            merged.append([x, y, ww, hh])
            continue
        px, py, pw, ph = merged[-1]
        overlap_x = max(0, min(px + pw, x + ww) - max(px, x))
        gap_y = y - (py + ph)
        if overlap_x >= 0.6 * min(pw, ww) and gap_y <= max(20, int(0.025 * h)):
            nx, ny = min(px, x), min(py, y)
            nr, nb = max(px + pw, x + ww), max(py + ph, y + hh)
            merged[-1] = [nx, ny, nr - nx, nb - ny]
        else:
            merged.append([x, y, ww, hh])

    detections: list[GridDetection] = []
    for box in merged:
        detection = _make_detection((h, w), tuple(box), horizontal, vertical, config)
        if detection is not None:
            detections.append(detection)
    detections.sort(key=lambda d: (d.bbox[1], d.bbox[0]))
    return detections


def detect_grid(image: np.ndarray, config: OCRConfig) -> GridDetection | None:
    grids = detect_grids(image, config)
    return max(grids, key=lambda d: d.bbox[2] * d.bbox[3], default=None)


def _erase_grid_lines(gray: np.ndarray) -> np.ndarray:
    if gray.size == 0:
        return gray
    inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = inv.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, w // 3), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8, h // 2)))
    lines = cv2.bitwise_or(
        cv2.morphologyEx(inv, cv2.MORPH_OPEN, hk),
        cv2.morphologyEx(inv, cv2.MORPH_OPEN, vk),
    )
    # Inpaint/white-out line pixels and slightly dilate characters back.
    cleaned = gray.copy()
    cleaned[lines > 0] = 255
    return cleaned


def remove_borders(cell: np.ndarray) -> np.ndarray:
    if cell.size == 0:
        return cell
    gray = _gray(cell)
    h, w = gray.shape
    margin_x = max(1, int(w * 0.02))
    margin_y = max(1, int(h * 0.06))
    gray[:margin_y, :] = 255
    gray[-margin_y:, :] = 255
    gray[:, :margin_x] = 255
    gray[:, -margin_x:] = 255
    return _erase_grid_lines(gray)


def make_variants(cell: np.ndarray, upscale: float) -> list[tuple[str, np.ndarray]]:
    gray = remove_borders(cell)
    if gray.size == 0:
        return []
    gray = cv2.copyMakeBorder(gray, 10, 10, 14, 14, cv2.BORDER_CONSTANT, value=255)
    interp = cv2.INTER_LANCZOS4 if upscale > 1 else cv2.INTER_AREA
    up = cv2.resize(gray, None, fx=upscale, fy=upscale, interpolation=interp)
    # Unsharp masking nhẹ; không dùng super-resolution sinh ảnh vì có thể làm sai chữ số.
    blur = cv2.GaussianBlur(up, (0, 0), 1.0)
    sharp = cv2.addWeighted(up, 1.45, blur, -0.45, 0)
    clahe = cv2.createCLAHE(clipLimit=1.7, tileGridSize=(8, 8)).apply(sharp)
    adaptive = cv2.adaptiveThreshold(clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    return [("gray", up), ("sharp", sharp), ("clahe", clahe), ("adaptive", adaptive), ("otsu", otsu)]


def build_table(
    page_number: int,
    table_index: int,
    image: np.ndarray,
    detection: GridDetection,
    config: OCRConfig,
    debug_dir: str = "",
) -> OCRTable:
    x0, y0, w, h = detection.bbox
    table = OCRTable(
        page=page_number,
        table_index=table_index,
        bbox=detection.bbox,
        x_lines=detection.x_lines,
        y_lines=detection.y_lines,
        structure_confidence=detection.confidence,
    )
    roi = image[y0:y0 + h, x0:x0 + w]
    debug_root = Path(debug_dir) if debug_dir else None
    if debug_root:
        debug_root.mkdir(parents=True, exist_ok=True)

    for row in range(len(detection.y_lines) - 1):
        y1, y2 = detection.y_lines[row], detection.y_lines[row + 1]
        for col in range(len(detection.x_lines) - 1):
            x1, x2 = detection.x_lines[col], detection.x_lines[col + 1]
            if x2 - x1 < config.min_cell_width or y2 - y1 < config.min_cell_height:
                continue
            pad_x = max(1, int((x2 - x1) * 0.018))
            pad_y = max(1, int((y2 - y1) * 0.045))
            crop = roi[max(0, y1 + pad_y):min(h, y2 - pad_y), max(0, x1 + pad_x):min(w, x2 - pad_x)]
            cell = OCRCell(
                page=page_number,
                table_index=table_index,
                row=row,
                col=col,
                bbox=(x0 + x1, y0 + y1, x2 - x1, y2 - y1),
            )
            if debug_root and crop.size:
                path = debug_root / f"p{page_number:03d}_t{table_index:02d}_r{row:04d}_c{col:03d}.png"
                cv2.imwrite(str(path), crop)
                cell.image_path = str(path)
            table.cells.append(cell)
    return table


def crop_cell(image: np.ndarray, cell: OCRCell) -> np.ndarray:
    x, y, w, h = cell.bbox
    return image[y:y + h, x:x + w]
