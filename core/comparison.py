from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from rapidfuzz import fuzz

from .config import EnterpriseConfig
from .models import (
    ComparedItem,
    ComparisonResult,
    ComparisonSummary,
    FieldDifference,
    ItemRecord,
    MatchKind,
    MatchResult,
    RowType,
    Severity,
    WorkbookData,
)
from .number_parser import parse_number, percent_delta
from .text_normalizer import canonical_id, normalize_name

_RANK = {Severity.OK: 0, Severity.INFO: 1, Severity.REVIEW: 2, Severity.WARNING: 3, Severity.CRITICAL: 4}


def _worst(a: Severity, b: Severity) -> Severity:
    return a if _RANK[a] >= _RANK[b] else b


def _safe_delta(base: Optional[float], value: Optional[float]) -> Optional[float]:
    return value - base if base is not None and value is not None else None


def _text_similarity(a: Any, b: Any) -> float:
    left, right = normalize_name(str(a or "")), normalize_name(str(b or ""))
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return (0.55 * fuzz.WRatio(left, right) + 0.45 * fuzz.token_set_ratio(left, right)) / 100.0


def _simple_numeric(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(float(value)) else None
    text = str(value or "").strip()
    if not text:
        return None
    if re.search(r"[A-Za-zÀ-ỹ/x×]", text) or "/" in text or "%" in text or "<" in text or ">" in text:
        return None
    if len(re.findall(r"\d+", text)) != 1 and not re.fullmatch(r"[\s\d.,()+\-]+", text):
        return None
    return parse_number(text)


def _add_difference(
    row: ComparedItem,
    field: str,
    reference: Any,
    candidate: Any,
    severity: Severity,
    message: str,
    *,
    delta: Optional[float] = None,
    delta_pct: Optional[float] = None,
    similarity: Optional[float] = None,
    score: float = 0.0,
) -> None:
    row.differences.append(FieldDifference(
        field=field,
        reference_value=reference,
        candidate_value=candidate,
        delta=delta,
        delta_pct=delta_pct,
        similarity=similarity,
        severity=severity,
        message=message,
    ))
    row.flags.append(message)
    row.severity = _worst(row.severity, severity)
    row.anomaly_score = min(100.0, row.anomaly_score + score)


def _add_note(row: ComparedItem, message: str) -> None:
    """Attach an informational note without changing anomaly severity or score.

    Notes are displayed in detailed reports and annotated bidder workbooks, but
    they are deliberately excluded from AI_KIEM_TRA and warning statistics.
    """
    text = str(message or "").strip()
    if text and text not in row.notes:
        row.notes.append(text)


def _compare_numeric(
    row: ComparedItem,
    field: str,
    base: Optional[float],
    value: Optional[float],
    warn_pct: float,
    critical_pct: float,
    warn_abs: float = 0.0,
    critical_abs: float = 0.0,
    weight_warn: float = 12.0,
    weight_critical: float = 24.0,
    missing_severity: Severity = Severity.REVIEW,
    zero_nonzero_severity: Severity = Severity.WARNING,
    max_severity: Severity = Severity.CRITICAL,
) -> None:
    if base is None and value is None:
        return
    if base is None or value is None:
        _add_difference(
            row, field, base, value, missing_severity,
            f"{field}: một hồ sơ bị thiếu dữ liệu ({base} ↔ {value})",
            score=weight_critical if missing_severity is Severity.CRITICAL else weight_warn,
        )
        return

    delta = value - base
    pct = percent_delta(base, value)
    abs_delta = abs(delta)
    if base == 0:
        if value != 0:
            severity = zero_nonzero_severity
            if max_severity is Severity.CRITICAL and critical_abs > 0 and abs_delta >= critical_abs:
                severity = Severity.CRITICAL
            elif warn_abs > 0 and abs_delta >= warn_abs:
                severity = Severity.WARNING
            _add_difference(
                row, field, base, value, severity,
                f"{field}: chuẩn bằng 0 nhưng hồ sơ đối chiếu là {value:,.3f}",
                delta=delta, score=weight_critical if severity is Severity.CRITICAL else weight_warn,
            )
        return

    assert pct is not None
    if abs(pct) >= critical_pct and abs_delta >= critical_abs:
        severity = max_severity
        _add_difference(
            row, field, base, value, severity,
            f"{field} lệch {pct:+.2%} ({delta:+,.0f})",
            delta=delta, delta_pct=pct,
            score=weight_critical if severity is Severity.CRITICAL else weight_warn,
        )
    elif abs(pct) >= warn_pct and abs_delta >= warn_abs:
        _add_difference(
            row, field, base, value, Severity.WARNING,
            f"{field} lệch {pct:+.2%} ({delta:+,.0f})",
            delta=delta, delta_pct=pct, score=weight_warn,
        )


def _compare_text(
    row: ComparedItem,
    field: str,
    base: Any,
    value: Any,
    review_score: float,
    critical_score: float,
    *,
    missing_severity: Severity = Severity.REVIEW,
    weight_review: float = 5.0,
    weight_warning: float = 10.0,
) -> None:
    left, right = str(base or "").strip(), str(value or "").strip()
    if not left and not right:
        return
    similarity = _text_similarity(left, right)
    if not left or not right:
        _add_difference(
            row, field, left, right, missing_severity,
            f"{field}: một hồ sơ để trống",
            similarity=similarity, score=weight_review,
        )
    elif similarity < critical_score:
        _add_difference(
            row, field, left, right, Severity.WARNING,
            f"{field} khác đáng kể (tương đồng {similarity:.1%})",
            similarity=similarity, score=weight_warning,
        )
    elif similarity < review_score:
        _add_difference(
            row, field, left, right, Severity.REVIEW,
            f"{field} cần xác nhận (tương đồng {similarity:.1%})",
            similarity=similarity, score=weight_review,
        )


def _technical_map(item: ItemRecord) -> dict[str, tuple[str, Any]]:
    output: dict[str, tuple[str, Any]] = {}
    for label, value in item.technical_specs.items():
        key = normalize_name(label)
        if key:
            output[key] = (label, value)
    return output


def _compare_technical(row: ComparedItem, ref: ItemRecord, cand: ItemRecord, config: EnterpriseConfig) -> None:
    left, right = _technical_map(ref), _technical_map(cand)
    for key in sorted(set(left) | set(right)):
        label = (left.get(key) or right.get(key))[0]
        a = left.get(key, (label, None))[1]
        b = right.get(key, (label, None))[1]
        if (a is None or str(a).strip() == "") and (b is None or str(b).strip() == ""):
            continue
        an, bn = _simple_numeric(a), _simple_numeric(b)
        if an is not None and bn is not None:
            _compare_numeric(
                row, f"Thông số: {label}", an, bn,
                config.thresholds.technical_warn_pct,
                max(config.thresholds.technical_warn_pct * 2, 0.10),
                weight_warn=7.0, weight_critical=13.0,
                max_severity=Severity.WARNING,
            )
        else:
            _compare_text(
                row, f"Thông số: {label}", a, b,
                review_score=0.90, critical_score=0.65,
                weight_review=3.0, weight_warning=7.0,
            )


def _quality_differences(row: ComparedItem, item: ItemRecord, label: str) -> None:
    for flag in item.data_quality_flags:
        lower = flag.lower()
        severity = Severity.CRITICAL if ("#ref" in lower or "lỗi công thức" in lower or "sai phép tính" in lower) else Severity.REVIEW
        _add_difference(
            row, "Chất lượng dữ liệu", label, flag, severity,
            f"{label}: {flag}", score=22.0 if severity is Severity.CRITICAL else 5.0,
        )


def build_bidder_rows(
    reference_items: list[ItemRecord],
    bidder_items: list[ItemRecord],
    bidder_name: str,
    matches: list[MatchResult],
    config: EnterpriseConfig,
    *,
    reference_is_boq: bool = False,
) -> list[ComparedItem]:
    refs = [item for item in reference_items if item.is_comparable]
    cands = [item for item in bidder_items if item.is_comparable]
    t = config.thresholds
    output: list[ComparedItem] = []

    for match in matches:
        ref = refs[match.reference_index] if match.reference_index is not None else None
        cand = cands[match.candidate_index] if match.candidate_index is not None else None
        anchor = ref or cand
        assert anchor is not None
        ordinal = ref.row_number if ref else (1_000_000 + cand.row_number)
        cid = canonical_id(anchor.sheet, anchor.item_code, anchor.item_name, ordinal, anchor.normalized_path)
        row = ComparedItem(canonical_id=cid, bidder=bidder_name, reference=ref, candidate=cand, match=match)

        if match.kind is MatchKind.MISSING:
            _add_difference(
                row, "Hạng mục", ref.item_name if ref else "", "", Severity.CRITICAL,
                "Thiếu hạng mục trong hồ sơ đối chiếu", score=45,
            )
            output.append(row)
            continue
        if match.kind is MatchKind.EXTRA:
            _add_difference(
                row, "Hạng mục", "", cand.item_name if cand else "", Severity.WARNING,
                "Hạng mục phát sinh ngoài Phụ lục 01/danh mục đối chiếu", score=30,
            )
            output.append(row)
            continue

        assert ref is not None and cand is not None
        if ref.sheet.casefold() != cand.sheet.casefold():
            # Different sheet names are common because PL01 and contractor files
            # rarely share the same workbook structure.  A sheet difference is
            # context only: it must not create a review flag, increase anomaly
            # score, or send an otherwise-correct item to AI_KIEM_TRA.
            _add_note(
                row,
                f"Khớp đúng hạng mục nhưng khác sheet: {ref.sheet} ↔ {cand.sheet}",
            )

        if match.kind is MatchKind.EXACT_CODE and match.lexical_score < t.name_review_score:
            severity = Severity.CRITICAL if match.lexical_score < t.name_reject_score else Severity.WARNING
            _add_difference(
                row, "Tên hạng mục", ref.item_name, cand.item_name, severity,
                f"Trùng mã nhưng tên hạng mục khác đáng kể ({match.lexical_score:.1%})",
                similarity=match.lexical_score, score=32 if severity is Severity.CRITICAL else 20,
            )
        elif match.score < t.name_review_score:
            _add_difference(
                row, "Tên hạng mục", ref.item_name, cand.item_name, Severity.REVIEW,
                f"Tên hạng mục khớp thấp ({match.score:.1%})",
                similarity=match.score, score=min(30, (t.name_review_score - match.score) * 100),
            )
        else:
            _compare_text(
                row, "Tên hạng mục", ref.item_name, cand.item_name,
                review_score=0.88, critical_score=0.55,
                weight_review=4.0, weight_warning=10.0,
            )

        _compare_text(row, "Mã hiệu", ref.item_code, cand.item_code, 0.95, 0.60, weight_review=3, weight_warning=8)
        _compare_text(row, "Đơn vị tính", ref.unit, cand.unit, 0.99, 0.80, weight_review=5, weight_warning=12)

        component_row = ref.row_type is RowType.COMPONENT or cand.row_type is RowType.COMPONENT
        if reference_is_boq:
            # PL01 is an official quantity catalogue, not a priced bidder.
            # Therefore price is never compared against PL01. It is compared
            # horizontally across bidders later by peer_analysis.py.
            _compare_numeric(
                row, "Khối lượng mời thầu", ref.reference_quantity, cand.reference_quantity,
                t.quantity_warn_pct, t.quantity_critical_pct,
                weight_warn=16, weight_critical=32,
                missing_severity=Severity.CRITICAL,
                max_severity=Severity.WARNING if component_row else Severity.CRITICAL,
            )
            _compare_numeric(
                row, "Khối lượng nhà thầu chào so với KLMT", ref.reference_quantity, cand.bid_quantity,
                t.quantity_warn_pct, t.quantity_critical_pct,
                weight_warn=12, weight_critical=24,
                missing_severity=Severity.REVIEW,
                max_severity=Severity.WARNING if component_row else Severity.CRITICAL,
            )
            # Material/brand/origin are evaluated against PL02, not against PL01.
            _quality_differences(row, ref, "Phụ lục 01")
            _quality_differences(row, cand, "Hồ sơ nhà thầu")
            row.quantity_delta = _safe_delta(ref.reference_quantity, cand.bid_quantity)
            row.quantity_delta_pct = percent_delta(ref.reference_quantity, cand.bid_quantity)
            row.price_delta = None
            row.price_delta_pct = None
            row.amount_delta = None
        else:
            _compare_text(row, "Vật tư/Quy cách", ref.material, cand.material, t.material_review_score, t.material_reject_score, weight_review=4, weight_warning=9)
            _compare_text(row, "Thương hiệu", ref.brand, cand.brand, t.brand_review_score, t.brand_reject_score, weight_review=4, weight_warning=9)
            _compare_text(row, "Xuất xứ", ref.origin, cand.origin, t.origin_review_score, t.origin_reject_score, weight_review=3, weight_warning=8)
            _compare_numeric(
                row, "Khối lượng nhà thầu chào", ref.quantity, cand.quantity,
                t.quantity_warn_pct, t.quantity_critical_pct,
                weight_warn=15, weight_critical=28,
                missing_severity=Severity.REVIEW,
                max_severity=Severity.WARNING if component_row else Severity.CRITICAL,
            )
            _compare_numeric(
                row, "KL mời thầu trong file", ref.reference_quantity, cand.reference_quantity,
                t.quantity_warn_pct, t.quantity_critical_pct,
                weight_warn=8, weight_critical=16,
                missing_severity=Severity.REVIEW,
                max_severity=Severity.WARNING,
            )
            _compare_numeric(
                row, "Đơn giá tổng hợp", ref.unit_price_total, cand.unit_price_total,
                t.price_warn_pct, t.price_critical_pct,
                warn_abs=t.price_warn_abs, critical_abs=t.price_critical_abs,
                weight_warn=20, weight_critical=35,
                missing_severity=Severity.REVIEW,
                max_severity=Severity.WARNING if component_row else Severity.CRITICAL,
            )
            _compare_numeric(
                row, "Thành tiền nhà thầu", ref.amount, cand.amount,
                t.price_warn_pct, t.price_critical_pct,
                warn_abs=t.price_warn_abs, critical_abs=t.price_critical_abs,
                weight_warn=18, weight_critical=32,
                missing_severity=Severity.REVIEW,
                max_severity=Severity.WARNING if component_row else Severity.CRITICAL,
            )
            for label, ref_value in ref.price_components.items():
                cand_value = cand.price_components[label]
                _compare_numeric(
                    row, f"Thành phần giá: {label}", ref_value, cand_value,
                    t.component_warn_pct, t.component_critical_pct,
                    warn_abs=t.price_warn_abs / 10, critical_abs=t.price_critical_abs / 10,
                    weight_warn=7, weight_critical=12,
                    missing_severity=Severity.REVIEW,
                    max_severity=Severity.WARNING,
                )
            _compare_technical(row, ref, cand, config)
            _quality_differences(row, ref, "Baseline")
            _quality_differences(row, cand, "Đối chiếu")
            row.quantity_delta = _safe_delta(ref.quantity, cand.quantity)
            row.quantity_delta_pct = percent_delta(ref.quantity, cand.quantity)
            row.price_delta = _safe_delta(ref.unit_price_total, cand.unit_price_total)
            row.price_delta_pct = percent_delta(ref.unit_price_total, cand.unit_price_total)
            row.amount_delta = _safe_delta(ref.amount, cand.amount)
        row.flags = list(dict.fromkeys(row.flags))
        output.append(row)

    return output


def summarize(rows: list[ComparedItem], reference: WorkbookData, bidders: list[WorkbookData]) -> ComparisonSummary:
    bidder_totals: dict[str, float] = defaultdict(float)
    seen_candidate_rows: set[tuple[str, str, int]] = set()
    for row in rows:
        cand = row.candidate
        if cand and cand.row_type is RowType.DETAIL and cand.amount is not None:
            key = (row.bidder, cand.sheet, cand.row_number)
            if key not in seen_candidate_rows:
                bidder_totals[row.bidder] += cand.amount
                seen_candidate_rows.add(key)

    refs = [item for item in reference.items if item.is_comparable]
    reference_total = sum(item.amount or 0.0 for item in refs if item.row_type is RowType.DETAIL)
    return ComparisonSummary(
        reference_name=reference.bidder or reference.path.stem,
        bidder_count=len(bidders),
        total_reference_items=len(refs),
        total_rows=len(rows),
        exact_matches=sum(row.match.kind in {MatchKind.EXACT_STRUCTURE, MatchKind.EXACT_CODE, MatchKind.EXACT_NAME, MatchKind.ROW_NEAR} for row in rows),
        fuzzy_matches=sum(row.match.kind in {MatchKind.FUZZY, MatchKind.SEMANTIC, MatchKind.RERANKED} for row in rows),
        missing_items=sum(row.match.kind is MatchKind.MISSING for row in rows),
        extra_items=sum(row.match.kind is MatchKind.EXTRA for row in rows),
        review_rows=sum(row.severity is Severity.REVIEW for row in rows),
        warning_rows=sum(row.severity is Severity.WARNING for row in rows),
        critical_rows=sum(row.severity is Severity.CRITICAL for row in rows),
        total_reference_amount=reference_total,
        bidder_totals=dict(bidder_totals),
        generated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    )


def make_result(rows: list[ComparedItem], reference: WorkbookData, bidders: list[WorkbookData], audit: dict[str, Any]) -> ComparisonResult:
    warnings = list(reference.warnings)
    for bidder in bidders:
        warnings.extend(f"{bidder.bidder}: {warning}" for warning in bidder.warnings)
    return ComparisonResult(rows=rows, summary=summarize(rows, reference, bidders), warnings=warnings, audit=audit)
