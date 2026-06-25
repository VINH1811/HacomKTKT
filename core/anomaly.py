from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from .config import EnterpriseConfig
from .models import ComparedItem, RowType, Severity


def _mad(values: np.ndarray, center: float) -> float:
    return float(np.median(np.abs(values - center)))


def enrich_consensus_anomalies(rows: list[ComparedItem], config: EnterpriseConfig) -> None:
    """Add multi-bidder price signals.

    The baseline price is part of the consensus population. This matters when
    comparing three bidders: one baseline + two candidate rows must count as
    three observations, rather than only the two candidates.
    """
    groups: dict[str, list[ComparedItem]] = defaultdict(list)
    for row in rows:
        groups[row.canonical_id].append(row)

    t = config.thresholds
    for group in groups.values():
        observations: list[float] = []
        first_ref = next((r.reference for r in group if r.reference and r.reference.unit_price_total is not None), None)
        if first_ref and first_ref.unit_price_total is not None and first_ref.unit_price_total >= 0:
            observations.append(first_ref.unit_price_total)
        observations.extend(
            row.candidate.unit_price_total
            for row in group
            if row.candidate is not None
            and row.candidate.unit_price_total is not None
            and row.candidate.unit_price_total >= 0
        )
        prices = np.asarray(observations, dtype=np.float64)
        if len(prices) < t.min_bidders_for_consensus:
            continue
        center = float(np.median(prices))
        mad = _mad(prices, center)
        scale = 1.4826 * mad
        for row in group:
            row.consensus_price = center
            row.consensus_mad = mad
            price = row.candidate.unit_price_total if row.candidate else None
            if price is None:
                continue
            if scale > 1e-9:
                z = (price - center) / scale
            elif center != 0:
                z = (price - center) / max(abs(center) * 0.01, 1.0)
            else:
                z = 0.0
            row.robust_z = float(z)
            if abs(z) >= t.robust_z_critical:
                row.flags.append(f"Giá lệch mạnh so với trung vị các HSDT (Robust Z={z:.2f})")
                row.severity = Severity.CRITICAL
                row.anomaly_score = min(100.0, row.anomaly_score + 35)
            elif abs(z) >= t.robust_z_warn:
                row.flags.append(f"Giá khác biệt so với trung vị các HSDT (Robust Z={z:.2f})")
                if row.severity in {Severity.OK, Severity.INFO, Severity.REVIEW}:
                    row.severity = Severity.WARNING
                row.anomaly_score = min(100.0, row.anomaly_score + 20)

    _add_isolation_forest_signal(rows, config)


def _add_isolation_forest_signal(rows: list[ComparedItem], config: EnterpriseConfig) -> None:
    usable: list[ComparedItem] = []
    features: list[list[float]] = []
    for row in rows:
        if not row.candidate or row.candidate.unit_price_total is None:
            continue
        # Keep this signal for principal BOQ lines; components are numerous and
        # would dominate the multivariate distribution.
        if row.candidate.row_type is not RowType.DETAIL:
            continue
        p_ratio = row.price_delta_pct if row.price_delta_pct is not None else 0.0
        q_ratio = row.quantity_delta_pct if row.quantity_delta_pct is not None else 0.0
        name_gap = 1.0 - row.match.score
        unit_mismatch = 1.0 if (
            row.reference
            and row.reference.normalized_unit
            and row.candidate.normalized_unit
            and row.reference.normalized_unit != row.candidate.normalized_unit
        ) else 0.0
        log_price = math.log1p(max(row.candidate.unit_price_total, 0.0))
        features.append([
            float(np.clip(p_ratio, -10, 10)),
            float(np.clip(q_ratio, -10, 10)),
            name_gap,
            unit_mismatch,
            log_price,
        ])
        usable.append(row)
    if len(features) < 30:
        return
    try:
        from sklearn.ensemble import IsolationForest

        matrix = np.asarray(features, dtype=np.float64)
        model = IsolationForest(
            n_estimators=160,
            max_samples="auto",
            contamination="auto",
            n_jobs=-1,
            random_state=config.random_state,
        )
        model.fit(matrix)
        decision = model.decision_function(matrix)
        q05, q95 = np.quantile(decision, [0.05, 0.95])
        denom = max(q95 - q05, 1e-9)
        signals = np.clip((q95 - decision) / denom, 0, 1)
        for row, signal in zip(usable, signals):
            if signal >= 0.92:
                row.flags.append(f"Mẫu đa biến bất thường (IsolationForest={signal:.2f})")
                if row.severity in {Severity.OK, Severity.INFO, Severity.REVIEW}:
                    row.severity = Severity.WARNING
                row.anomaly_score = min(100.0, row.anomaly_score + float(signal) * 12)
    except Exception:
        return
