from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any


# =============================================================================
# BIỂU THỨC CHÍNH QUY
# =============================================================================

_SPACE = re.compile(r"\s+")
_CODE_SEP = re.compile(r"[\s_/\\.]+")
_NON_ALNUM = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+", re.UNICODE)
_FORMULA_STT = re.compile(r"^=", re.IGNORECASE)
_UNIT_NOISE = re.compile(r"[^0-9a-zA-ZÀ-ỹ]+", re.UNICODE)


# =============================================================================
# DANH SÁCH ĐƠN VỊ TƯƠNG ĐƯƠNG
# =============================================================================

UNIT_ALIASES: dict[str, str] = {
    "cai": "cái",
    "cái": "cái",
    "chiec": "cái",
    "chiếc": "cái",
    "bo": "bộ",
    "bộ": "bộ",
    "tu": "tủ",
    "tủ": "tủ",
    "lot": "lô",
    "lo": "lô",
    "lô": "lô",
    "tb": "thiết bị",
    "thietbi": "thiết bị",
    "thiếtbị": "thiết bị",

    "m": "m",
    "met": "m",
    "mét": "m",
    "md": "m",
    "metdai": "m",
    "métdài": "m",
    "mét dài": "m",

    "m2": "m²",
    "met2": "m²",
    "mét2": "m²",
    "mvuong": "m²",
    "m vuong": "m²",
    "m vuông": "m²",
    "metvuong": "m²",
    "métvuông": "m²",
    "met vuong": "m²",
    "mét vuông": "m²",

    "m3": "m³",
    "met3": "m³",
    "mét3": "m³",
    "mkhoi": "m³",
    "m khoi": "m³",
    "m khối": "m³",
    "metkhoi": "m³",
    "métkhối": "m³",
    "met khoi": "m³",
    "mét khối": "m³",

    "kg": "kg",
    "kilogam": "kg",
    "kilogram": "kg",
    "tan": "tấn",
    "tấn": "tấn",
    "ton": "tấn",
    "tonne": "tấn",

    "l": "lít",
    "lit": "lít",
    "lít": "lít",

    "kw": "kW",
    "kwh": "kWh",
    "kv": "kV",
    "a": "A",
    "v": "V",
    "va": "VA",
    "kva": "kVA",
    "mva": "MVA",

    "mm": "mm",
    "cm": "cm",
    "dm": "dm",
    "km": "km",
    "mm2": "mm²",
    "cm2": "cm²",
    "dm2": "dm²",
    "km2": "km²",
    "mm3": "mm³",
    "cm3": "cm³",
    "dm3": "dm³",
    "km3": "km³",

    "100m": "100m",
}


STOPWORDS = {
    "va",
    "và",
    "cua",
    "của",
    "cho",
    "tai",
    "tại",
    "theo",
    "kem",
    "kèm",
    "bao",
    "gom",
    "gồm",
    "cac",
    "các",
    "hang",
    "hạng",
    "muc",
    "mục",
}


# =============================================================================
# HÀM CƠ SỞ
# =============================================================================

def strip_accents(text: Any) -> str:
    """Bỏ dấu tiếng Việt nhưng giữ nguyên chữ và số."""

    value = unicodedata.normalize("NFD", str(text or ""))
    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )
    return value.replace("đ", "d").replace("Đ", "D")


