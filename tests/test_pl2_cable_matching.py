"""Regression: hạng mục CÁP bị ghép nhầm nhóm PL02 và báo sai thương hiệu.

Bug thật từ dữ liệu Hacom: cáp Taisin (được phép trong nhóm "Hệ thống dây cáp
hạ thế") bị báo "ngoài danh sách (Schneider/ABB/Siemens)" vì ghép nhầm nhóm.
Ba nguyên nhân gốc đã sửa:
1. "cáp" nằm trong stopword (lẫn với "cung cấp") -> mất từ phân biệt chính.
2. Hint so bằng substring thô: "ong" khớp bừa trong "dong" (lõi đồng),
   "ha the" khớp mọi hạng mục điện -> cộng điểm oan cho nhóm sai.
3. Bonus hint nhị phân: khớp 1 tín hiệu tình cờ (pvc trong vỏ cáp) được cộng
   bằng khớp 4-5 tín hiệu thật (cap/xlpe/pvc/fr/cu).
"""

from __future__ import annotations

import pytest

from core.models import DocumentRole, ItemRecord, MaterialRequirement, RowType
from core.pl2_reader import PL2Matcher, _tokens, evaluate_pl2_compliance
from core.text_normalizer import normalize_name


def _req(name: str, brands: tuple, origins: tuple = ("Asia",)) -> MaterialRequirement:
    return MaterialRequirement(
        source_sheet="PL02", source_row=1, system="Hệ thống điện", item_name=name,
        requirement_text=f"{' / '.join(brands)} - {' / '.join(origins)}",
        allowed_brands=brands, allowed_origins=origins, note="",
        normalized_name=normalize_name(name),
    )


REQS = [
    _req("Tủ điện hạ thế (Đơn vị sản xuất, lắp ráp)", ("Á Châu", "Đạt Vĩnh Tiến", "Bích Hạnh"), ("VN",)),
    _req("Thiết bị đóng cắt Tủ điện hạ thế", ("Schneider", "ABB", "Siemens")),
    _req("Hệ thống dây cáp hạ thế", ("Cadivi", "Thipha", "Taisin")),
    _req("Ống luồn dây điện PVC", ("Sino", "Sam Phú", "AC"), ("VN",)),
    _req("Busway", ("Schneider", "ABB", "Siemens")),
]


def _item(name: str, path: str, material: str = "", brand: str = "Taisin", origin: str = "Việt Nam") -> ItemRecord:
    return ItemRecord(
        source_id="x", role=DocumentRole.HSDT, bidder="NT", workbook="w", sheet="1. HT điện",
        row_number=6, stt="1", item_name=name, unit="m", material=material, brand=brand, origin=origin,
        row_type=RowType.DETAIL, normalized_path=normalize_name(path), normalized_name=normalize_name(name),
    )


@pytest.fixture()
def matcher() -> PL2Matcher:
    return PL2Matcher(REQS)


def test_cap_token_is_not_a_stopword():
    # "cáp" phải sống sót qua tokenizer — nó là từ phân biệt chính của nhóm cáp.
    assert "cap" in _tokens("hệ thống dây cáp hạ thế")


def test_fr_cable_matches_cable_group_and_taisin_compliant(matcher):
    # Đúng case screenshot của người dùng: Cu/FR/XLPE + Taisin.
    it = _item("Cu/FR/XLPE (1x240)mm2", "Cáp hạ thế | Cáp điện 0,6kV, lõi đồng, cách điện FR",
               material="Cu/Mica/XLPE/LSZH 1x240mm2, 0.6/1kV")
    best, score = matcher.match(it, minimum_score=0.66)
    assert best is not None and best.item_name == "Hệ thống dây cáp hạ thế", \
        f"Cáp FR phải ghép nhóm cáp, không phải {best.item_name if best else None!r}"
    status, issues = evaluate_pl2_compliance(it, best)
    assert status == "PHÙ HỢP DANH SÁCH PL02", f"Taisin thuộc danh sách nhóm cáp: {issues}"


def test_pvc_sheathed_cable_not_stolen_by_conduit_group(matcher):
    # Cáp vỏ PVC: chữ "PVC" trong tên không được kéo về nhóm "Ống luồn dây PVC".
    it = _item("Cu/XLPE/PVC (3x240+1x120)mm2",
               "Cáp điện 0,6kV, lõi đồng, cách điện FR | Cáp điện 0,6kV lõi đồng, cách điện XLPE, vỏ PVC")
    best, _ = matcher.match(it, minimum_score=0.66)
    assert best is not None and best.item_name == "Hệ thống dây cáp hạ thế"


def test_copper_core_does_not_trigger_ong_hint(matcher):
    # "lõi đồng" chứa chuỗi con "ong" — hint "ống" không được khớp substring.
    it = _item("Cu/FR/XLPE (1x70)mm2", "Cáp điện 0,6kV, lõi đồng, cách điện FR")
    best, _ = matcher.match(it, minimum_score=0.66)
    assert best is not None and "cáp" in best.item_name.lower()


def test_real_conduit_still_matches_conduit_group(matcher):
    # Ống luồn dây thật vẫn phải về đúng nhóm ống (không bị fix kéo lệch).
    it = _item("Ống luồn dây PVC cứng D20 (lắp đặt chìm)", "PHẦN ỐNG LUỒN DÂY", brand="Sino")
    best, _ = matcher.match(it, minimum_score=0.66)
    assert best is not None and best.item_name == "Ống luồn dây điện PVC"
    status, _ = evaluate_pl2_compliance(it, best)
    assert status == "PHÙ HỢP DANH SÁCH PL02"


def test_switchgear_still_matches_switchgear_group(matcher):
    # Tủ điện/đóng cắt không bị ảnh hưởng: vẫn về đúng họ tủ điện.
    it = _item("Tủ điện LV-G.1+LV-G.2", "PHẦN TỦ ĐIỆN HẠ THẾ",
               material="Thiết bị đóng cắt: Schneider", brand="ACIT")
    best, _ = matcher.match(it, minimum_score=0.66)
    assert best is not None and "tủ điện" in best.item_name.lower()


def test_single_incidental_hint_gets_smaller_bonus_than_multiple(matcher):
    # Kiểm tra trực tiếp cơ chế bonus phân bậc: item cáp nhiều tín hiệu phải
    # thắng nhóm ống chỉ khớp 1 tín hiệu "pvc" tình cờ.
    it = _item("Cu/XLPE/PVC (1x120)mm2", "Cáp điện 0,6kV, lõi đồng")
    scores = {}
    for entry in matcher._prepared:
        best_one = PL2Matcher([entry.requirement])
        _, s = best_one.match(it, minimum_score=0.0)
        scores[entry.requirement.item_name] = s
    assert scores["Hệ thống dây cáp hạ thế"] > scores["Ống luồn dây điện PVC"]
