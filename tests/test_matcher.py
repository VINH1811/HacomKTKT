from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import DocumentRole, ItemRecord
from core.text_normalizer import normalize_code, normalize_name, normalize_unit


def item(code, name, unit="cái"):
    return ItemRecord(
        source_id="x", role=DocumentRole.HSDT, bidder="x", workbook="x.xlsx", sheet="S1", row_number=1,
        item_code=code, item_name=name, unit=unit,
        normalized_code=normalize_code(code), normalized_name=normalize_name(name), normalized_unit=normalize_unit(unit),
    )


def test_hybrid_match_is_one_to_one():
    refs = [item("M-01", "Tủ điện phân phối tổng"), item("M-02", "Cáp đồng XLPE 4x10")]
    cands = [item("M01", "Tủ phân phối điện tổng"), item("", "Cáp điện đồng cách điện XLPE 4 x 10")]
    cfg = EnterpriseConfig(); cfg.enable_semantic_matching = False
    matches = match_items(refs, cands, cfg)
    matched = [m for m in matches if m.reference_index is not None and m.candidate_index is not None]
    assert len(matched) == 2
    assert len({m.candidate_index for m in matched}) == 2
