from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import cv2
import numpy as np

from .config import OCRConfig

# Cụm từ ưu tiên cho hồ sơ mời thầu / bảng BOQ. Điểm cao chỉ được dùng
# để phân biệt trang đúng chiều với trang lộn ngược, không dùng để sửa nội dung.
_ORIENTATION_PHRASES: dict[str, float] = {
    "stt": 4.0,
    "dien giai": 6.0,
    "don vi": 4.0,
    "khoi luong": 6.0,
    "ghi chu": 5.0,
    "ma vat tu": 6.0,
    "ma hieu": 5.0,
    "mo ta": 5.0,
    "thong tin vat lieu": 7.0,
    "vat lieu": 5.0,
    "thuong hieu": 5.0,
    "xuat xu": 5.0,
    "vl chinh": 4.0,
    "vl phu": 4.0,
    "don gia": 5.0,
    "thanh tien": 6.0,
    "nhan cong": 4.0,
    "loi nhuan": 4.0,
    "cong ty": 4.0,
    "du an": 4.0,
    "hang muc": 5.0,
    "moi thau": 4.0,
    "nha thau": 4.0,
    "nha san xuat": 4.0,
    "quy cach": 4.0,
    "viet nam": 3.0,
    "he thong": 3.0,
}

_COMMON_TOKENS = {
    "va", "theo", "cua", "cho", "cong", "ty", "du", "an", "hang", "muc",
    "don", "vi", "khoi", "luong", "thanh", "tien", "vat", "lieu", "chinh",
    "phu", "ghi", "chu", "xuat", "xu", "thuong", "hieu", "mo", "ta", "thong",
    "tin", "nhan", "may", "loi", "nhuan", "moi", "thau", "nha", "chao",
    "san", "dien", "gia", "tong", "hop",
}


@dataclass(slots=True)
class OrientationProbe:
    score: float
    text: str = ""
    keyword_hits: tuple[str, ...] = ()
    available: bool = False


def normalize_probe_text(text: str) -> str:
    value = unicodedata.normalize("NFD", str(text or "").lower())
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def semantic_text_score(text: str) -> tuple[float, tuple[str, ...]]:
    """Chấm điểm văn bản có giống tiêu đề/bảng tiếng Việt đúng chiều hay không.

    Confidence OCR không được dùng làm tín hiệu chính vì Tesseract đôi khi cho
    confidence cao với chữ lộn ngược. Từ khóa nghiệp vụ và token tiếng Việt hợp
    lệ là tín hiệu quyết định.
    """
    normalized = normalize_probe_text(text)
    if not normalized:
        return 0.0, ()

    hits = tuple(phrase for phrase in _ORIENTATION_PHRASES if phrase in normalized)
    phrase_score = sum(_ORIENTATION_PHRASES[phrase] for phrase in hits)
    tokens = normalized.split()
    common_score = min(20, sum(token in _COMMON_TOKENS for token in tokens)) * 0.35
    long_words = sum(token.isalpha() and len(token) >= 4 for token in tokens)
    lexical_score = min(long_words, 30) * 0.05
    # Nhiều token một ký tự thường là dấu hiệu OCR chữ bị đảo/lộn ngược.
    one_letter = sum(token.isalpha() and len(token) == 1 for token in tokens)
    penalty = max(0, one_letter - 8) * 0.10
    return max(0.0, phrase_score + common_score + lexical_score - penalty), hits


def _prepare_top_probe(image: np.ndarray, config: OCRConfig) -> np.ndarray:
    h, w = image.shape[:2]
    top_ratio = float(np.clip(config.orientation_probe_top_ratio, 0.18, 0.50))
    roi = image[: max(120, int(h * top_ratio)), :]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi.copy()

    target_width = int(np.clip(config.orientation_probe_target_width, 1800, 3400))
    scale = target_width / max(gray.shape[1], 1)
    # Không phóng quá mạnh ảnh đã lớn; chỉ tăng nhẹ để giữ dấu tiếng Việt.
    scale = float(np.clip(scale, 0.65, 1.35))
    if abs(scale - 1.0) > 0.03:
        interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)

    # Với chữ rất nhỏ, CLAHE có thể làm dày đường kẻ và phá dấu tiếng Việt.
    # Unsharp nhẹ + Otsu giữ nét chữ ổn định hơn cho probe định hướng.
    blur = cv2.GaussianBlur(gray, (0, 0), 0.8)
    sharp = cv2.addWeighted(gray, 1.25, blur, -0.25, 0)
    return cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def tesseract_orientation_probe(image: np.ndarray, config: OCRConfig) -> OrientationProbe:
    if not config.orientation_semantic_probe:
        return OrientationProbe(0.0)
    try:
        import pytesseract

        if config.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
        prepared = _prepare_top_probe(image, config)
        ocr_config = "--oem 1 --psm 11 -c preserve_interword_spaces=1"
        try:
            text = pytesseract.image_to_string(
                prepared,
                lang="vie+eng",
                config=ocr_config,
                timeout=config.orientation_probe_timeout,
            )
        except Exception:
            text = pytesseract.image_to_string(
                prepared,
                lang="eng",
                config=ocr_config,
                timeout=config.orientation_probe_timeout,
            )
        score, hits = semantic_text_score(text)
        return OrientationProbe(score, normalize_probe_text(text), hits, True)
    except Exception:
        return OrientationProbe(0.0)


def probe_upright_pair(image: np.ndarray, config: OCRConfig) -> dict[int, OrientationProbe]:
    return {
        0: tesseract_orientation_probe(image, config),
        180: tesseract_orientation_probe(cv2.rotate(image, cv2.ROTATE_180), config),
    }
