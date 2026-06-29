"""Phần D — Ngưỡng cảnh báo (D-01 → D-06).

Kiểm tra hành vi ở biên ngưỡng khối lượng và so sánh giá ngang hàng. Ngưỡng được
đặt tường minh theo kịch bản (MED=5%, HIGH=20%) đúng tinh thần D-05: ngưỡng phải
cấu hình được và có tác dụng thật.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from core.comparison import build_bidder_rows
from core.config import EnterpriseConfig
from core.matcher import match_items
from core.models import CompareThresholds, DocumentRole, ItemRecord, RowType, Severity
from core.pipeline import compare_bidder_files
from core.text_normalizer import normalize_code, normalize_name, normalize_unit


def _item(role: DocumentRole, ref_qty=None, bid_qty=None, price=100) -> ItemRecord:
    return ItemRecord(
        source_id="x", role=role, bidder="b", workbook="w.xlsx", sheet="S", row_number=2,
        item_code="M01", item_name="Cáp đồng XLPE", unit="m",
        reference_quantity=ref_qty, bid_quantity=bid_qty, unit_price_total=price,
        row_type=RowType.DETAIL, normalized_code=normalize_code("M01"),
        normalized_name=normalize_name("Cáp đồng XLPE"), normalized_unit=normalize_unit("m"),
    )


def _quantity_severity(bid_qty: float, *, warn=0.05, crit=0.20):
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.thresholds = CompareThresholds(quantity_warn_pct=warn, quantity_critical_pct=crit)
    ref = [_item(DocumentRole.HSMT, ref_qty=100)]
    cand = [_item(DocumentRole.HSDT, ref_qty=100, bid_qty=bid_qty)]
    rows = build_bidder_rows(ref, cand, "NT A", match_items(ref, cand, cfg), cfg, reference_is_boq=True)
    diffs = [d for r in rows for d in r.differences
             if "khối lượng nhà thầu chào so" in str(d.field).lower()]
    return [d.severity for d in diffs]


# --- D-01..D-04: biên ngưỡng khối lượng (MED=5%, HIGH=20%) --------------------

def test_d01_quantity_below_med_threshold_no_flag():
    assert _quantity_severity(104.9) == []  # 4.9% < 5%


def test_d02_quantity_just_above_med_is_warning():
    sev = _quantity_severity(105.1)  # 5.1%
    assert sev == [Severity.WARNING]


def test_d03_quantity_below_high_is_still_warning_not_critical():
    sev = _quantity_severity(119.9)  # 19.9% < 20%
    assert sev == [Severity.WARNING]


def test_d04_quantity_above_high_is_critical():
    sev = _quantity_severity(120.1)  # 20.1% >= 20%
    assert sev == [Severity.CRITICAL]


# --- D-05: thay ngưỡng -> kết quả thay đổi ------------------------------------

def test_d05_changing_threshold_changes_result():
    # Cùng mức lệch 4%: với ngưỡng MED=3% -> cảnh báo; với MED=5% -> không.
    assert _quantity_severity(104, warn=0.03) == [Severity.WARNING]
    assert _quantity_severity(104, warn=0.05) == []


# --- D-06: so sánh giá ngang hàng giữa nhiều nhà thầu ------------------------

def _bidder_book(path: Path, price: float) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BOQ"
    ws.append(["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá tổng hợp", "Thành tiền"])
    ws.append(["1", "M-01", "Tủ điện tổng", "Cái", 1, price, price])
    wb.save(path)


def test_d06_price_outlier_among_bidders_is_flagged(tmp_path: Path):
    # 3 nhà thầu: 100k, 105k, 200k -> NT cao bất thường (200k) phải bị gắn cờ giá.
    prices = {"NT1": 100_000, "NT2": 105_000, "NT3 cao": 200_000}
    bidder_files = []
    for name, price in prices.items():
        p = tmp_path / f"{name}.xlsx"
        _bidder_book(p, price)
        bidder_files.append((name, p))
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False

    result = compare_bidder_files(bidder_files, config=cfg)

    # Tìm dòng của NT3 và kiểm tra có cờ so sánh giá ngang hàng.
    nt3_rows = [r for r in result.rows if r.bidder == "NT3 cao"]
    price_diffs = [d for r in nt3_rows for d in r.differences
                   if "so sánh ngang hàng" in str(d.field).lower() and "đơn giá" in str(d.field).lower()]
    assert price_diffs, "NT3 (giá 200k) phải bị gắn cờ giá cao bất thường"
    # Trung vị nhóm phải được nêu trong thông báo (median của 100/105/200 = 105k).
    assert any("105" in str(d.reference_value) for d in price_diffs)
