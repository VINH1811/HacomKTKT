"""Tách tên nhà thầu từ tên file KHÔNG được gắn cứng tên dự án/gói thầu cụ thể.

Bộ tách chỉ loại thuật ngữ đấu thầu chung; tên dự án dùng chung được loại tự
động qua _strip_shared_tokens — nên hàm phải hoạt động đúng cho GÓI THẦU BẤT KỲ,
không chỉ gói Hacom Mall đã dùng khi phát triển.
"""

from __future__ import annotations

import app
from core.bidder_name import BIDDER_NOISE, guess_bidder_name, strip_shared_tokens


def test_guess_strips_generic_tender_terms():
    assert app._guess_bidder_name("251106_Noi dung lam ro HSCG_Searefico.xlsx") == "Searefico"
    assert app._guess_bidder_name(
        "1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx"
    ) == "Hacom Mall Linh Anh"  # tên dự án còn lại khi CHỈ CÓ 1 file (sẽ được strip khi có nhiều file)


def test_no_hardcoded_project_name_in_noise_list():
    # Không được gắn cứng "hacom"/"mall" (hoặc bất kỳ tên dự án nào) trong bộ lọc.
    # Bộ lọc nay nằm ở core/bidder_name.py để script xử lý dữ liệu dùng chung.
    pattern = BIDDER_NOISE.pattern.lower()
    assert "hacom" not in pattern
    assert "mall" not in pattern


def test_app_reuses_the_shared_module():
    # Web và script phải dùng CÙNG một bộ luật, nếu không sẽ đoán ra hai tên khác nhau.
    assert app._guess_bidder_name is guess_bidder_name
    assert app._strip_shared_tokens is strip_shared_tokens


def test_shared_token_stripping_isolates_bidder_hacom():
    names = [
        app._guess_bidder_name("1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2.xlsx"),
        app._guess_bidder_name("2. 2025.12.09 Chao gia ME Hacom Mall Van Lang Tri Trung V2.xlsx"),
        app._guess_bidder_name("4. 2025.12.08 Chao gia ME Hacom Mall Van Khanh V2.xlsx"),
    ]
    assert app._strip_shared_tokens(names) == ["Linh Anh", "Van Lang Tri Trung", "Van Khanh"]


def test_shared_token_stripping_generalizes_to_other_project():
    # Dự án hoàn toàn khác (không có trong code) vẫn tách đúng -> chứng minh không overfit.
    names = [
        app._guess_bidder_name("BOQ Chao gia Vinhomes Grand Park Cong ty ABC.xlsx"),
        app._guess_bidder_name("BOQ Chao gia Vinhomes Grand Park Cong ty XYZ.xlsx"),
    ]
    assert app._strip_shared_tokens(names) == ["ABC", "XYZ"]


def test_single_file_left_unchanged_by_stripping():
    assert app._strip_shared_tokens(["Linh Anh"]) == ["Linh Anh"]


def test_stripping_never_empties_identical_names():
    # Hai file cùng nhà thầu (mọi token chung) -> KHÔNG được ra tên rỗng.
    out = app._strip_shared_tokens(["Linh Anh", "Linh Anh"])
    assert out == ["Linh Anh", "Linh Anh"]
