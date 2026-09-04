"""Tổng hai bản lệch quá xa mà số hạng mục gần bằng nhau thì phải NGHI NGỜ.

Phản hồi thực tế: báo cáo nói bản mới tăng hơn 100% trong khi giá không hề thay
đổi. Nguyên nhân thường là MỘT BẢN BỊ ĐỌC THIẾU — nhà thầu đổi tên sheet, hoặc
một sheet dùng tiêu đề cột đơn giá lạ nên không đọc được tiền.

Đưa ra con số tăng vọt một cách tự tin trong tình huống đó là tệ hơn im lặng:
người chấm sẽ đi đàm phán dựa trên số sai. Thà nói thẳng là đáng ngờ.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from core.config import EnterpriseConfig
from core.version_compare import compare_quote_versions

HDR = ["STT", "Mã hiệu", "Tên hạng mục", "ĐVT", "KL nhà thầu chào",
       "Đơn giá tổng hợp", "Thành tiền"]


def _book(path: Path, count: int, price_factor: float = 1.0,
          priced_share: float = 1.0) -> Path:
    """``priced_share`` < 1 mô phỏng việc một phần hồ sơ không đọc được tiền."""
    wb = Workbook(); ws = wb.active; ws.title = "PCCC"
    ws.append(list(HDR))
    priced_until = int(count * priced_share)
    for i in range(1, count + 1):
        qty = i * 3
        if i <= priced_until:
            price = round((100_000 + i * 7_531) * price_factor)
            ws.append([str(i), f"HM-{i:03d}", f"Hạng mục số {i}", "cái", qty, price, qty * price])
        else:
            ws.append([str(i), f"HM-{i:03d}", f"Hạng mục số {i}", "cái", qty, None, None])
    wb.save(path)
    return path


def _config() -> EnterpriseConfig:
    cfg = EnterpriseConfig()
    cfg.enable_semantic_matching = False
    cfg.enable_reranker = False
    return cfg


def _warned(result) -> bool:
    return any("ĐỌC THIẾU" in w for w in result.warnings)


def test_warns_when_one_version_reads_almost_no_money(tmp_path: Path):
    # Bản cũ chỉ đọc được tiền ở 1/4 số dòng, nhưng đủ hạng mục.
    old = _book(tmp_path / "v1.xlsx", 40, priced_share=0.25)
    new = _book(tmp_path / "v2.xlsx", 40)
    result = compare_quote_versions(old, new, "NT", config=_config())
    assert _warned(result), "Phải nghi ngờ khi tổng lệch quá xa mà số hạng mục như nhau"
    assert any("Bản cũ" in w for w in result.warnings), "Phải chỉ rõ bản nào đáng ngờ"


def test_no_warning_for_a_genuine_small_increase(tmp_path: Path):
    old = _book(tmp_path / "v1.xlsx", 40)
    new = _book(tmp_path / "v2.xlsx", 40, price_factor=1.05)
    assert not _warned(compare_quote_versions(old, new, "NT", config=_config()))


def test_no_warning_when_the_new_version_really_is_much_bigger(tmp_path: Path):
    # Số hạng mục tăng gấp đôi thì tiền tăng nhiều là hợp lý, không đáng ngờ.
    old = _book(tmp_path / "v1.xlsx", 20)
    new = _book(tmp_path / "v2.xlsx", 60)
    assert not _warned(compare_quote_versions(old, new, "NT", config=_config()))


def test_threshold_is_configurable(tmp_path: Path, monkeypatch):
    import importlib

    import core.version_compare as vc

    old = _book(tmp_path / "v1.xlsx", 40)
    new = _book(tmp_path / "v2.xlsx", 40, price_factor=1.05)
    monkeypatch.setenv("HSMT_VERSION_MONEY_GAP", "0.01")
    reloaded = importlib.reload(vc)
    try:
        result = reloaded.compare_quote_versions(old, new, "NT", config=_config())
        assert any("ĐỌC THIẾU" in w for w in result.warnings)
    finally:
        monkeypatch.delenv("HSMT_VERSION_MONEY_GAP", raising=False)
        importlib.reload(vc)
