"""Phần C — Đối chiếu tool vs đọc tay (C-01 → C-03).

Việc "đọc tay" của con người không tự động hóa được, nhưng phần lõi của C-03 —
ĐO độ chính xác của tool so với một "đáp án biết trước" — thì tự động hóa được.

Ta dựng một bộ KLMT + 1 hồ sơ nhà thầu với các sai lệch ĐÃ BIẾT TRƯỚC, chạy tool,
rồi kiểm tra tool:
  - Bắt đúng các sai lệch cần bắt (không bỏ sót / false negative),
  - Không gắn cờ các dòng vốn khớp hoàn toàn (không báo nhầm / false positive).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from core.config import EnterpriseConfig
from core.models import MatchKind, Severity
from core.tender_package import compare_appendices_with_bidders


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append(header)
    for r in rows:
        ws.append(r)
    wb.save(path)


_PL1_HEADER = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá tổng hợp", "Thành tiền"]
# Hồ sơ chào giá thực tế có CẢ cột KL mời thầu lẫn KL nhà thầu chào.
_NT_HEADER = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu",
              "Khối lượng nhà thầu chào", "Đơn giá tổng hợp", "Thành tiền"]


def _make_ground_truth(tmp_path: Path):
    """KLMT 4 hạng mục; hồ sơ NT có sai lệch biết trước:
       - HM1: khớp hoàn toàn  -> KHÔNG được gắn cờ
       - HM2: lệch khối lượng 30% -> phải gắn cờ
       - HM3: KLMT có nhưng NT thiếu -> MISSING
       - HM4: khớp + NT thêm 1 hạng mục ngoài KLMT -> EXTRA
    """
    pl1 = tmp_path / "klmt.xlsx"
    _write(pl1, _PL1_HEADER, [
        ["1", "M-01", "Tủ điện tổng", "Cái", 2, 1_000_000, 2_000_000],
        ["2", "M-02", "Cáp đồng XLPE 4x10", "m", 100, 50_000, 5_000_000],
        ["3", "M-03", "Máy bơm nước thải", "Bộ", 1, 12_000_000, 12_000_000],
        ["4", "M-04", "Đèn LED downlight", "Bộ", 50, 200_000, 10_000_000],
    ])
    bidder = tmp_path / "nt.xlsx"
    _write(bidder, _NT_HEADER, [
        # STT, mã, tên, ĐVT, KL mời thầu, KL NT chào, đơn giá, thành tiền
        ["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_050_000, 2_100_000],       # khớp
        ["2", "M-02", "Cáp đồng XLPE 4x10", "m", 100, 130, 52_000, 6_760_000],  # NT chào lệch 30%
        # M-03 bị thiếu (không có dòng)
        ["4", "M-04", "Đèn LED downlight", "Bộ", 50, 50, 205_000, 10_250_000],  # khớp
        ["5", "M-99", "Chi phí vận chuyển phát sinh", "Lần", 1, 1, 3_000_000, 3_000_000],  # EXTRA
    ])
    return pl1, bidder


def test_c03_tool_catches_known_deviations_without_false_positives(tmp_path: Path):
    pl1, bidder = _make_ground_truth(tmp_path)
    out = compare_appendices_with_bidders(
        bidder_files=[("NT A", bidder)],
        output_dir=tmp_path / "out",
        pl1_path=pl1, pl2_path=None, config=_cfg(),
    )
    rows = out.result.rows

    def find(code):
        for r in rows:
            item = r.reference or r.candidate
            if item and item.item_code == code:
                return r
        return None

    # HM1 (M-01) khớp hoàn toàn -> KHÔNG có báo động lệch khối lượng (WARNING/CRITICAL).
    r1 = find("M-01")
    assert r1 is not None and r1.match.kind not in {MatchKind.MISSING, MatchKind.EXTRA}
    r1_qty_alarms = [d for d in r1.differences
                     if "khối lượng" in str(d.field).lower() and d.severity in {Severity.WARNING, Severity.CRITICAL}]
    assert not r1_qty_alarms, "Dòng khớp hoàn toàn không được báo động lệch khối lượng (false positive)"

    # HM2 (M-02) lệch khối lượng 30% -> phải có báo động lệch (WARNING trở lên).
    r2 = find("M-02")
    assert r2 is not None
    r2_qty_alarms = [d for d in r2.differences
                     if "khối lượng" in str(d.field).lower() and d.severity in {Severity.WARNING, Severity.CRITICAL}]
    assert r2_qty_alarms, "Phải bắt được lệch khối lượng 30% (tránh false negative)"

    # HM3 (M-03) thiếu -> MISSING / CRITICAL.
    r3 = find("M-03")
    assert r3 is not None and r3.match.kind is MatchKind.MISSING

    # HM5 (M-99) phát sinh ngoài KLMT -> EXTRA.
    r5 = find("M-99")
    assert r5 is not None and r5.match.kind is MatchKind.EXTRA

    # Tổng quan: đúng 1 thiếu và 1 phát sinh, không nhiều hơn (không nhiễu).
    assert out.result.summary.missing_items == 1
    assert out.result.summary.extra_items == 1
