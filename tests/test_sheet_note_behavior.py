from core.comparison import build_bidder_rows
from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import DocumentRole, ItemRecord, Severity
from core.peer_analysis import enrich_peer_comparison
from core.text_normalizer import normalize_name, normalize_unit


def _item(*, role, bidder, sheet, price=None):
    name = "Tủ điện LV-G.1+LV-G.2+LV-G.3+LV-G.4+LV-G.5+LV-G.6"
    return ItemRecord(
        source_id=f"{bidder}:{sheet}",
        role=role,
        bidder=bidder,
        workbook=f"{bidder}.xlsx",
        sheet=sheet,
        row_number=7 if role is DocumentRole.HSMT else 11,
        item_name=name,
        unit="Tủ",
        reference_quantity=1.0,
        bid_quantity=1.0 if role is DocumentRole.HSDT else None,
        unit_price_total=price,
        reference_amount=price,
        bid_amount=price,
        normalized_name=normalize_name(name),
        normalized_unit=normalize_unit("Tủ"),
    )


def test_different_sheet_is_note_not_warning_when_name_and_quantity_match():
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    ref = _item(
        role=DocumentRole.HSMT,
        bidder="PHỤ LỤC 01",
        sheet="2 - PHAN TU HA THE",
    )
    cand = _item(
        role=DocumentRole.HSDT,
        bidder="Linh Anh",
        sheet="1. HT điện",
        price=1_806_743_942.4,
    )

    matches = match_items([ref], [cand], cfg)
    rows = build_bidder_rows(
        [ref], [cand], "Linh Anh", matches, cfg, reference_is_boq=True,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.severity is Severity.OK
    assert row.anomaly_score == 0
    assert row.flags == []
    assert row.differences == []
    assert any("khác sheet" in note.lower() for note in row.notes)


def test_price_difference_between_bidders_still_warns_after_cross_sheet_match():
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    ref = _item(
        role=DocumentRole.HSMT,
        bidder="PHỤ LỤC 01",
        sheet="2 - PHAN TU HA THE",
    )
    bidder_a = _item(
        role=DocumentRole.HSDT,
        bidder="Linh Anh",
        sheet="1. HT điện",
        price=1_806_743_942.4,
    )
    bidder_b = _item(
        role=DocumentRole.HSDT,
        bidder="Nhà thầu B",
        sheet="Ha tang dien",
        price=2_200_000_000.0,
    )

    rows = []
    for bidder, candidate in (("Linh Anh", bidder_a), ("Nhà thầu B", bidder_b)):
        matches = match_items([ref], [candidate], cfg)
        rows.extend(build_bidder_rows(
            [ref], [candidate], bidder, matches, cfg, reference_is_boq=True,
        ))

    # Before the horizontal bidder comparison, a sheet difference is only a note.
    assert all(row.severity is Severity.OK for row in rows)
    assert all(any("khác sheet" in note.lower() for note in row.notes) for row in rows)

    enrich_peer_comparison(rows, cfg)

    assert all(row.severity in {Severity.WARNING, Severity.CRITICAL} for row in rows)
    assert all(any("đơn giá tổng hợp" in flag.lower() for flag in row.flags) for row in rows)
    assert all(not any("khác sheet" in flag.lower() for flag in row.flags) for row in rows)
