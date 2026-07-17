"""Khi bản chuẩn (PL01) bị chọn nhầm hoặc không bao phủ phạm vi hồ sơ, gần như
mọi hạng mục nhà thầu sẽ không ghép được và bị coi là 'phát sinh ngoài' GIẢ.

Khi đó hệ thống phải:
1. CẢNH BÁO rõ ràng rằng PL01 nhiều khả năng sai;
2. KHÔNG dồn cả hồ sơ xuống mục B — nếu dồn thì phần A chỉ còn tiêu đề nhóm,
   tạo ra file sắp xếp rỗng ruột (đúng lỗi người dùng gặp phải).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook

from core.annotator import _phatsinh_block_rows
from core.comparison import scope_mismatch_warnings
from core.config import EnterpriseConfig
from core.tender_package import compare_appendices_with_bidders

SHEET = "1. HT dien"
HEADERS = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá tổng hợp", "Thành tiền"]


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _write(path: Path, sheet: str, rows: list[list]) -> None:
    wb = Workbook(); ws = wb.active; ws.title = sheet
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def _bidder_rows() -> list[list]:
    # Hồ sơ 24 hạng mục tủ điện (trên ngưỡng tối thiểu để guard hoạt động).
    return [
        [str(i), f"TD-{i:02d}", f"Tủ điện nhánh loại {i}", "Cái", i, 1_000_000, i * 1_000_000]
        for i in range(1, 25)
    ]


def _mismatched_pair(tmp_path: Path):
    """PL01 phạm vi hoàn toàn khác (đèn/công tắc) so với hồ sơ (tủ điện)."""
    pl1 = tmp_path / "pl01.xlsx"
    _write(pl1, "KLMT", [
        ["1", "D-001", "Đèn Led Tube 1m2", "Bộ", 5, None, None],
        ["2", "C-001", "Công tắc đơn", "Cái", 8, None, None],
    ])
    bidder = tmp_path / "linh_anh.xlsx"
    _write(bidder, SHEET, _bidder_rows())
    return pl1, bidder


def _compare(tmp_path: Path):
    pl1, bidder = _mismatched_pair(tmp_path)
    return compare_appendices_with_bidders(
        [("Linh Anh", bidder)], tmp_path / "out", pl1_path=pl1, config=_cfg()
    ).result


def test_scope_mismatch_produces_warning(tmp_path: Path):
    result = _compare(tmp_path)
    hits = [w for w in result.warnings if "KHÔNG ghép được với Phụ lục 01" in w]
    assert hits, f"Phải cảnh báo PL01 sai phạm vi. Cảnh báo hiện có: {result.warnings}"
    assert "Linh Anh" in hits[0]


def test_scope_mismatch_does_not_relocate_everything_to_section_b(tmp_path: Path):
    result = _compare(tmp_path)
    # Tất cả hạng mục đều là 'phát sinh' -> KHÔNG được dời dòng nào (giữ file gốc).
    assert _phatsinh_block_rows(result.rows) == {}, (
        "Khi PL01 sai phạm vi, không được dồn cả hồ sơ xuống mục B"
    )


def test_normal_case_still_relocates(tmp_path: Path):
    # Hồ sơ đủ lớn (24 mục) nhưng PL01 ĐÚNG phạm vi: khớp 22/24, chỉ 2 phát sinh
    # thật -> guard không được kích hoạt, phát sinh vẫn phải dời xuống mục B.
    pl1 = tmp_path / "pl01.xlsx"
    _write(pl1, "KLMT", [
        [str(i), f"TD-{i:02d}", f"Tủ điện nhánh loại {i}", "Cái", i, None, None]
        for i in range(1, 23)
    ])
    bidder = tmp_path / "nt.xlsx"
    _write(bidder, SHEET, _bidder_rows())
    result = compare_appendices_with_bidders(
        [("NT A", bidder)], tmp_path / "out", pl1_path=pl1, config=_cfg()
    ).result
    assert not [w for w in result.warnings if "KHÔNG ghép được với Phụ lục 01" in w], (
        "PL01 đúng phạm vi thì không được cảnh báo lệch phạm vi"
    )
    assert _phatsinh_block_rows(result.rows).get(SHEET), (
        "Phát sinh thật vẫn phải được dời xuống mục B"
    )


def test_warning_helper_thresholds():
    class _Row:
        def __init__(self, extra: bool):
            self.bidder = "NT"
            self.candidate = object()
            self.reference = None if extra else object()

    # Đủ lớn + quá nửa phát sinh -> cảnh báo.
    assert scope_mismatch_warnings("Phụ lục 01", [_Row(True)] * 15 + [_Row(False)] * 10)
    # Đủ lớn nhưng phát sinh ít -> không cảnh báo.
    assert not scope_mismatch_warnings("Phụ lục 01", [_Row(True)] * 5 + [_Row(False)] * 20)
    # Hồ sơ quá nhỏ -> không kết luận dù toàn phát sinh (tránh dương tính giả).
    assert not scope_mismatch_warnings("Phụ lục 01", [_Row(True)] * 5)
