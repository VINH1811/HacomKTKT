"""Phần E — Trải nghiệm người dùng (E-01 → E-04).

E là nhóm test VỚI NGƯỜI THẬT (quan sát thao tác), không tự động hóa hoàn toàn:
  - E-01 (tự tìm cách upload) và E-04 (thu thập điểm tắc nghẽn UX) -> CHỈ làm tay,
    không có test tự động ở đây.
  - E-02 (đọc kết quả, biết NT nào nặng nhất): tự động hóa được phần NỀN TẢNG —
    dữ liệu kết quả phải đủ để xếp hạng nhà thầu theo số cờ nghiêm trọng.
  - E-03 (tự đổi ngưỡng): tự động hóa được phần NỀN TẢNG — ngưỡng nhập từ giao
    diện phải chảy đúng vào cấu hình so sánh và có tác dụng.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from openpyxl import Workbook

from app import _build_config
from core.config import EnterpriseConfig
from core.models import Severity
from core.tender_package import compare_appendices_with_bidders


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _write(path: Path, rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng mời thầu",
               "Khối lượng nhà thầu chào", "Đơn giá tổng hợp", "Thành tiền"])
    for r in rows:
        ws.append(r)
    wb.save(path)


# --- E-03 (nền tảng): ngưỡng từ giao diện chảy đúng vào cấu hình --------------

def test_e03_ui_threshold_values_flow_into_config():
    payload = {
        "price_warn_pct": 0.07,
        "price_critical_pct": 0.20,
        "quantity_warn_pct": 0.03,
        "quantity_critical_pct": 0.12,
    }
    cfg = _build_config(payload)
    assert cfg.thresholds.price_warn_pct == 0.07
    assert cfg.thresholds.price_critical_pct == 0.20
    assert cfg.thresholds.quantity_warn_pct == 0.03
    assert cfg.thresholds.quantity_critical_pct == 0.12


def test_e03_defaults_used_when_not_provided():
    cfg = _build_config({})
    # Có giá trị mặc định hợp lý, không lỗi khi thiếu tham số.
    assert cfg.thresholds.quantity_warn_pct == 0.05
    assert cfg.thresholds.price_warn_pct == 0.10


# --- E-02 (nền tảng): kết quả đủ để xếp hạng nhà thầu nặng/nhẹ ----------------

def test_e02_result_lets_us_rank_bidders_by_severity(tmp_path: Path):
    pl1 = tmp_path / "pl1.xlsx"
    _write(pl1, [
        ["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_000_000, 2_000_000],
        ["2", "M-02", "Cáp đồng XLPE", "m", 100, 100, 50_000, 5_000_000],
        ["3", "M-03", "Máy bơm", "Bộ", 1, 1, 12_000_000, 12_000_000],
    ])
    # NT XẤU: thiếu 1 hạng mục + lệch khối lượng lớn.
    bad = tmp_path / "bad.xlsx"
    _write(bad, [
        ["1", "M-01", "Tủ điện tổng", "Cái", 2, 5, 1_000_000, 5_000_000],   # lệch KL 150%
        ["2", "M-02", "Cáp đồng XLPE", "m", 100, 100, 50_000, 5_000_000],
        # thiếu M-03
    ])
    # NT TỐT: khớp hết.
    good = tmp_path / "good.xlsx"
    _write(good, [
        ["1", "M-01", "Tủ điện tổng", "Cái", 2, 2, 1_000_000, 2_000_000],
        ["2", "M-02", "Cáp đồng XLPE", "m", 100, 100, 50_000, 5_000_000],
        ["3", "M-03", "Máy bơm", "Bộ", 1, 1, 12_000_000, 12_000_000],
    ])

    out = compare_appendices_with_bidders(
        bidder_files=[("NT Tốt", good), ("NT Xấu", bad)],
        output_dir=tmp_path / "out", pl1_path=pl1, pl2_path=None, config=_cfg(),
    )

    # Mỗi dòng kết quả có tên nhà thầu + mức độ -> xếp hạng được.
    severe = Counter()
    for row in out.result.rows:
        if row.severity in {Severity.WARNING, Severity.CRITICAL}:
            severe[row.bidder] += 1

    assert severe["NT Xấu"] > severe["NT Tốt"], \
        "Phải xác định được NT Xấu có nhiều vấn đề nghiêm trọng hơn NT Tốt"

    # NT Xấu phải có hạng mục thiếu (M-03) -> đúng là hồ sơ có vấn đề nặng.
    missing_bad = [r for r in out.result.rows
                   if r.bidder == "NT Xấu" and r.match.kind.value == "missing"]
    assert missing_bad, "NT Xấu thiếu hạng mục M-03 phải được ghi nhận"
