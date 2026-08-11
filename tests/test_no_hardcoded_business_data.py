"""Không gắn cứng tên khách hàng, và mọi ngưỡng/từ vựng phải cấu hình được.

Hệ thống dùng cho nhiều gói thầu khác nhau, nên tên nhà thầu, tên dự án và các
ngưỡng nghiệp vụ không được nằm trong mã. Trước đây script gom dữ liệu giá liệt
kê sẵn năm nhà thầu bằng if/elif và ghi cố định tên dự án, năm, vùng miền.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.bidder_name import (
    BIDDER_NOISE,
    COLUMN_NOISE,
    guess_bidder_from_column,
    guess_bidder_from_context,
    guess_bidder_name,
    strip_shared_tokens,
)
from core.dossier_check import DEFAULT_CHECKLIST, load_checklist
from core.env_config import env_bool, env_float, env_groups, env_int, env_terms

ROOT = Path(__file__).resolve().parent.parent
# Tên riêng của khách hàng/dự án cụ thể — không được xuất hiện trong mã nguồn.
_CUSTOMER_NAMES = re.compile(
    r"linh\s*anh|searefico|van\s*khanh|vân\s*khánh|tri\s*trung|trí\s*trung|"
    r"van\s*lang|hacom|vạn\s*hòa|noxh",
    re.IGNORECASE,
)
_SCANNED = ["core", "ocr", "security", "scripts"]


def _python_files() -> list[Path]:
    files = [ROOT / "app.py"]
    for folder in _SCANNED:
        files.extend(sorted((ROOT / folder).rglob("*.py")))
    return [f for f in files if "__pycache__" not in f.parts]


def test_no_customer_names_in_source():
    offenders: list[str] = []
    for path in _python_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or not _CUSTOMER_NAMES.search(line):
                continue
            offenders.append(f"{path.relative_to(ROOT)}:{number}: {stripped[:70]}")
    assert not offenders, "Tên khách hàng/dự án bị gắn cứng:\n" + "\n".join(offenders)


def test_no_absolute_paths_in_source():
    pattern = re.compile(r"""["']([A-Za-z]:[\\/]|/home/|/Users/)""")
    offenders = [
        f"{path.relative_to(ROOT)}:{number}"
        for path in _python_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line) and not line.strip().startswith("#")
    ]
    assert not offenders, f"Đường dẫn tuyệt đối bị gắn cứng: {offenders}"


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("Ho so du thau_Cong ty ABC_Rev01.xlsx", "Cong ty ABC"),
        ("BOQ MEP_KHANH HOA_Rev00.xlsx", "KHANH HOA"),
        ("2. 2025.12.09 Chao gia ME Cong ty XYZ V2.xlsx", "Cong ty XYZ"),
    ],
)
def test_bidder_name_is_derived_not_listed(filename: str, expected: str):
    # Không có danh sách nhà thầu nào trong mã: tên suy ra từ chính tên file.
    assert guess_bidder_name(filename).strip() == expected


def test_project_name_is_removed_only_across_several_files():
    # Một file đơn lẻ không biết đâu là tên dự án, đâu là tên nhà thầu.
    single = guess_bidder_name("Chao gia Du an X Cong ty ABC.xlsx")
    assert single == "Du an X Cong ty ABC"
    # Có nhiều file thì phần dùng chung lộ ra và bị loại.
    names = [
        guess_bidder_name("Chao gia Du an X Cong ty ABC.xlsx"),
        guess_bidder_name("Chao gia Du an X Cong ty DEF.xlsx"),
        guess_bidder_name("Chao gia Du an X Cong ty GHI.xlsx"),
    ]
    assert strip_shared_tokens(names) == ["ABC", "DEF", "GHI"]


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Đơn giá Cong ty ABC", "Cong ty ABC"),
        ("ĐƠN GIÁ - CÔNG TY ABC", "CÔNG TY ABC"),
        ("Đơn giá", ""),                 # tiêu đề chung, không phải tên ai
        ("Đơn giá tổng hợp", ""),
        ("Thành tiền (VNĐ)", ""),
        ("KL Nhà thầu chào", ""),
        ("Đơn giá VL chính", ""),
        ("CP quản lý", ""),
    ],
)
def test_column_title_yields_only_real_names(title: str, expected: str):
    assert guess_bidder_from_column(title) == expected


@pytest.mark.parametrize("name", ["Chaozhou", "Vatico", "Statco", "Advantech"])
def test_generic_terms_do_not_eat_into_real_names(name: str):
    # Thiếu ranh giới từ thì "chao" cắt "Chaozhou" thành "zhou".
    assert guess_bidder_from_column(f"Đơn giá {name}") == name


