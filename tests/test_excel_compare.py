from pathlib import Path

from openpyxl import Workbook

from core.config import EnterpriseConfig
from core.models import Severity
from core.pipeline import compare_tender_files, compare_bidder_files


def make_book(path: Path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Điện"
    ws.append(["Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá", "Thành tiền"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_missing_and_zero_are_not_silently_ok(tmp_path):
    hsmt = tmp_path / "hsmt.xlsx"
    bid = tmp_path / "bid.xlsx"
    make_book(hsmt, [
        ["M-01", "Tủ điện tổng", "Tủ", 2, 1000, 2000],
        ["M-02", "Cáp điện Cu XLPE", "m", 10, 100, 1000],
    ])
    make_book(bid, [
        ["M-01", "Tủ điện tổng", "Tủ", 2, 1000, 0],
    ])
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    result = compare_tender_files(hsmt, [("A", bid)], config=cfg)
    row1 = next(r for r in result.rows if r.reference and r.reference.item_code == "M-01")
    row2 = next(r for r in result.rows if r.reference and r.reference.item_code == "M-02")
    assert row1.candidate.amount == 0
    assert row1.severity is Severity.CRITICAL
    assert row2.match.kind.value == "missing"
    assert row2.severity is Severity.CRITICAL


def test_multi_bidder_consensus_flags_outlier(tmp_path):
    files = []
    for name, price in [("A", 100), ("B", 105), ("C", 500), ("D", 98)]:
        path = tmp_path / f"{name}.xlsx"
        make_book(path, [["M-01", "Cáp điện Cu XLPE 4x10", "m", 10, price, 10*price]])
        files.append((name, path))
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    result = compare_bidder_files(files, config=cfg)
    outlier = next(r for r in result.rows if r.bidder == "C")
    assert outlier.consensus_price is not None
    assert outlier.severity in {Severity.WARNING, Severity.CRITICAL}
    assert any("trung vị" in f.lower() for f in outlier.flags)


def test_same_code_different_name_is_flagged(tmp_path):
    hsmt = tmp_path / "hsmt_name.xlsx"
    bid = tmp_path / "bid_name.xlsx"
    make_book(hsmt, [["M-01", "Tủ điện phân phối tổng", "Tủ", 1, 1000, 1000]])
    make_book(bid, [["M-01", "Máy bơm nước chữa cháy", "Tủ", 1, 1000, 1000]])
    cfg = EnterpriseConfig(); cfg.enable_semantic_matching = False
    result = compare_tender_files(hsmt, [("A", bid)], config=cfg)
    row = result.rows[0]
    assert row.severity in {Severity.WARNING, Severity.CRITICAL}
    assert any("trùng mã" in flag.lower() and "tên" in flag.lower() for flag in row.flags)


def test_duplicate_code_is_preserved_and_flagged(tmp_path):
    hsmt = tmp_path / "hsmt_dup.xlsx"
    bid = tmp_path / "bid_dup.xlsx"
    make_book(hsmt, [
        ["M-01", "Tủ điện tổng", "Tủ", 1, 1000, 1000],
        ["M-01", "Tủ điện nhánh", "Tủ", 1, 900, 900],
    ])
    make_book(bid, [
        ["M-01", "Tủ điện tổng", "Tủ", 1, 1000, 1000],
        ["M-01", "Tủ điện nhánh", "Tủ", 1, 900, 900],
    ])
    cfg = EnterpriseConfig(); cfg.enable_semantic_matching = False
    result = compare_tender_files(hsmt, [("A", bid)], config=cfg)
    assert len([r for r in result.rows if r.reference is not None]) == 2
    assert any("mã hiệu trùng" in flag.lower() for r in result.rows for flag in r.flags)