@lru_cache(maxsize=300_000)
def normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản chung nhưng không làm mất số mũ kỹ thuật.

    NFKC chuyển:
        ² -> 2
        ³ -> 3

    Vì vậy:
        Cáp điện 3×2.5 mm²
    được chuẩn hóa thành:
        cap dien 3x2 5 mm2
    """

    value = unicodedata.normalize(
        "NFKC",
        str(text or ""),
    ).strip().lower()

    value = (
        value
        .replace("×", "x")
        .replace("Ø", " phi ")
        .replace("ø", " phi ")
        .replace("^2", "2")
        .replace("^3", "3")
    )

    value = _NON_ALNUM.sub(" ", value)
    return _SPACE.sub(" ", value).strip()


@lru_cache(maxsize=300_000)
def normalize_name(text: str) -> str:
    """Chuẩn hóa tên hạng mục để dùng trong matcher."""

    value = strip_accents(normalize_text(text))
    return " ".join(
        token
        for token in value.split()
        if token not in STOPWORDS
    )


@lru_cache(maxsize=300_000)
def normalize_code(code: str) -> str:
    """Chuẩn hóa mã hiệu nhưng bỏ qua ô chứa công thức Excel."""

    raw = str(code or "").strip()

    if _FORMULA_STT.match(raw):
        return ""

    value = strip_accents(raw.upper())
    value = _CODE_SEP.sub("-", value)
    value = re.sub(r"[^A-Z0-9-]", "", value)
    value = re.sub(r"-+", "-", value).strip("-")

    simple_match = re.fullmatch(r"([A-Z]+)-?(\d+)", value)
    if simple_match:
        return f"{simple_match.group(1)}-{simple_match.group(2)}"

    return value


@lru_cache(maxsize=100_000)
def normalize_stt(value: str) -> str:
    """Chuẩn hóa số thứ tự, mã phân cấp hoặc ký hiệu dòng."""

    raw = str(value or "").strip()

    if not raw or raw.startswith("="):
        return ""

    normalized = strip_accents(raw).upper().replace(" ", "")
    normalized = re.sub(r"[^A-Z0-9.\-]", "", normalized)

    return normalized.strip(".-")


# =============================================================================
# CHUẨN HÓA ĐƠN VỊ
# =============================================================================

def _prepare_unit_text(value: Any) -> str:
    """Chuẩn bị chuỗi đơn vị mà không làm mất ý nghĩa số mũ."""

    raw = str(value or "").strip()
    if not raw:
        return ""

    normalized = unicodedata.normalize("NFKC", raw).lower()

    normalized = (
        normalized
        .replace("×", "x")
        .replace("Ø", " phi ")
        .replace("ø", " phi ")
        .replace("^2", "2")
        .replace("^3", "3")
        .replace("²", "2")
        .replace("³", "3")
    )

    normalized = _UNIT_NOISE.sub(" ", normalized)
    return _SPACE.sub(" ", normalized).strip()


@lru_cache(maxsize=20_000)
def normalize_unit(unit: str) -> str:
    """Chuẩn hóa đơn vị đo lường."""

    normalized = _prepare_unit_text(unit)
    if not normalized:
        return ""

    compact = normalized.replace(" ", "")
    plain = strip_accents(normalized)
    plain_compact = plain.replace(" ", "")

    for candidate in (
        normalized,
        compact,
        plain,
        plain_compact,
    ):
        if candidate in UNIT_ALIASES:
            return UNIT_ALIASES[candidate]

    metric_power_match = re.fullmatch(
        r"(mm|cm|dm|m|dam|hm|km)([23])",
        compact,
    )

    if metric_power_match:
        prefix, power = metric_power_match.groups()
        return f"{prefix}{'²' if power == '2' else '³'}"

    return normalized


# =============================================================================
# CÁC HÀM CÔNG KHAI KHÁC
# =============================================================================

def token_set(text: str) -> set[str]:
    """Trả về tập token đã chuẩn hóa của tên hạng mục."""

    return set(normalize_name(text).split())


def canonical_id(
    sheet: str,
    code: str,
    name: str,
    ordinal: int = 0,
    path: str = "",
) -> str:
    """Tạo định danh ổn định cho một dòng hạng mục."""

    normalized_sheet = normalize_name(sheet)[:40]
    normalized_code = normalize_code(code)
    normalized_name = normalize_name(name)[:80]
    normalized_parent = normalize_name(path)[:60]

    base = normalized_code or normalized_name or f"ROW-{ordinal}"

    if normalized_parent:
        base = f"{normalized_parent}::{base}"

    if normalized_sheet:
        return f"{normalized_sheet}::{base}::{ordinal}"

    return f"{base}::{ordinal}"
