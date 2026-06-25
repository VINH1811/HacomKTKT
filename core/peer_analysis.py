from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Callable, Optional

from rapidfuzz import fuzz

from .config import EnterpriseConfig
from .models import ComparedItem, FieldDifference, Severity
from .text_normalizer import normalize_name

_RANK = {Severity.OK: 0, Severity.INFO: 1, Severity.REVIEW: 2, Severity.WARNING: 3, Severity.CRITICAL: 4}


def _worst(a: Severity, b: Severity) -> Severity:
    return a if _RANK[a] >= _RANK[b] else b


def _signed_symmetric_pct(value: float, center: float) -> float:
    denominator = (abs(value) + abs(center)) / 2.0
    if denominator == 0:
        return 0.0
    return (value - center) / denominator


def _spread_symmetric(min_value: float, max_value: float) -> float:
    denominator = (abs(min_value) + abs(max_value)) / 2.0
    if denominator == 0:
        return 0.0
    return abs(max_value - min_value) / denominator


def _append_difference(
    row: ComparedItem,
    *,
    field: str,
    reference_value: Any,
    candidate_value: Any,
    severity: Severity,
    message: str,
    delta: Optional[float] = None,
    delta_pct: Optional[float] = None,
    similarity: Optional[float] = None,
    score: float = 0.0,
) -> None:
    row.differences.append(FieldDifference(
        field=field,
        reference_value=reference_value,
        candidate_value=candidate_value,
        delta=delta,
        delta_pct=delta_pct,
        similarity=similarity,
        severity=severity,
        message=message,
    ))
    row.flags.append(message)
    row.flags = list(dict.fromkeys(row.flags))
    row.severity = _worst(row.severity, severity)
    row.anomaly_score = min(100.0, row.anomaly_score + score)


def _numeric_value(row: ComparedItem, field: str) -> Optional[float]:
    item = row.candidate
    if item is None:
        return None
    return {
        "Đơn giá tổng hợp": item.unit_price_total,
        "Thành tiền theo KLMT": item.reference_amount,
        "Thành tiền nhà thầu chào": item.bid_amount,
        "Khối lượng nhà thầu chào": item.bid_quantity,
        "VL chính": item.price_main,
        "VL phụ": item.price_aux,
        "NC & máy TC": item.price_labor,
        "Chi phí quản lý": item.price_management,
        "Lợi nhuận": item.price_profit,
    }[field]


def _peer_numeric(
    group: list[ComparedItem],
    field: str,
    config: EnterpriseConfig,
) -> int:
    values = [(row, _numeric_value(row, field)) for row in group]
    values = [(row, value) for row, value in values if value is not None]
    if len(values) < 2:
        return 0

    numbers = [float(value) for _, value in values]
    low, high, center = min(numbers), max(numbers), float(median(numbers))
    spread = _spread_symmetric(low, high)
    low_bidder = next(row.bidder for row, value in values if float(value) == low)
    high_bidder = next(row.bidder for row, value in values if float(value) == high)

    is_quantity = "Khối lượng" in field
    is_component = field in {"VL chính", "VL phụ", "NC & máy TC", "Chi phí quản lý", "Lợi nhuận"}
    if is_quantity:
        warn_pct, critical_pct = config.thresholds.quantity_warn_pct, config.thresholds.quantity_critical_pct
        warn_abs = critical_abs = 0.0
    elif is_component:
        warn_pct, critical_pct = config.thresholds.component_warn_pct, config.thresholds.component_critical_pct
        warn_abs = config.thresholds.price_warn_abs / 10
        critical_abs = config.thresholds.price_critical_abs / 10
    else:
        warn_pct, critical_pct = config.thresholds.price_warn_pct, config.thresholds.price_critical_pct
        warn_abs = config.thresholds.price_warn_abs
        critical_abs = config.thresholds.price_critical_abs

    absolute_span = abs(high - low)
    if spread >= critical_pct and absolute_span >= critical_abs:
        group_severity = Severity.CRITICAL
        score = 26.0 if not is_component else 14.0
    elif spread >= warn_pct and absolute_span >= warn_abs:
        group_severity = Severity.WARNING
        score = 14.0 if not is_component else 8.0
    else:
        return 0

    group_message = (
        f"{field} giữa các nhà thầu chênh {spread:.2%}: thấp nhất {low_bidder}={low:,.3f}, "
        f"cao nhất {high_bidder}={high:,.3f}; trung vị nhóm={center:,.3f}"
    )

    marked = 0
    for row, raw_value in values:
        value = float(raw_value)
        deviation = _signed_symmetric_pct(value, center)
        # With exactly two bidders neither side is a standard, so both are marked.
        # With three or more, mark values that materially differ from the median;
        # still keep the group span in the master report through the extremes.
        should_mark = len(values) == 2 or abs(deviation) >= warn_pct or value in {low, high}
        if not should_mark:
            continue
        _append_difference(
            row,
            field=f"So sánh ngang hàng - {field}",
            reference_value=f"Trung vị nhóm: {center:,.3f}",
            candidate_value=value,
            severity=group_severity,
            message=group_message + f"; {row.bidder} lệch trung vị {deviation:+.2%}",
            delta=value - center,
            delta_pct=deviation,
            score=score,
        )
        if field == "Đơn giá tổng hợp":
            row.consensus_price = center
            row.price_delta = value - center
            row.price_delta_pct = deviation
        marked += 1
    return marked