def test_noise_patterns_have_no_broken_escapes():
    # \b viết sai thành ký tự backspace thì cả nhóm từ khoá không bao giờ khớp.
    for pattern in (BIDDER_NOISE, COLUMN_NOISE):
        assert "\x08" not in pattern.pattern


def test_shared_tokens_tolerate_a_stray_file():
    # Quét cả thư mục thường lẫn file lạ; nếu đòi token phải có ở MỌI tên thì
    # chỉ một file lạ cũng đủ làm tên dự án không bị loại.
    names = ["Du an X Cong ty ABC", "Du an X Cong ty DEF",
             "Du an X Cong ty GHI", "Bang tong hop ket qua"]
    assert strip_shared_tokens(names) == names          # mặc định: không đổi
    relaxed = strip_shared_tokens(names, min_ratio=0.6)
    assert relaxed[:3] == ["ABC", "DEF", "GHI"]


def test_shared_tokens_never_empty_a_name():
    # Mọi token đều dùng chung -> phải giữ nguyên tên, không trả về rỗng.
    assert strip_shared_tokens(["Cong ty ABC", "Cong ty ABC"], min_ratio=0.5) == \
        ["Cong ty ABC", "Cong ty ABC"]


def test_context_falls_back_between_sources():
    # Tiêu đề cột không ra tên thì lấy từ tên file.
    assert guess_bidder_from_context("Đơn giá", "Chao gia Cong ty ABC.xlsx") == "Cong ty ABC"
    assert guess_bidder_from_context("", "") == ""


def test_env_helpers_clamp_and_fall_back(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X_F", "9.9")
    assert env_float("X_F", 0.5, 0.0, 1.0) == 1.0          # kẹp về biên trên
    monkeypatch.setenv("X_F", "khong-phai-so")
    assert env_float("X_F", 0.5, 0.0, 1.0) == 0.5          # sai định dạng -> mặc định
    monkeypatch.setenv("X_I", "0")
    assert env_int("X_I", 40, 2, 100) == 2
    monkeypatch.setenv("X_B", "có")
    assert env_bool("X_B", False) is True
    assert env_bool("X_CHUA_DAT", True) is True


def test_env_vocabulary_is_extendable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("X_TERMS", " Lô , gói ,, ")
    assert env_terms("X_TERMS") == {"lô", "gói"}
    monkeypatch.setenv("X_GROUPS", "be tong,nhua duong;m250,m300,m350")
    assert env_groups("X_GROUPS") == (("be tong", "nhua duong"), ("m250", "m300", "m350"))
    # Nhóm chỉ có một từ thì vô nghĩa, phải bỏ.
    monkeypatch.setenv("X_GROUPS", "mot-tu")
    assert env_groups("X_GROUPS") == ()


def test_dossier_checklist_is_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    assert load_checklist() is DEFAULT_CHECKLIST

    path = tmp_path / "checklist.json"
    path.write_text(json.dumps([
        {"key": "don", "label": "Đơn chào giá", "patterns": [r"don\s*chao\s*gia"]},
        {"key": "bctc", "label": "Báo cáo tài chính (5 năm)",
         "patterns": [r"bao\s*cao\s*tai\s*chinh"], "min_count": 5},
    ]), encoding="utf-8")
    monkeypatch.setenv("HSMT_DOSSIER_CHECKLIST", str(path))
    custom = load_checklist()
    assert [i.min_count for i in custom] == [1, 5]

    # Tệp hỏng thì quay về bộ mặc định, không được chấm thiếu tài liệu oan.
    monkeypatch.setenv("HSMT_DOSSIER_CHECKLIST", str(tmp_path / "khong-ton-tai.json"))
    assert load_checklist() is DEFAULT_CHECKLIST


def test_skip_sheets_is_extendable(monkeypatch: pytest.MonkeyPatch):
    import importlib

    import core.excel_reader as reader

    monkeypatch.setenv("HSMT_SKIP_SHEETS", "phu luc rieng, bang ke")
    reloaded = importlib.reload(reader)
    try:
        assert "phu luc rieng" in reloaded.SKIP_SHEETS
        assert "bang ke" in reloaded.SKIP_SHEETS
        assert "tong hop" in reloaded.SKIP_SHEETS, "Bộ mặc định phải được giữ"
    finally:
        monkeypatch.delenv("HSMT_SKIP_SHEETS", raising=False)
        importlib.reload(reader)
