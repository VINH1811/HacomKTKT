from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

_NA = {"", "-", "--", "—", "–", "n/a", "na", "none", "null", "nan"}
_CURRENCY = re.compile(r"(?i)\b(vnd|vnđ|đồng|dong|usd|eur)\b|₫|\$")
_ALLOWED = re.compile(r"[^0-9,\.\-+() ]")


def parse_number(value: Any) -> Optional[float]:
    """Parse numbers from Vietnamese/international spreadsheet text.

    Handles: 1.234.567,89; 1,234,567.89; 1 234 567; (1.000); -0.5.
    Ambiguous single separators are resolved conservatively.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, Decimal)):
        f = float(value)
        return f if math.isfinite(f) else None

    raw = str(value).replace("\u00a0", " ").strip()
    if raw.lower() in _NA:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    raw = _CURRENCY.sub("", raw)
    raw = _ALLOWED.sub("", raw).strip()
    raw = raw.replace(" ", "")
    if not raw or raw in {"+", "-"}:
        return None

    sign = -1 if negative else 1
    if raw.startswith("-"):
        sign = -1
        raw = raw[1:]
    elif raw.startswith("+"):
        raw = raw[1:]

    if not raw:
        return None

    dot_count, comma_count = raw.count("."), raw.count(",")
    normalized = raw

    if dot_count and comma_count:
        # Right-most separator is decimal; the other is thousands.
        if raw.rfind(",") > raw.rfind("."):
            normalized = raw.replace(".", "").replace(",", ".")
        else:
            normalized = raw.replace(",", "")
    elif comma_count:
        normalized = _normalize_single_separator(raw, ",")
    elif dot_count:
        normalized = _normalize_single_separator(raw, ".")

    try:
        result = float(Decimal(normalized)) * sign
        return result if math.isfinite(result) else None
    except (InvalidOperation, ValueError):
        return None


def _normalize_single_separator(raw: str, sep: str) -> str:
    parts = raw.split(sep)
    if len(parts) == 2:
        left, right = parts
        # Leading zero and short suffix is decimal (0.5 / 0,25).
        if left in {"0", ""} and 1 <= len(right) <= 6:
            return f"{left or '0'}.{right}"
        # 1-2 decimal places are almost always decimals.
        if 1 <= len(right) <= 2:
            return f"{left}.{right}"
        # Exactly 3 digits is thousands except for common decimal values below 100.
        if len(right) == 3:
            return left + right
        return f"{left}.{right}"

    # Multiple equal separators: thousands if every trailing group has 3 digits.
    if all(len(p) == 3 for p in parts[1:]):
        return "".join(parts)
    # Otherwise use the final separator as decimal.
    return "".join(parts[:-1]) + "." + parts[-1]


def percent_delta(base: Optional[float], value: Optional[float]) -> Optional[float]:
    if base is None or value is None:
        return None
    if base == 0:
        return 0.0 if value == 0 else None
    return (value - base) / abs(base)


def safe_amount(quantity: Optional[float], price: Optional[float], amount: Optional[float]) -> Optional[float]:
    if amount is not None:
        return amount
    if quantity is not None and price is not None:
        return quantity * price
    return None


def math_error(quantity: Optional[float], price: Optional[float], amount: Optional[float], tolerance_pct: float = 0.005) -> Optional[float]:
    if quantity is None or price is None or amount is None:
        return None
    expected = quantity * price
    scale = max(abs(expected), abs(amount), 1.0)
    diff = abs(expected - amount)
    return diff if diff / scale > tolerance_pct else None
