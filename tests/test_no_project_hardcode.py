"""Bỏ hard-code tên dự án "hacom"/"mall" và tên tầng cố định.

- PL02 của dự án bất kỳ phải đọc được mặc định (không lọc theo tên dự án).
- Cột chia theo tầng được nhận diện chung (Tầng N / Tầng hầm), không phụ thuộc
  danh sách tầng cứng của một công trình cụ thể.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from core.config import EnterpriseConfig
from core.excel_reader import map_columns
from core.models import DocumentRole
from core.pl2_reader import load_pl2_requirements


def _cfg() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _make_pl2_other_project(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "PL02"
    ws.append(["Dự án: KHU ĐÔ THỊ ABC", None, None, None])  # tên dự án KHÁC hacom/mall
    ws.append(["STT", "Tên vật tư thiết bị", "Thương hiệu - Xuất xứ", "Ghi chú"])
    ws.append(["1", "Tủ điện tổng", "Schneider / ABB - EU", ""])
    ws.append(["2", "Cáp đồng XLPE", "Cadivi - Việt Nam", ""])
    wb.save(path)


def test_pl2_of_other_project_is_read_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HSMT_PL2_PROJECT_KEYWORDS", raising=False)
    path = tmp_path / "pl2_abc.xlsx"
    _make_pl2_other_project(path)

    requirements, warnings = load_pl2_requirements(path, config=_cfg())

    # Mặc định KHÔNG lọc theo tên dự án -> phải đọc được yêu cầu vật tư.
    assert len(requirements) == 2
    assert not any("dự án khác" in w.lower() for w in warnings)


def test_pl2_project_filter_can_be_enabled_via_keywords(tmp_path: Path):
    path = tmp_path / "pl2_abc.xlsx"
    _make_pl2_other_project(path)

    # Bật lọc với từ khóa không khớp -> sheet ghi "Dự án..." bị bỏ qua.
    requirements, warnings = load_pl2_requirements(
        path, project_keywords=("hacom", "mall"), config=_cfg()
    )
    assert requirements == []
    assert any("dự án khác" in w.lower() for w in warnings)


def test_pl2_keywords_from_env(tmp_path: Path, monkeypatch):
    path = tmp_path / "pl2_abc.xlsx"
    _make_pl2_other_project(path)
    monkeypatch.setenv("HSMT_PL2_PROJECT_KEYWORDS", "hacom,mall")

    requirements, _warnings = load_pl2_requirements(path, config=_cfg())
    assert requirements == []  # bị lọc vì dự án không khớp từ khóa env


def _technical_labels(flat_headers: list[str]) -> set[str]:
    _fixed, technical = map_columns(flat_headers, DocumentRole.HSDT)
    return set(technical.values())


def test_arbitrary_floor_columns_are_detected_as_technical():
    # Tầng bất kỳ (7, 30, hầm) phải được nhận là cột kỹ thuật, không chỉ 1..5/23.
    headers = ["STT", "Diễn giải", "ĐVT", "Tầng 7", "Tầng 30", "Tầng hầm"]
    labels = _technical_labels(headers)
    assert "Tầng 7" in labels
    assert "Tầng 30" in labels
    assert "Tầng hầm" in labels


def test_non_floor_columns_not_misdetected_as_floor():
    headers = ["STT", "Diễn giải", "ĐVT", "Khối lượng", "Đơn giá tổng hợp"]
    labels = _technical_labels(headers)
    # Không có cột kỹ thuật giả nào sinh ra từ các cột thường.
    assert "Khối lượng" not in labels
