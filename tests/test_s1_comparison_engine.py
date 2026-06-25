"""S1 - Unit tests cho Comparison Engine.

Các test cô lập logic so sánh, không cần đọc/ghi workbook thật.
"""

from __future__ import annotations

from core.comparison import build_bidder_rows
from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import DocumentRole, ItemRecord, MatchKind, MatchResult, RowType, Severity
from core.peer_analysis import enrich_peer_comparison
from core.text_normalizer import normalize_code, normalize_name, normalize_unit


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    # Đặt ngưỡng tuyệt đối bằng 0 để unit test chỉ tập trung vào phần trăm.
    cfg.thresholds.price_warn_abs = 0
    cfg.thresholds.price_critical_abs = 0
    return cfg


def _item(
    *,
    role: DocumentRole,
    bidder: str,
    sheet: str = "Điện",
    row: int = 2,
    code: str = "M-01",
    name: str = "Tủ điện tổng",
    unit: str = "Tủ",
    reference_quantity: float | None = 100.0,
    bid_quantity: float | None = None,
    price: float | None = 1_000_000.0,
    amount: float | None = None,
    quality_flags: list[str] | None = None,
) -> ItemRecord:
    if amount is None and price is not None:
        quantity = bid_quantity if role is DocumentRole.HSDT and bid_quantity is not None else reference_quantity
        amount = quantity * price if quantity is not None else None

    return ItemRecord(
        source_id=f"{bidder}:{sheet}:{row}",
        role=role,
        bidder=bidder,
        workbook=f"{bidder}.xlsx",
        sheet=sheet,
        row_number=row,
        stt="1",
        item_code=code,
        item_name=name,
        unit=unit,
        reference_quantity=reference_quantity,
        bid_quantity=bid_quantity,
        unit_price_total=price,
        reference_amount=amount if role is DocumentRole.HSMT else None,
        bid_amount=amount if role is DocumentRole.HSDT else None,
        row_type=RowType.DETAIL,
        normalized_stt="1",
        normalized_code=normalize_code(code),
        normalized_name=normalize_name(name),
        normalized_unit=normalize_unit(unit),
        data_quality_flags=quality_flags or [],
    )


def _exact_match() -> MatchResult:
    return MatchResult(
        reference_index=0,
        candidate_index=0,
        kind=MatchKind.EXACT_NAME,
        score=1.0,
        lexical_score=1.0,
        unit_score=1.0,
        reason="Test exact match",
    )


def _compare_pl01(ref: ItemRecord, candidate: ItemRecord, cfg: EnterpriseConfig | None = None):
    rows = build_bidder_rows(
        [ref],
        [candidate],
        candidate.bidder,
        [_exact_match()],
        cfg or _cfg(),
        reference_is_boq=True,
    )
    assert len(rows) == 1
    return rows[0]


def test_s1_ce01_equal_quantity_has_no_warning():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01", reference_quantity=100)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=100,
        bid_quantity=100,
    )

    row = _compare_pl01(ref, cand)

    assert row.quantity_delta == 0
    assert row.quantity_delta_pct == 0
    assert row.severity is Severity.OK
    assert row.flags == []


def test_s1_ce02_quantity_difference_8_percent_is_warning():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01", reference_quantity=100)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=100,
        bid_quantity=108,
    )

    row = _compare_pl01(ref, cand)

    assert row.quantity_delta == 8
    assert row.quantity_delta_pct == 0.08
    assert row.severity is Severity.WARNING
    assert any("khối lượng nhà thầu chào" in flag.lower() for flag in row.flags)


def test_s1_ce03_quantity_difference_35_percent_is_critical():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01", reference_quantity=100)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=100,
        bid_quantity=135,
    )

    row = _compare_pl01(ref, cand)

    assert row.quantity_delta_pct == 0.35
    assert row.severity is Severity.CRITICAL
    assert row.anomaly_score >= 24


def test_s1_ce04_unit_mismatch_is_flagged():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01", unit="100m", reference_quantity=5)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        unit="m",
        reference_quantity=5,
        bid_quantity=500,
    )

    row = _compare_pl01(ref, cand)

    assert row.severity is not Severity.OK
    assert any("đơn vị tính" in flag.lower() for flag in row.flags)
    assert any("khối lượng" in flag.lower() for flag in row.flags)


