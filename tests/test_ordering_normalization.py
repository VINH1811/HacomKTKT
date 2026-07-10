"""Chuẩn hóa thứ tự đầu vào.

Khi file nhà thầu bị đảo/lệch thứ tự dòng và có hạng mục phát sinh ngoài danh
mục, báo cáo phải:
  1. Xếp các hạng mục ĐÃ GHÉP theo đúng thứ tự của bản chuẩn (bản chuẩn được lập
     theo số thứ tự), không theo vị trí vật lý bị lệch trong file nhà thầu.
  2. Dồn TẤT CẢ hạng mục phát sinh (EXTRA) xuống cuối, không chèn giữa.
"""

from __future__ import annotations

from core.comparison import build_bidder_rows
from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import DocumentRole, ItemRecord, MatchKind, RowType
from core.text_normalizer import (
    normalize_code,
    normalize_name,
    normalize_stt,
    normalize_unit,
)


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _item(*, role, bidder, sheet, row, stt, code, name) -> ItemRecord:
    return ItemRecord(
        source_id=f"{bidder}:{sheet}:{row}",
        role=role,
        bidder=bidder,
        workbook=f"{bidder}.xlsx",
        sheet=sheet,
        row_number=row,
        stt=stt,
        item_code=code,
        item_name=name,
        unit="Cái",
        reference_quantity=1.0,
        bid_quantity=1.0 if role is DocumentRole.HSDT else None,
        unit_price_total=1_000.0,
        row_type=RowType.DETAIL,
        normalized_stt=normalize_stt(stt),
        normalized_code=normalize_code(code),
        normalized_name=normalize_name(name),
        normalized_unit=normalize_unit("Cái"),
    )


def _reference() -> list[ItemRecord]:
    # Bản chuẩn (PL01) lập theo số thứ tự: dòng tăng dần theo STT.
    return [
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=2, stt="1", code="M-01", name="Tủ điện tổng"),
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=3, stt="2", code="M-02", name="Cáp điện CU XLPE"),
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=4, stt="3", code="M-03", name="Đèn LED âm trần"),
    ]


def _shuffled_bidder_with_extra() -> list[ItemRecord]:
    # Cùng sheet, nhưng thứ tự dòng bị ĐẢO so với bản chuẩn, và chèn một hạng mục
    # phát sinh ở GIỮA file (row 3) để chắc chắn nó không bám vị trí vật lý.
    return [
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=2, stt="3", code="M-03", name="Đèn LED âm trần"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=3, stt="99", code="X-99", name="Hạng mục phát sinh ngoài"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=4, stt="1", code="M-01", name="Tủ điện tổng"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=5, stt="2", code="M-02", name="Cáp điện CU XLPE"),
    ]


def test_matched_rows_follow_reference_order():
    cfg = _cfg()
    refs = _reference()
    cands = _shuffled_bidder_with_extra()
    matches = match_items(refs, cands, cfg)
    rows = build_bidder_rows(refs, cands, "NT A", matches, cfg, reference_is_boq=True)

    matched = [r for r in rows if r.match.kind not in {MatchKind.MISSING, MatchKind.EXTRA}]
    # Các hạng mục đã ghép hiện theo đúng thứ tự bản chuẩn: 1, 2, 3 (không phải
    # thứ tự vật lý 3, 1, 2 trong file nhà thầu).
    assert [r.reference.stt for r in matched] == ["1", "2", "3"]


def test_extra_items_pushed_to_bottom():
    cfg = _cfg()
    refs = _reference()
    cands = _shuffled_bidder_with_extra()
    matches = match_items(refs, cands, cfg)
    rows = build_bidder_rows(refs, cands, "NT A", matches, cfg, reference_is_boq=True)

    kinds = [r.match.kind for r in rows]
    extra_positions = [i for i, k in enumerate(kinds) if k is MatchKind.EXTRA]
    non_extra_positions = [i for i, k in enumerate(kinds) if k is not MatchKind.EXTRA]

    assert extra_positions, "Phải phát hiện được hạng mục phát sinh"
    # Mọi hạng mục phát sinh nằm SAU toàn bộ dòng đã ghép/thiếu.
    assert min(extra_positions) > max(non_extra_positions)
    assert rows[-1].match.kind is MatchKind.EXTRA
    assert rows[-1].candidate.item_name == "Hạng mục phát sinh ngoài"
