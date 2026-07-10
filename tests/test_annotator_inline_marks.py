"""File đánh dấu: KHÔNG thêm cột AI bên cạnh dữ liệu, chỉ tô màu + chú thích
(comment) trực tiếp lên ô có vấn đề; giữ 2 sheet phụ AI_TONG_QUAN/AI_KIEM_TRA.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from core.config import EnterpriseConfig
from core.tender_package import compare_appendices_with_bidders

_AI_COLUMNS = {"AI MỨC ĐỘ", "AI LÝ DO", "AI GHI CHÚ"}
BIDDER_SHEET = "1. HT điện"


def _cfg(**kw) -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _pl1(path: Path) -> None:
    wb = Workbook(); ws = wb.active; ws.title = "KLMT"
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2])
    ws.append(["2", "M-02", "Cáp đồng XLPE 4x10", "m", 100])
    wb.save(path)


def _bidder(path: Path) -> None:
    wb = Workbook(); ws = wb.active; ws.title = BIDDER_SHEET
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu",
               "Khối lượng nhà thầu chào", "Đơn giá tổng hợp", "Thành tiền"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_000_000, 2_000_000])
    # Khối lượng chào 130 vs KLMT 100 -> lệch, phải bị đánh dấu.
    ws.append(["2", "M-02", "Cáp đồng XLPE 4x10", "m", 100, 130, 50_000, 6_500_000])
    wb.save(path)


def _annotate(tmp_path: Path) -> Path:
    pl1 = tmp_path / "pl1.xlsx"; _pl1(pl1)
    bidder = tmp_path / "b.xlsx"; _bidder(bidder)
    out = compare_appendices_with_bidders(
        [("NT A", bidder)], tmp_path / "out", pl1_path=pl1,
        config=_cfg(annotate_workers=1, parse_cache_size=0, match_cache_size=0),
    )
    return Path(out.annotated_files["NT A"])


def test_no_ai_columns_added_beside_data(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    ws = wb[BIDDER_SHEET]
    headers = {str(c.value) for c in ws[1] if c.value is not None}
    # Không còn bất kỳ cột AI nào bên cạnh dữ liệu.
    assert not (headers & _AI_COLUMNS), headers
    assert not any(str(h).startswith("AI ") for h in headers)
    # Số cột đúng bằng file gốc (8), không phình thêm cột.
    assert ws.max_column == 8


def test_front_sheets_kept(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    assert "AI_TONG_QUAN" in wb.sheetnames
    assert "AI_KIEM_TRA" in wb.sheetnames


def test_problem_cells_have_fill_and_hover_comment(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    ws = wb[BIDDER_SHEET]

    commented = [c for row in ws.iter_rows() for c in row if c.comment is not None]
    filled = [c for row in ws.iter_rows() for c in row
              if c.fill is not None and c.fill.patternType and c.fill.fgColor.rgb not in (None, "00000000")]

    # Có ít nhất một ô được gắn chú thích (di chuột hiện ra) và một ô được tô màu.
    assert commented, "Phải có ô mang chú thích khi di chuột"
    assert filled, "Phải có ô được tô màu"
    # Chú thích nằm ngay trên ô dữ liệu (không phải trên cột phụ nào).
    assert all(c.column <= 8 for c in commented)
