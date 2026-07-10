"""Chuẩn hóa thứ tự đầu vào.

Khi file nhà thầu bị đảo/lệch thứ tự dòng và có hạng mục phát sinh ngoài danh
mục, báo cáo phải:
  1. Xếp các hạng mục ĐÃ GHÉP theo đúng số thứ tự (STT) của bản chuẩn, không
     theo vị trí vật lý bị lệch trong file nhà thầu.
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
    stt_sort_key,
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


# --------------------------------------------------------------------------
# Đơn vị: khóa sắp xếp STT tự nhiên, phân cấp.
# --------------------------------------------------------------------------

def test_stt_sort_key_is_natural_numeric():
    # '1.2' phải đứng TRƯỚC '1.10' (so theo giá trị số, không phải chuỗi thô).
    assert stt_sort_key("1.2") < stt_sort_key("1.10")
    assert stt_sort_key("2") < stt_sort_key("10")
    assert stt_sort_key("1") < stt_sort_key("1.1") < stt_sort_key("2")


def test_stt_sort_key_empty_goes_last():
    assert stt_sort_key("") > stt_sort_key("999")
    assert stt_sort_key("   ") > stt_sort_key("1")


def test_sorted_by_stt_not_string():
    values = ["1", "10", "2", "1.10", "1.2"]
    ordered = sorted(values, key=stt_sort_key)
    assert ordered == ["1", "1.2", "1.10", "2", "10"]


# --------------------------------------------------------------------------
# Tích hợp: matcher + build_bidder_rows giữ đúng thứ tự chuẩn hóa.
# --------------------------------------------------------------------------

def _reference() -> list[ItemRecord]:
    return [
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=2, stt="1", code="M-01", name="Tủ điện tổng"),
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=3, stt="2", code="M-02", name="Cáp điện CU XLPE"),
        _item(role=DocumentRole.HSMT, bidder="PL01", sheet="Điện", row=4, stt="10", code="M-10", name="Đèn LED âm trần"),
    ]


def _shuffled_bidder_with_extra() -> list[ItemRecord]:
    # Cùng sheet, nhưng thứ tự dòng bị ĐẢO so với bản chuẩn, và chèn một hạng mục
    # phát sinh ở GIỮA file (row 3) để chắc chắn nó không bám vị trí vật lý.
    return [
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=2, stt="10", code="M-10", name="Đèn LED âm trần"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=3, stt="99", code="X-99", name="Hạng mục phát sinh ngoài"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=4, stt="1", code="M-01", name="Tủ điện tổng"),
        _item(role=DocumentRole.HSDT, bidder="NT A", sheet="Điện", row=5, stt="2", code="M-02", name="Cáp điện CU XLPE"),
    ]


def test_matched_rows_follow_reference_stt_order():
    cfg = _cfg()
    refs = _reference()
    cands = _shuffled_bidder_with_extra()
    matches = match_items(refs, cands, cfg)
    rows = build_bidder_rows(refs, cands, "NT A", matches, cfg, reference_is_boq=True)

    matched = [r for r in rows if r.match.kind not in {MatchKind.MISSING, MatchKind.EXTRA}]
    # Các hạng mục đã ghép hiện theo đúng STT bản chuẩn: 1, 2, 10 (không phải thứ
    # tự vật lý 10, 1, 2 trong file nhà thầu).
    assert [r.reference.stt for r in matched] == ["1", "2", "10"]


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
    # Dòng cuối cùng là hạng mục phát sinh.
    assert rows[-1].match.kind is MatchKind.EXTRA
    assert rows[-1].candidate.item_name == "Hạng mục phát sinh ngoài"
