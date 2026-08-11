"""Thông báo lỗi phải gọi file bằng đúng tên người dùng đã tải lên.

Khi lưu, mỗi file được thêm tiền tố thứ tự ("000_", "001_") để hai file trùng
tên không đè nhau. Hệ thống đã có sẵn bước đổi ngược về tên gốc, nhưng bước đó
chỉ chạy cho lỗi ngoài dự kiến — còn UserFacingError, tức đúng loại thông báo
người dùng hay gặp nhất, lại đi thẳng qua. Người đọc thấy tên lạ sẽ tưởng hệ
thống đã sửa file của mình.
"""

from __future__ import annotations

from app import restore_original_names


def test_stored_name_is_replaced_by_original():
    request = {
        "request_file": "000_Lam ro.xlsx",
        "request_original": "251106_Nội dung làm rõ HSCG_Vân Khánh.xlsx",
    }
    message = "Không tìm thấy bảng làm rõ trong '000_Lam ro.xlsx'."
    assert restore_original_names(message, request) == (
        "Không tìm thấy bảng làm rõ trong "
        "'251106_Nội dung làm rõ HSCG_Vân Khánh.xlsx'."
    )


def test_bidder_entries_are_restored():
    request = {"bidders": [{"file": "002_hs.xlsx", "original_name": "Chào giá Linh Anh V2.xlsx"}]}
    out = restore_original_names("Không đọc được file '002_hs.xlsx'", request)
    assert "Chào giá Linh Anh V2.xlsx" in out and "002_hs.xlsx" not in out


def test_prefix_is_stripped_even_without_request():
    out = restore_original_names("Lỗi ở file '001_bang_chao_gia.xlsx' rồi", None)
    assert "001_" not in out and "bang_chao_gia.xlsx" in out


def test_ordinary_numbers_are_left_alone():
    # Không được cắt nhầm số trong nội dung nghiệp vụ.
    for message in ("Mã hiệu 250_A không khớp",
                    "Chênh lệch 100_000 đồng",
                    "Sheet '1. HT điện' dòng 123_456"):
        assert restore_original_names(message, None) == message


def test_empty_message_is_safe():
    assert restore_original_names("", {"a_file": "x"}) == ""
    assert restore_original_names("không sao", None) == "không sao"
