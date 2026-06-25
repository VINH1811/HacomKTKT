from __future__ import annotations

from pathlib import Path

import cv2
import fitz
import numpy as np

from .config import OCRConfig
from .models import OCRPage


def _pixmap_to_bgr(pix: fitz.Pixmap) -> np.ndarray:
    channels = pix.n
    array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, channels)
    if channels == 4:
        return cv2.cvtColor(array, cv2.COLOR_RGBA2BGR)
    if channels == 3:
        return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    return cv2.cvtColor(array, cv2.COLOR_GRAY2BGR)


def _dominant_embedded_image(doc: fitz.Document, page: fitz.Page) -> np.ndarray | None:
    best: np.ndarray | None = None
    best_pixels = 0
    for image in page.get_images(full=True):
        try:
            info = doc.extract_image(image[0])
            data = np.frombuffer(info["image"], dtype=np.uint8)
            decoded = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if decoded is None:
                continue
            pixels = decoded.shape[0] * decoded.shape[1]
            if pixels > best_pixels:
                best = decoded
                best_pixels = pixels
        except Exception:
            continue
    return best if best_pixels >= 600_000 else None


def rotate_image(image: np.ndarray, angle: int) -> np.ndarray:
    angle %= 360
    if angle == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image.copy()


def _line_score(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = binary.shape
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(24, w // 38), 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(24, h // 38)))
    horizontal = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
    vertical = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
    density = (np.count_nonzero(horizontal) + np.count_nonzero(vertical)) / max(h * w, 1)
    landscape_bonus = 0.025 if w >= h else 0.0
    return float(density + landscape_bonus)


def _tesseract_osd_rotation(image: np.ndarray, config: OCRConfig) -> int | None:
    if not config.orientation_with_tesseract:
        return None
    try:
        import pytesseract

        if config.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
        sample = image
        max_side = max(sample.shape[:2])
        if max_side > 2200:
            scale = 2200 / max_side
            sample = cv2.resize(sample, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        result = pytesseract.image_to_osd(sample, output_type=pytesseract.Output.DICT)
        return int(result.get("rotate", 0)) % 360
    except Exception:
        return None


def normalize_orientation(image: np.ndarray, config: OCRConfig) -> tuple[np.ndarray, int]:
    # Chỉ dùng OSD như gợi ý; hình học bảng quyết định portrait/landscape.
    osd = _tesseract_osd_rotation(image, config)
    scores = {angle: _line_score(rotate_image(image, angle)) for angle in (0, 90, 180, 270)}
    best_geometry = max(scores, key=lambda angle: (scores[angle], -angle))
    # OSD chỉ được chọn trong cùng trục portrait/landscape với hình học lưới.
    # Nếu OSD đổi trục 90 độ, bước 0/180 phía sau không thể sửa lại.
    if (
        osd in scores
        and osd % 180 == best_geometry % 180
        and scores[osd] >= 0.82 * scores[best_geometry]
    ):
        return rotate_image(image, osd), osd
    return rotate_image(image, best_geometry), best_geometry


def _estimated_dpi(page: fitz.Page, image: np.ndarray) -> float:
    width_in = max(float(page.rect.width) / 72.0, 0.01)
    height_in = max(float(page.rect.height) / 72.0, 0.01)
    return float((image.shape[1] / width_in + image.shape[0] / height_in) / 2.0)


def load_pages(path: str | Path, config: OCRConfig) -> list[OCRPage]:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Không đọc được ảnh: {path}")
        oriented, rotation = normalize_orientation(image, config)
        return [OCRPage(page=1, image=oriented, rotation=rotation, source="image", estimated_dpi=0.0)]
    if suffix != ".pdf":
        raise ValueError("OCR hỗ trợ PDF hoặc ảnh PNG/JPG/TIFF/WebP.")

    document = fitz.open(path)
    pages: list[OCRPage] = []
    try:
        if len(document) > config.max_pages:
            raise ValueError(f"PDF có {len(document)} trang, vượt giới hạn {config.max_pages} trang.")
        for index, page in enumerate(document):
            embedded = _dominant_embedded_image(document, page)
            if embedded is not None:
                image = embedded
                source = "embedded-image"
            else:
                zoom = config.render_dpi / 72.0
                pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                image = _pixmap_to_bgr(pixmap)
                source = f"render-{config.render_dpi}dpi"
            dpi = _estimated_dpi(page, image)
            oriented, rotation = normalize_orientation(image, config)
            pages.append(OCRPage(
                page=index + 1,
                image=oriented,
                rotation=rotation,
                source=source,
                estimated_dpi=dpi,
            ))
    finally:
        document.close()
    return pages