def test_s1_ce05_missing_item_is_critical():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01")
    match = MatchResult(0, None, MatchKind.MISSING, 0.0, reason="Không tìm thấy")

    row = build_bidder_rows([ref], [], "NT A", [match], _cfg(), reference_is_boq=True)[0]

    assert row.severity is Severity.CRITICAL
    assert any("thiếu hạng mục" in flag.lower() for flag in row.flags)


def test_s1_ce06_extra_item_is_warning():
    cand = _item(role=DocumentRole.HSDT, bidder="NT A", bid_quantity=1)
    match = MatchResult(None, 0, MatchKind.EXTRA, 0.0, reason="Phát sinh")

    row = build_bidder_rows([], [cand], "NT A", [match], _cfg(), reference_is_boq=True)[0]

    assert row.severity is Severity.WARNING
    assert any("phát sinh ngoài" in flag.lower() for flag in row.flags)


def test_s1_ce07_different_sheet_is_note_not_warning():
    ref = _item(
        role=DocumentRole.HSMT,
        bidder="PL01",
        sheet="2 - PHAN TU HA THE",
        reference_quantity=1,
    )
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="Linh Anh",
        sheet="1. HT điện",
        reference_quantity=1,
        bid_quantity=1,
    )

    row = _compare_pl01(ref, cand)

    assert row.severity is Severity.OK
    assert row.anomaly_score == 0
    assert row.flags == []
    assert any("khác sheet" in note.lower() for note in row.notes)


def test_s1_ce08_single_bidder_does_not_compare_price_against_pl01():
    ref = _item(
        role=DocumentRole.HSMT,
        bidder="PL01",
        reference_quantity=1,
        price=None,
    )
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=1,
        bid_quantity=1,
        price=9_999_999_999,
    )

    row = _compare_pl01(ref, cand)

    assert row.price_delta is None
    assert row.price_delta_pct is None
    assert not any("đơn giá" in flag.lower() for flag in row.flags)


def test_s1_ce09_price_outlier_is_flagged_only_in_peer_stage():
    cfg = _cfg()
    reference = _item(
        role=DocumentRole.HSMT,
        bidder="PL01",
        reference_quantity=1,
        price=None,
    )
    prices = {
        "NT1": 100_000_000.0,
        "NT2": 105_000_000.0,
        "NT3": 95_000_000.0,
        "NT4": 200_000_000.0,
    }

    rows = []
    for index, (bidder, price) in enumerate(prices.items(), start=1):
        candidate = _item(
            role=DocumentRole.HSDT,
            bidder=bidder,
            row=10 + index,
            reference_quantity=1,
            bid_quantity=1,
            price=price,
        )
        matches = match_items([reference], [candidate], cfg)
        rows.extend(build_bidder_rows(
            [reference], [candidate], bidder, matches, cfg, reference_is_boq=True,
        ))

    assert all(row.severity is Severity.OK for row in rows)

    enrich_peer_comparison(rows, cfg)
    nt4 = next(row for row in rows if row.bidder == "NT4")

    assert nt4.consensus_price is not None
    assert nt4.severity in {Severity.WARNING, Severity.CRITICAL}
    assert any("đơn giá tổng hợp" in flag.lower() for flag in nt4.flags)


def test_s1_ce10_formula_error_is_critical():
    ref = _item(role=DocumentRole.HSMT, bidder="PL01", reference_quantity=1)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=1,
        bid_quantity=1,
        quality_flags=["Ô G2 có lỗi công thức #REF!"],
    )

    row = _compare_pl01(ref, cand)

    assert row.severity is Severity.CRITICAL
    assert any("#ref" in flag.lower() for flag in row.flags)


def test_s1_ce11_configurable_quantity_threshold_is_used():
    cfg = _cfg()
    cfg.thresholds.quantity_warn_pct = 0.03
    cfg.thresholds.quantity_critical_pct = 0.10

    ref = _item(role=DocumentRole.HSMT, bidder="PL01", reference_quantity=100)
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="NT A",
        reference_quantity=100,
        bid_quantity=104,
    )

    row = _compare_pl01(ref, cand, cfg)

    assert row.quantity_delta_pct == 0.04
    assert row.severity is Severity.WARNING
