"""File đánh dấu: bản SẮP XẾP mang tên gốc, bản gốc thành '— gốc'.

- Sheet mang tên gốc là bản đã sắp xếp: đầu mục giữ nguyên, hạng mục khớp theo
  thứ tự, khối phát sinh dồn xuống cuối sau dòng phân cách, có tổng dựng lại.
- Công thức TRONG-DÒNG được dịch địa chỉ theo dòng mới (vẫn "sống").
- Bản gốc ('— gốc') giữ nguyên từng dòng và công thức; mọi tham chiếu chéo
  (sheet khác, hyperlink AI_KIEM_TRA) được viết lại trỏ về bản gốc.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from core.config import EnterpriseConfig
from core.tender_package import compare_appendices_with_bidders

SHEET = "1. HT điện"
GOC = "1. HT điện — gốc"
NAME_COL = 3
AMOUNT_COL = 8  # Thành tiền


def _cfg(**kw) -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _annotate(tmp_path: Path) -> Path:
    pl1 = tmp_path / "pl1.xlsx"
    # PL01 đặt tên sheet KHÁC bidder -> ghép theo MÃ hiệu, M-99 chắc chắn phát sinh.
    wb = Workbook(); ws = wb.active; ws.title = "KLMT"
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2])
    ws.append(["2", "M-02", "Cáp đồng XLPE", "m", 100])
    wb.save(pl1)

    bidder = tmp_path / "b.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = SHEET
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu",
               "Khối lượng nhà thầu chào", "Đơn giá tổng hợp", "Thành tiền"])
    # Dòng đầu mục (GROUP) + công thức thành tiền TRONG-DÒNG (=F*G).
    ws.append(["I", "", "Tủ điện hạ thế", "", None, None, None, None])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_000_000, "=F3*G3"])
    ws.append(["2", "M-99", "Phát sinh giữa file", "Cái", 5, 5, 500_000, "=F4*G4"])
    ws.append(["3", "M-02", "Cáp đồng XLPE", "m", 100, 100, 50_000, "=F5*G5"])
    # Sheet khác tham chiếu chéo vào sheet BOQ theo dòng gốc.
    tk = wb.create_sheet("Tong ket")
    tk["A1"] = "='1. HT điện'!H3"
    wb.save(bidder)

    out = compare_appendices_with_bidders(
        [("NT A", bidder)], tmp_path / "out", pl1_path=pl1,
        config=_cfg(annotate_workers=1, parse_cache_size=0, match_cache_size=0),
    )
    return Path(out.annotated_files["NT A"])


def _names(ws) -> list[str]:
    out = []
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, NAME_COL).value
        if v is not None and str(v).strip():
            out.append(str(v).strip())
    return out


def _row_of(ws, part: str) -> int:
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, NAME_COL).value
        if v is not None and part in str(v):
            return r
    raise AssertionError(f"Không thấy dòng chứa '{part}'")


def test_sorted_sheet_takes_original_name_goc_kept(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    assert SHEET in wb.sheetnames     # bản sắp xếp mang tên gốc
    assert GOC in wb.sheetnames       # bản gốc vẫn còn với hậu tố '— gốc'


def test_phatsinh_block_at_bottom_with_divider_and_totals(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SHEET]
    names = _names(ws)

    def idx(part):
        return next(i for i, n in enumerate(names) if part in n)

    # Đầu mục đi trước nhóm của nó; hạng mục khớp giữ thứ tự.
    assert idx("Tủ điện hạ thế") < idx("Tủ điện tổng") < idx("Cáp đồng XLPE")
    # Phát sinh nằm sau dòng phân cách, sau toàn bộ hạng mục khớp.
    assert idx("Cáp đồng XLPE") < idx("PHÁT SINH NGOÀI DANH MỤC") < idx("Phát sinh giữa file")
    # Có tổng phát sinh riêng.
    assert any("CỘNG PHÁT SINH" in n for n in names)


def test_row_formulas_translated_to_new_rows(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SHEET]
    # Công thức trong-dòng phải "sống" và trỏ đúng dòng MỚI của chính nó.
    for part in ("Tủ điện tổng", "Cáp đồng XLPE", "Phát sinh giữa file"):
        r = _row_of(ws, part)
        assert ws.cell(r, AMOUNT_COL).value == f"=F{r}*G{r}", part


def test_rebuilt_subtotal_is_live_formula(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SHEET]
    r = _row_of(ws, "Cộng: Tủ điện hạ thế")
    value = str(ws.cell(r, AMOUNT_COL).value or "")
    assert value.startswith("=SUM(")


def test_goc_sheet_unchanged_and_cross_refs_rewritten(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    goc = wb[GOC]
    # Bản gốc giữ nguyên vị trí dòng và công thức gốc.
    assert goc.cell(4, NAME_COL).value == "Phát sinh giữa file"
    assert goc.cell(4, AMOUNT_COL).value == "=F4*G4"
    # Tham chiếu chéo từ sheet khác được viết lại trỏ về bản gốc.
    assert wb["Tong ket"]["A1"].value == f"='{GOC}'!H3"


def test_ai_kiem_tra_hyperlinks_point_to_goc(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    review = wb["AI_KIEM_TRA"]
    links = []
    for row in review.iter_rows():
        for c in row:
            hl = c.hyperlink
            if hl is not None:
                links.append(str(getattr(hl, "target", "") or "") + str(getattr(hl, "location", "") or ""))
    assert links, "AI_KIEM_TRA phải có liên kết tới dòng gốc"
    assert all("— gốc" in link for link in links if SHEET in link or GOC in link)
