"""File đánh dấu: thêm sheet '<tên> — sắp xếp' (bản sao chỉ giá trị) dồn hạng
mục phát sinh xuống cuối, KHÔNG đụng vào sheet gốc.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from core.config import EnterpriseConfig
from core.tender_package import compare_appendices_with_bidders

SHEET = "1. HT điện"
SORTED = "1. HT điện — sắp xếp"
NAME_COL = 3


def _cfg(**kw) -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def _annotate(tmp_path: Path) -> Path:
    pl1 = tmp_path / "pl1.xlsx"
    # PL01 đặt tên sheet KHÁC bidder -> ghép theo MÃ hiệu (không theo STT/vị trí),
    # nên M-99 (không có mã trong PL01) chắc chắn là phát sinh.
    wb = Workbook(); ws = wb.active; ws.title = "KLMT"
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2])
    ws.append(["2", "M-02", "Cáp đồng XLPE", "m", 100])
    wb.save(pl1)

    bidder = tmp_path / "b.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = SHEET
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu",
               "Khối lượng nhà thầu chào", "Đơn giá tổng hợp", "Thành tiền"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_000_000, 2_000_000])
    # Hạng mục PHÁT SINH nằm GIỮA (không có trong PL01).
    ws.append(["2", "M-99", "Phát sinh giữa file", "Cái", 5, 5, 500_000, 2_500_000])
    ws.append(["3", "M-02", "Cáp đồng XLPE", "m", 100, 100, 50_000, 5_000_000])
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


def test_sorted_companion_sheet_created(tmp_path: Path):
    wb = load_workbook(_annotate(tmp_path))
    assert SHEET in wb.sheetnames          # sheet gốc vẫn còn
    assert SORTED in wb.sheetnames         # có thêm sheet sắp xếp


def test_phatsinh_moved_to_bottom_in_sorted_sheet(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SORTED]
    names = _names(ws)

    def idx(part):
        return next(i for i, n in enumerate(names) if part in n)

    # Trong sheet sắp xếp: hạng mục khớp trước, phát sinh xuống cuối.
    assert idx("Phát sinh giữa file") > idx("Tủ điện tổng")
    assert idx("Phát sinh giữa file") > idx("Cáp đồng XLPE")
    assert names[-1].startswith("Phát sinh")


def test_original_sheet_is_unchanged(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SHEET]
    # Sheet gốc GIỮ NGUYÊN thứ tự: phát sinh vẫn ở dòng 3 (giữa file).
    assert ws.cell(3, NAME_COL).value == "Phát sinh giữa file"


def test_marks_carried_into_sorted_sheet(tmp_path: Path):
    ws = load_workbook(_annotate(tmp_path))[SORTED]
    names = _names(ws)
    ps_row = 2 + next(i for i, n in enumerate(names) if n.startswith("Phát sinh"))
    cell = ws.cell(ps_row, NAME_COL)
    # Ô tên hạng mục phát sinh giữ chú thích đã đánh dấu.
    assert cell.comment is not None and "phát sinh" in cell.comment.text.lower()
