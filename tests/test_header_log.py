"""Nhật ký tiêu đề lạ: đủ để nhận dạng cột, không giữ số liệu nhạy cảm.

File Excel không có chuẩn nên sẽ luôn gặp cách đặt tên cột chưa từng thấy. Ghi
lại chúng để định kỳ mở rộng sổ tay từ khóa, thay vì chờ người dùng báo lỗi.

Nguyên tắc: cột CHỮ ghi vài giá trị mẫu ngắn ("cái", "m2") vì đó chính là thứ
cho biết đây là cột đơn vị tính hay thương hiệu; cột SỐ chỉ ghi đặc trưng (số
chữ số, có thập phân không) — với việc phân loại cột thì đặc trưng nói được
nhiều hơn con số, mà lại không đưa đơn giá của nhà thầu vào nhật ký.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.header_log import _profile_column, record_unknown_headers


def _read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ------------------------------------------------------- đặc trưng từng cột

def test_numeric_column_records_shape_not_values():
    profile = _profile_column([1_674_849, 2_500_000, 3_100_000])
    assert profile["kieu"] == "so"
    assert profile["so_chu_so_it_nhat"] == 7
    assert profile["co_phan_thap_phan"] is False
    blob = json.dumps(profile, ensure_ascii=False)
    assert "1674849" not in blob, "Không được ghi đơn giá thật vào nhật ký"


def test_decimal_numbers_are_flagged():
    assert _profile_column([1.05, 2.5, 3.75])["co_phan_thap_phan"] is True


def test_text_column_keeps_short_samples():
    profile = _profile_column(["cái", "m2", "bộ", "cái", "m2"])
    assert profile["kieu"] == "chu"
    assert set(profile["gia_tri_mau"]) == {"cái", "m2", "bộ"}
    assert profile["so_gia_tri_khac_nhau"] == 3


def test_long_text_is_not_kept_as_a_sample():
    long_name = "Cung cấp và lắp đặt đầu báo khói địa chỉ loại quang điện GST kèm đế"
    profile = _profile_column([long_name] * 6)
    assert profile["kieu"] == "chu"
    assert profile["gia_tri_mau"] == [], "Mô tả hạng mục dài không giúp nhận dạng cột"


def test_empty_column():
    assert _profile_column(["", None, "  "])["kieu"] == "trong"


# ------------------------------------------------------------- ghi nhật ký

def _rows() -> list[list]:
    return [[str(i), "cái", 1_674_849] for i in range(1, 26)]


def test_only_unmapped_columns_are_logged(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    record_unknown_headers(
        workbook="hs.xlsx", sheet="PCCC",
        flat_headers=["STT", "Đơn vị lạ", "Giá lạ"],
        mapped_columns={0}, rows=_rows(), log_path=str(log),
    )
    entries = _read(log)[0]["cot_chua_nhan_ra"]
    assert [e["tieu_de"] for e in entries] == ["Đơn vị lạ", "Giá lạ"]
    assert entries[0]["gia_tri_mau"] == ["cái"]
    assert "gia_tri_mau" not in entries[1], "Cột số không giữ giá trị"


def test_nothing_written_when_every_column_is_known(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    record_unknown_headers(
        workbook="hs.xlsx", sheet="PCCC", flat_headers=["STT", "ĐVT"],
        mapped_columns={0, 1}, rows=_rows(), log_path=str(log),
    )
    assert not log.exists()


def test_blank_headers_are_ignored(tmp_path: Path):
    log = tmp_path / "log.jsonl"
    record_unknown_headers(
        workbook="hs.xlsx", sheet="PCCC", flat_headers=["STT", "", "   "],
        mapped_columns={0}, rows=_rows(), log_path=str(log),
    )
    assert not log.exists()


def test_logging_never_breaks_the_caller(tmp_path: Path):
    # Đường dẫn không ghi được cũng không được phép ném lỗi ra ngoài.
    record_unknown_headers(
        workbook="hs.xlsx", sheet="PCCC", flat_headers=["Lạ"],
        mapped_columns=set(), rows=_rows(),
        log_path=str(tmp_path / "khong-ton-tai" / "\0" / "log.jsonl"),
    )


def test_can_be_switched_off(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import importlib

    import core.header_log as hl

    monkeypatch.setenv("HSMT_HEADER_LOG", "0")
    reloaded = importlib.reload(hl)
    try:
        log = tmp_path / "log.jsonl"
        reloaded.record_unknown_headers(
            workbook="hs.xlsx", sheet="PCCC", flat_headers=["Lạ"],
            mapped_columns=set(), rows=_rows(), log_path=str(log),
        )
        assert not log.exists()
    finally:
        monkeypatch.delenv("HSMT_HEADER_LOG", raising=False)
        importlib.reload(hl)


# --------------------------------------- chỉ ghi tiêu đề THỰC SỰ chưa hiểu

def test_ignore_hook_bo_qua_tieu_de_nhom_cha(tmp_path):
    """Tên nhóm cha ("NHÀ THẦU X") không phải cột dữ liệu, đừng ghi vào nhật ký."""
    log = tmp_path / "nk.jsonl"
    record_unknown_headers(
        workbook="a.xlsx", sheet="S", flat_headers=["CÔNG TY ABC", "Cột lạ"],
        mapped_columns=set(), rows=[["x", "y"]], log_path=str(log),
        ignore=lambda raw: raw.startswith("CÔNG TY"),
    )
    ghi = _read(log)
    assert [c["tieu_de"] for c in ghi[0]["cot_chua_nhan_ra"]] == ["Cột lạ"]


def test_cot_khop_luat_nhung_thua_khong_bi_ghi_la_la():
    """Mỗi vai trò chỉ chọn được một cột. Cột "Ghi chú" thứ hai vẫn được LUẬT
    nhận ra, chỉ là thua khi tranh vai trò — ghi nó vào nhật ký sẽ khiến người
    vận hành khai nhầm nó thành một vai trò khác."""
    from core.excel_reader import map_columns
    from core.models import DocumentRole

    flat = ["STT", "Tên hạng mục", "ĐVT", "Khối lượng", "Đơn giá", "Ghi chú", "Ghi chú"]
    nhan_ra: set[int] = set()
    fixed, _tech = map_columns(flat, DocumentRole.HSDT, nhan_ra)

    assert list(fixed.values()).count("note") == 1        # chỉ một cột thắng
    assert {5, 6} <= nhan_ra                              # nhưng cả hai đều được nhận ra
    assert set(fixed) <= nhan_ra