def _text_similarity(a: str, b: str) -> float:
    left, right = normalize_name(a), normalize_name(b)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return (0.55 * fuzz.WRatio(left, right) + 0.45 * fuzz.token_set_ratio(left, right)) / 100.0


def _peer_text(
    group: list[ComparedItem],
    field: str,
    getter: Callable[[ComparedItem], str],
    *,
    warning: bool = False,
    threshold: float = 0.88,
) -> int:
    present = [(row, str(getter(row) or "").strip()) for row in group if row.candidate is not None]
    if len(present) < 2:
        return 0
    nonempty = [(row, value) for row, value in present if value]
    if not nonempty:
        return 0

    unique: list[str] = []
    for _, value in nonempty:
        if not any(_text_similarity(value, existing) >= threshold for existing in unique):
            unique.append(value)
    has_missing = len(nonempty) != len(present)
    if len(unique) <= 1 and not has_missing:
        return 0

    display = "; ".join(f"{row.bidder}={value or '[trống]'}" for row, value in present)
    severity = Severity.WARNING if warning else Severity.REVIEW
    marked = 0
    for row, value in present:
        closest = max((_text_similarity(value, other) for other in unique if other != value), default=0.0) if value else 0.0
        message = f"{field} không thống nhất giữa các nhà thầu: {display}"
        _append_difference(
            row,
            field=f"So sánh ngang hàng - {field}",
            reference_value="Các nhà thầu ngang hàng",
            candidate_value=value,
            severity=severity,
            message=message,
            similarity=closest,
            score=8.0 if warning else 4.0,
        )
        marked += 1
    return marked


def enrich_peer_comparison(
    rows: list[ComparedItem],
    config: EnterpriseConfig,
    *,
    price_only: bool = False,
) -> dict[str, int | bool | str]:
    """Compare bidders horizontally without choosing a bidder as standard.

    ``price_only`` is used by the appendix workflow.  In that workflow,
    quantities, item names, units and technical requirements are already
    checked against PL01/PL02, so the horizontal stage must add only price
    differences.  The standalone bidder-comparison workflow keeps the full
    cross-bidder comparison by using the default ``False`` value.
    """
    groups: dict[str, list[ComparedItem]] = defaultdict(list)
    for row in rows:
        groups[row.canonical_id].append(row)

    stats: dict[str, int | bool | str] = {
        "groups": len(groups),
        "numeric_flags": 0,
        "text_flags": 0,
        "enabled": True,
        "scope": "price_only" if price_only else "full",
    }
    if price_only:
        numeric_fields = (
            "Đơn giá tổng hợp",
            "Thành tiền theo KLMT",
            "Thành tiền nhà thầu chào",
            "VL chính",
            "VL phụ",
            "NC & máy TC",
            "Chi phí quản lý",
            "Lợi nhuận",
        )
    else:
        numeric_fields = (
            "Đơn giá tổng hợp", "Thành tiền theo KLMT", "Thành tiền nhà thầu chào",
            "Khối lượng nhà thầu chào", "VL chính", "VL phụ", "NC & máy TC",
            "Chi phí quản lý", "Lợi nhuận",
        )
    for group in groups.values():
        for field in numeric_fields:
            stats["numeric_flags"] += _peer_numeric(group, field, config)
        if not price_only:
            stats["text_flags"] += _peer_text(group, "Đơn vị tính", lambda r: r.candidate.unit if r.candidate else "", warning=True, threshold=0.98)
            stats["text_flags"] += _peer_text(group, "Vật tư/Quy cách", lambda r: r.candidate.material if r.candidate else "", threshold=0.82)
            stats["text_flags"] += _peer_text(group, "Thương hiệu", lambda r: r.candidate.brand if r.candidate else "", threshold=0.88)
            stats["text_flags"] += _peer_text(group, "Xuất xứ", lambda r: r.candidate.origin if r.candidate else "", threshold=0.90)

            technical_labels = sorted({label for row in group if row.candidate for label in row.candidate.technical_specs})
            for label in technical_labels:
                stats["text_flags"] += _peer_text(
                    group,
                    f"Thông số {label}",
                    lambda r, key=label: str(r.candidate.technical_specs.get(key, "")) if r.candidate else "",
                    threshold=0.90,
                )
    return stats
