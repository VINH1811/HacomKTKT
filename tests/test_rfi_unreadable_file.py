"""Không đọc được bảng làm rõ thì phải báo, không được trả về 0 yêu cầu.

Trả về "0 yêu cầu làm rõ" khi thật ra không đọc được bảng là kết luận ngược
hoàn toàn: chuyên viên hiểu là nhà thầu không phải làm rõ gì.

Trong gói thầu thật có hai loại bảng khác nhau — làm rõ HSCG (chủ đầu tư yêu
cầu, nhà thầu trả lời) và làm rõ HSYC (nhà thầu hỏi, chủ đầu tư trả lời) —
chức năng này chỉ xử lý loại thứ nhất, nên phải nói rõ điều đó.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from core.models import UserFacingError
from core.rfi_tracker import STATUS_ANSWERED, STATUS_UNANSWERED, describe_headers, track_rfi


def _hsyc_style(path: Path) -> Path:
    """Bảng làm rõ HSYC — đúng cấu trúc thật, nhưng không phải loại được hỗ trợ."""
    wb = Workbook(); ws = wb.active; ws.title = "RFI 01.01"
    ws.append(["GÓI THẦU: CUNG CẤP VTTB"])
    ws.append([])
    ws.append(["STT", "CÂU HỎI NHÀ THẦU", "THAM CHIẾU ĐẾN",
               "TVTK TRẢ LỜI", "CHỦ ĐẦU TƯ TRẢ LỜI", "GHI CHÚ"])
    ws.append(["1", "Đề nghị làm rõ phạm vi cấp nguồn", "", "", "Theo hồ sơ thiết kế", ""])
    wb.save(path)
    return path


def _hscg_style(path: Path) -> Path:
    wb = Workbook(); ws = wb.active; ws.title = "PL 1"
    ws.append(["STT", "Nội dung đánh giá theo HSYC", "Yêu cầu",
               "Nhà thầu kê khai", "Ý kiến CĐT", "Nhà thầu trả lời làm rõ"])
    ws.append(["1", "Hiệu lực hồ sơ", "90 ngày", "60 ngày",
               "Đề nghị gia hạn lên 90 ngày", "Nhà thầu đồng ý gia hạn"])
    ws.append(["2", "Doanh thu bình quân", "≥ 50 tỷ", "42 tỷ",
               "Đề nghị giải trình", ""])
    wb.save(path)
    return path


def test_unsupported_layout_raises_instead_of_zero(tmp_path: Path):
    path = _hsyc_style(tmp_path / "hsyc.xlsx")
    with pytest.raises(UserFacingError) as excinfo:
        track_rfi(path, path, "Nhà thầu A")
    message = str(excinfo.value)
    assert "Không tìm thấy bảng làm rõ" in message
    assert "HSYC" in message, "Phải nói rõ loại bảng nào chưa hỗ trợ"
    assert "Tiêu đề đọc được" in message, "Phải kèm tiêu đề để người dùng đối chiếu"


def test_supported_layout_still_works(tmp_path: Path):
    path = _hscg_style(tmp_path / "hscg.xlsx")
    result = track_rfi(path, path, "Nhà thầu A")
    assert len(result.items) == 2
    assert result.count(STATUS_ANSWERED) == 1
    assert result.count(STATUS_UNANSWERED) == 1


def test_describe_headers_reports_what_was_read(tmp_path: Path):
    seen = describe_headers(_hsyc_style(tmp_path / "hsyc.xlsx"))
    assert "CÂU HỎI NHÀ THẦU" in seen and "RFI 01.01" in seen
