#!/usr/bin/env python3
"""
Chạy toàn bộ pytest trong thư mục tests và tạo báo cáo giải thích chi tiết,
có ví dụ cụ thể để người không chuyên cũng hiểu.

Đầu ra:
    reports/test_reports/test_report_YYYYMMDD_HHMMSS/
        report.html
        report.md
        report.json
        junit.xml
        pytest_console.txt

Chạy:
    python run_all_tests.py
    python run_all_tests.py --quiet
    python run_all_tests.py --coverage --cov-target core
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import dataclasses
import datetime as dt
import html
import importlib.util
import inspect
import io
import json
import platform
import re
import subprocess
import sys
import textwrap
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import pytest
except ModuleNotFoundError:
    print(
        'Chưa cài pytest. Chạy: python -m pip install "pytest>=8.2,<9"',
        file=sys.stderr,
    )
    raise SystemExit(2)


REPORT_VERSION = "4.0.0"
MAX_TRACEBACK_CHARS = 40_000
MAX_CAPTURE_CHARS = 20_000
MAX_SOURCE_CHARS = 15_000


# =============================================================================
# MÔ TẢ NGHIỆP VỤ CHI TIẾT CHO CÁC TESTCASE HIỆN CÓ
# =============================================================================

@dataclasses.dataclass(frozen=True)
class Guide:
    title: str
    scenario: str
    example: str
    expected: str
    business_meaning: str
    failure_impact: str


def G(
    title: str,
    scenario: str,
    example: str,
    expected: str,
    business_meaning: str,
    failure_impact: str,
) -> Guide:
    return Guide(
        title=title,
        scenario=scenario,
        example=example,
        expected=expected,
        business_meaning=business_meaning,
        failure_impact=failure_impact,
    )


KNOWN_GUIDES: dict[str, Guide] = {
    # -------------------------------------------------------------------------
    # API và khả năng hệ thống
    # -------------------------------------------------------------------------
    "test_health_reports_comparison_and_ocr": G(
        "Kiểm tra máy chủ công bố đúng các chức năng đang hoạt động",
        "Gọi địa chỉ kiểm tra sức khỏe của hệ thống trước khi người dùng tải hồ sơ.",
        "Trình duyệt hoặc frontend gọi GET /api/health. Phản hồi phải cho biết hệ thống có chế độ so sánh hồ sơ và OCR.",
        "API trả trạng thái hoạt động bình thường và các cờ comparison/package/OCR đúng với chức năng thật.",
        "Frontend biết nút nào được phép hiển thị và quản trị viên biết dịch vụ đã sẵn sàng.",
        "Giao diện có thể ẩn nhầm chức năng, báo hệ thống hỏng hoặc cho người dùng gọi chức năng chưa sẵn sàng.",
    ),
    "test_ocr_route_is_available": G(
        "Kiểm tra đường dẫn OCR tồn tại",
        "Người dùng chọn PDF scan hoặc ảnh rồi bấm nút OCR.",
        "Frontend gửi yêu cầu tới POST /api/ocr. Test bảo đảm đường dẫn này được FastAPI đăng ký, không trả lỗi 404 do thiếu route.",
        "Máy chủ nhận được yêu cầu OCR và trả phản hồi hợp lệ theo quy trình của hệ thống.",
        "Người dùng có thể gửi tài liệu scan để chuyển thành Excel.",
        "Nút OCR trên giao diện sẽ không hoạt động dù các thư viện OCR đã được cài.",
    ),
    "test_compare_package_api_accepts_one_bidder": G(
        "Kiểm tra gói thầu chấp nhận chỉ một nhà thầu",
        "Có PL01 hoặc PL02 và chỉ có một file chào giá của một nhà thầu.",
        "Ví dụ tải PL01.xlsx cùng NhaThauA.xlsx. Hệ thống phải nhận hồ sơ và tạo job xử lý thay vì bắt buộc từ hai nhà thầu trở lên.",
        "API chấp nhận yêu cầu, tạo mã tác vụ và không báo lỗi thiếu nhà thầu.",
        "Phù hợp trường hợp thực tế chỉ có một đơn vị nộp báo giá.",
        "Người dùng sẽ không thể kiểm tra hồ sơ một nhà thầu, dù đây là chức năng đã được yêu cầu.",
    ),

    # -------------------------------------------------------------------------
    # So sánh Excel
    # -------------------------------------------------------------------------
    "test_missing_and_zero_are_not_silently_ok": G(
        "Không được coi hạng mục thiếu hoặc số lượng 0 là bình thường",
        "PL01 yêu cầu một hạng mục nhưng nhà thầu bỏ hẳn hoặc để khối lượng bằng 0.",
        "Ví dụ PL01 yêu cầu 10 máy bơm; hồ sơ nhà thầu không có dòng máy bơm hoặc ghi số lượng 0.",
        "Hệ thống phải tạo cảnh báo thiếu hạng mục/khối lượng bất thường, không được đánh dấu OK.",
        "Người kiểm tra không bỏ sót việc nhà thầu chưa chào đủ khối lượng.",
        "Hồ sơ thiếu hàng hóa có thể bị kết luận hợp lệ sai, ảnh hưởng đánh giá thầu.",
    ),
    "test_multi_bidder_consensus_flags_outlier": G(
        "Phát hiện đơn giá lệch bất thường giữa nhiều nhà thầu",
        "Nhiều nhà thầu cùng báo giá một hạng mục nhưng có một giá cách xa nhóm còn lại.",
        "Ví dụ bốn giá là 100, 105, 95 và 200. Ba giá đầu gần nhau, giá 200 là điểm lệch.",
        "Hệ thống phải cảnh báo nhà thầu có giá 200 là cao bất thường so với mặt bằng ngang hàng.",
        "Người dùng nhanh chóng thấy giá cần kiểm tra lại mà không phải dò thủ công từng cột.",
        "Đơn giá nhập nhầm hoặc bất thường có thể lọt qua báo cáo.",
    ),
    "test_same_code_different_name_is_flagged": G(
        "Cùng mã nhưng tên vật tư khác phải được cảnh báo",
        "Hai dòng dùng cùng một mã hiệu nhưng mô tả hàng hóa không giống nhau.",
        "Ví dụ cùng mã M-01 nhưng PL01 ghi “Tủ điện tổng”, còn nhà thầu ghi “Ống HDPE D110”.",
        "Hệ thống không được ghép im lặng; phải gắn cờ xung đột mã và tên.",
        "Tránh so sánh nhầm hai loại vật tư chỉ vì trùng mã.",
        "Giá và khối lượng của hai hạng mục khác nhau có thể bị ghép chung, làm sai toàn bộ kết quả.",
    ),
    "test_duplicate_code_is_preserved_and_flagged": G(
        "Giữ lại đầy đủ các dòng trùng mã và đồng thời cảnh báo",
        "Trong một file có hai dòng cùng mã vật tư.",
        "Ví dụ mã M-01 xuất hiện ở dòng 10 và dòng 25. Cả hai dòng đều phải còn trong dữ liệu sau khi đọc.",
        "Không được tự xóa một dòng; hệ thống phải giữ cả hai và tạo cờ mã trùng để người dùng xem xét.",
        "Báo cáo không làm mất dữ liệu gốc và vẫn chỉ ra điểm nghi vấn.",
        "Một hạng mục có thể biến mất khỏi báo cáo hoặc bị cộng sai số lượng.",
    ),

    # -------------------------------------------------------------------------
    # Đọc Excel nhanh
    # -------------------------------------------------------------------------
    "test_calamine_reader_preserves_rows": G(
        "Calamine phải đọc đủ dòng và đúng thứ tự",
        "File Excel được đọc bằng bộ máy nhanh Calamine.",
        "Ví dụ file có tiêu đề, ba dòng vật tư và một dòng tổng; sau khi đọc không được mất hoặc đảo thứ tự các dòng.",
        "Số dòng, nội dung và vị trí tương đối phải giống dữ liệu trong file.",
        "Tăng tốc đọc file nhưng không đánh đổi độ chính xác.",
        "Hạng mục có thể bị bỏ sót hoặc đối chiếu sai dòng nguồn.",
    ),
    "test_parallel_workbook_load": G(
        "Đọc nhiều workbook song song vẫn phải trả đủ kết quả",
        "Bốn nhà thầu cùng tải file lên một thời điểm.",
        "Ví dụ NT1.xlsx, NT2.xlsx, NT3.xlsx và NT4.xlsx được đưa vào ThreadPoolExecutor.",
        "Kết quả phải chứa đủ bốn file, không lẫn dữ liệu và không mất file nào.",
        "Nhiều người hoặc nhiều nhà thầu có thể được xử lý nhanh hơn.",
        "Có thể xảy ra thiếu kết quả, lẫn tên nhà thầu hoặc lỗi ngẫu nhiên khi tải đồng thời.",
    ),
    "test_ref_is_scanned_and_annotated": G(
        "Phát hiện công thức Excel lỗi #REF! và đánh dấu đúng vị trí",
        "Workbook có ô công thức tham chiếu tới vùng đã bị xóa.",
        "Ví dụ ô G25 hiển thị #REF! hoặc công thức chứa #REF!.",
        "Bộ quét phải tìm thấy ô lỗi và file kết quả phải có ghi chú/đánh dấu để người dùng nhìn thấy.",
        "Người dùng biết chính xác ô công thức hỏng thay vì chỉ nhận một cảnh báo chung.",
        "Tổng tiền hoặc khối lượng có thể sai mà không ai biết nguyên nhân.",
    ),

    # -------------------------------------------------------------------------
    # OCR
    # -------------------------------------------------------------------------
    "test_detect_simple_wired_table": G(
        "Nhận diện được bảng có đường kẻ trong ảnh",
        "Ảnh scan chứa một bảng đơn giản có các đường ngang và dọc.",
        "Ví dụ bảng 3 cột × 4 dòng với khung ô rõ ràng.",
        "Thuật toán phải tìm được vùng bảng và các ô cơ bản.",
        "OCR biết chia ảnh thành hàng/cột trước khi đọc chữ và số.",
        "Nội dung có thể bị dồn vào một cột hoặc sai cấu trúc Excel.",
    ),
    "test_dense_19_column_grid_and_schema": G(
        "Nhận diện bảng BOQ dày có 19 cột",
        "Tài liệu dự toán có rất nhiều cột hẹp, tiêu đề nhiều tầng và số liệu sát nhau.",
        "Ví dụ một trang có 19 cột gồm STT, mã hiệu, mô tả, đơn vị, khối lượng, vật liệu, nhân công, máy và các thành phần giá.",
        "Hệ thống phải dựng được lưới 19 cột và ánh xạ đúng cấu trúc dữ liệu mong đợi.",
        "File OCR giữ được bố cục gần với biểu mẫu dự toán thực tế.",
        "Số liệu có thể bị chuyển nhầm cột, đặc biệt là khối lượng và đơn giá.",
    ),
    "test_parser_keeps_multiple_tables": G(
        "Một trang có nhiều bảng thì phải giữ lại tất cả",
        "Trang scan chứa hai hoặc nhiều bảng độc lập.",
        "Ví dụ phía trên là bảng vật tư, phía dưới là bảng tổng hợp chi phí.",
        "Parser phải trả về nhiều bảng, không chỉ lấy bảng đầu tiên.",
        "Người dùng không bị mất phần dữ liệu nằm ở bảng thứ hai.",
        "Báo cáo OCR thiếu nội dung dù ảnh gốc vẫn có dữ liệu.",
    ),
    "test_zero_values_are_not_replaced_by_fallback": G(
        "Số 0 hợp lệ không được thay bằng giá trị dự phòng",
        "OCR đọc được một ô có giá trị 0 thật.",
        "Ví dụ chi phí máy thi công bằng 0; fallback khác đang có giá trị 100.",
        "Kết quả cuối cùng vẫn phải là 0, vì 0 khác với ô không đọc được.",
        "Không tự tạo chi phí giả trong bảng kết quả.",
        "Tổng tiền có thể bị tăng sai chỉ vì hệ thống hiểu 0 là thiếu dữ liệu.",
    ),
    "test_semantic_score_prefers_valid_vietnamese_table_header": G(
        "Ưu tiên hướng ảnh có tiêu đề tiếng Việt hợp lý",
        "Một trang được thử ở nhiều góc xoay 0°, 90°, 180° và 270°.",
        "Ở góc đúng có các từ như “STT”, “Mô tả công việc”, “Đơn vị”, “Khối lượng”; góc sai tạo chuỗi vô nghĩa.",
        "Điểm ngữ nghĩa của góc đúng phải cao hơn.",
        "Hệ thống chọn đúng chiều đọc dựa trên nội dung chứ không chỉ dựa vào hình học.",
        "OCR có thể đọc trang bị lộn ngược và tạo Excel vô nghĩa.",
    ),
    "test_orientation_selection_uses_semantic_probe": G(
        "Bộ chọn hướng phải thực sự dùng kết quả kiểm tra ngữ nghĩa",
        "Các góc xoay có chất lượng hình ảnh gần giống nhau nhưng chỉ một góc tạo ra chữ đúng.",
        "Ví dụ góc 90° nhận được tiêu đề chuẩn, góc 0° chỉ có ký tự rời rạc.",
        "Hàm chọn hướng phải chọn góc có nội dung hợp lý.",
        "Tăng độ chính xác OCR cho file scan bị xoay.",
        "Trang vẫn có thể bị chọn sai dù đã có bước dò hướng.",
    ),
    "test_dense_boq_header_rows_do_not_stop_at_second_thin_row": G(
        "Không kết thúc tiêu đề bảng quá sớm",
        "BOQ có tiêu đề nhiều tầng và một vài dòng tiêu đề rất ít chữ.",
        "Ví dụ dòng 1 là nhóm cột, dòng 2 chỉ có vài ô, dòng 3 mới chứa tên cột chi tiết.",
        "Parser phải tiếp tục đọc đủ phần tiêu đề thay vì dừng ở dòng mỏng thứ hai.",
        "Tên cột được xác định đúng trong biểu mẫu phức tạp.",
        "Dữ liệu có thể bị xem nhầm là tiêu đề hoặc tên cột bị thiếu.",
    ),

    # -------------------------------------------------------------------------
    # Matching và số
    # -------------------------------------------------------------------------
    "test_hybrid_match_is_one_to_one": G(
        "Mỗi hạng mục chỉ được ghép với một hạng mục tương ứng",
        "Có hai dòng chuẩn và hai dòng nhà thầu có tên/mã gần giống.",
        "Ví dụ “Tủ điện tổng” và “Cáp XLPE” phải lần lượt ghép với đúng một dòng; không được dùng cùng một dòng nhà thầu cho cả hai.",
        "Mỗi chỉ số dòng chuẩn và dòng ứng viên chỉ xuất hiện trong một cặp ghép.",
        "Tránh đếm lặp hoặc so sánh một báo giá cho nhiều hạng mục.",
        "Khối lượng và giá có thể bị nhân đôi hoặc một dòng khác bị coi là thiếu.",
    ),
    "test_parse_vietnamese_and_international_numbers": G(
        "Đọc đúng nhiều kiểu viết số",
        "Excel/PDF có thể dùng dấu chấm, dấu phẩy hoặc khoảng trắng làm dấu phân cách.",
        "Ví dụ “1.234.567,89” phải thành 1234567.89; “1,234,567.89” cũng phải cho cùng giá trị.",
        "Bộ đọc số xác định đúng phần nghìn, phần thập phân và dấu âm.",
        "Giá và khối lượng từ nhiều nguồn vẫn so sánh được.",
        "Một dấu phân cách bị hiểu sai có thể làm giá tăng hoặc giảm hàng nghìn lần.",
    ),

    # -------------------------------------------------------------------------
    # Phụ lục và chế độ gói thầu
    # -------------------------------------------------------------------------
    "test_pl1_only_is_supported": G(
        "Chỉ có PL01 vẫn xử lý được",
        "Người dùng có PL01 nhưng không có PL02.",
        "Ví dụ tải PL01 cùng file nhà thầu; ô PL02 để trống.",
        "Pipeline vẫn chạy, dùng PL01 làm căn cứ cho mã, tên, đơn vị và khối lượng.",
        "Không bắt người dùng phải có đủ cả hai phụ lục trong mọi trường hợp.",
        "Công việc bị chặn dù dữ liệu cần thiết đã có trong PL01.",
    ),
    "test_pl2_only_uses_multiway_peer_consensus": G(
        "Chỉ có PL02 vẫn hỗ trợ so sánh nhiều nhà thầu theo mặt bằng chung",
        "Không có PL01 nhưng có PL02 và nhiều file nhà thầu.",
        "Ví dụ ba nhà thầu báo 100, 103 và 190 cho cùng hạng mục.",
        "Hệ thống dùng đối chiếu đa chiều để nhận ra giá 190 lệch khỏi nhóm, không chọn tùy ý một nhà thầu làm chuẩn.",
        "So sánh công bằng giữa các nhà thầu.",
        "Kết quả có thể thiên lệch nếu lấy một nhà thầu làm mốc tuyệt đối.",
    ),
    "test_single_bidder_pl1_compares_appendix_without_peer_price": G(
        "Một nhà thầu chỉ đối chiếu yêu cầu, không phán xét giá ngang hàng",
        "Có PL01 và duy nhất một hồ sơ nhà thầu.",
        "Ví dụ PL01 không có đơn giá chuẩn; nhà thầu báo 1.000.000 đồng.",
        "Hệ thống kiểm tra tên, mã, đơn vị, số lượng và yêu cầu kỹ thuật nhưng không nói giá cao/thấp do không có nhà thầu khác để so.",
        "Tránh đưa ra kết luận giá thiếu căn cứ.",
        "Một giá hợp lệ có thể bị gắn cảnh báo sai chỉ vì đem so với dữ liệu không phải giá tham chiếu.",
    ),
    "test_package_multi_bidder_peer_stage_is_price_only": G(
        "Giai đoạn so sánh ngang hàng chỉ xét giá",
        "Sau khi từng hồ sơ đã được đối chiếu với PL01/PL02, hệ thống so các nhà thầu với nhau.",
        "Ví dụ tên sheet khác nhau nhưng cùng hạng mục; giai đoạn ngang hàng chỉ so đơn giá của hạng mục đã ghép.",
        "Không tạo lại cảnh báo tên, đơn vị hoặc số lượng ở bước ngang hàng; chỉ tạo cảnh báo giá giữa các nhà thầu.",
        "Báo cáo rõ nguồn cảnh báo và không lặp lỗi.",
        "Người dùng có thể nhận nhiều cảnh báo trùng nhau và khó biết lỗi nằm ở phụ lục hay ở giá.",
    ),
    "test_package_mode_uses_pl1_pl2_and_no_bidder_baseline": G(
        "Chế độ gói thầu dùng phụ lục làm căn cứ, không lấy nhà thầu đầu tiên làm chuẩn",
        "Có PL01, PL02 và nhiều hồ sơ nhà thầu.",
        "Ví dụ nhà thầu A và B đều được đối chiếu độc lập với phụ lục; A không được dùng làm chuẩn để chấm B.",
        "Cấu trúc và khối lượng lấy từ phụ lục, còn giá nhiều nhà thầu được so ngang hàng.",
        "Đảm bảo tính trung lập khi đánh giá.",
        "Nhà thầu được tải đầu tiên có thể vô tình chi phối toàn bộ kết quả.",
    ),

    # -------------------------------------------------------------------------
    # Regression
    # -------------------------------------------------------------------------
    "test_column_number_legend_does_not_hide_normal_priced_row": G(
        "Dòng chú giải số cột không được làm mất dòng giá bình thường",
        "Một sheet có hàng chú giải đánh số cột 1, 2, 3… gần vùng dữ liệu.",
        "Ví dụ dòng chú giải nằm phía trên một hạng mục có đơn giá hợp lệ.",
        "Parser phải bỏ qua chú giải nhưng vẫn giữ dòng hạng mục phía dưới.",
        "Sửa lỗi cũ từng khiến dữ liệu thật bị ẩn nhầm.",
        "Một hạng mục hợp lệ có thể biến mất khỏi báo cáo.",
    ),
    "test_component_without_price_is_not_false_quality_error": G(
        "Dòng thành phần không có giá không được báo lỗi chất lượng giả",
        "Một dòng chỉ là tiêu đề nhóm hoặc thành phần mô tả, không yêu cầu đơn giá.",
        "Ví dụ dòng “A. Hệ thống điện” không có giá vì không phải vật tư chi tiết.",
        "Hệ thống nhận diện đúng loại dòng và không cảnh báo thiếu giá.",
        "Báo cáo tập trung vào lỗi thật thay vì làm người dùng mất thời gian.",
        "Báo cáo có quá nhiều cảnh báo giả, làm giảm độ tin cậy.",
    ),

    # -------------------------------------------------------------------------
    # S1 Comparison Engine
    # -------------------------------------------------------------------------
    "test_s1_ce01_equal_quantity_has_no_warning": G(
        "Khối lượng bằng nhau thì không cảnh báo",
        "Phụ lục và nhà thầu ghi cùng một số lượng.",
        "Ví dụ PL01 = 100 mét cáp, nhà thầu = 100 mét cáp.",
        "Độ chênh bằng 0% và trạng thái không phải WARNING/CRITICAL.",
        "Người dùng không bị làm phiền bởi dữ liệu hoàn toàn khớp.",
        "Hệ thống có thể tạo cảnh báo giả cho hồ sơ đúng.",
    ),
    "test_s1_ce02_quantity_difference_8_percent_is_warning": G(
        "Chênh khối lượng 8% phải tạo cảnh báo",
        "Nhà thầu ghi số lượng lệch vừa phải so với phụ lục.",
        "Ví dụ PL01 = 100, nhà thầu = 108; chênh 8%.",
        "Hệ thống gắn mức WARNING theo ngưỡng đang cấu hình.",
        "Người kiểm tra biết có sai khác cần xem lại nhưng chưa phải mức nghiêm trọng nhất.",
        "Sai số vừa phải có thể bị bỏ qua.",
    ),
    "test_s1_ce03_quantity_difference_35_percent_is_critical": G(
        "Chênh khối lượng 35% phải là nghiêm trọng",
        "Số lượng nhà thầu khác rất xa yêu cầu.",
        "Ví dụ PL01 = 100, nhà thầu = 135; chênh 35%.",
        "Hệ thống gắn CRITICAL hoặc mức nghiêm trọng tương đương.",
        "Lỗi lớn được đưa lên ưu tiên xử lý.",
        "Sai khối lượng lớn có thể bị xem như cảnh báo nhẹ.",
    ),
    "test_s1_ce04_unit_mismatch_is_flagged": G(
        "Khác đơn vị phải được cảnh báo",
        "Tên hạng mục giống nhau nhưng đơn vị không tương thích.",
        "Ví dụ phụ lục dùng “m”, nhà thầu dùng “100m” hoặc “bộ”.",
        "Hệ thống gắn cờ UNIT_MISMATCH và không coi số lượng là so sánh trực tiếp.",
        "Tránh kết luận sai khi 5 đơn vị “100m” thực chất bằng 500m.",
        "Khối lượng có thể bị hiểu sai 100 lần.",
    ),
    "test_s1_ce05_missing_item_is_critical": G(
        "Hạng mục bị thiếu phải là lỗi nghiêm trọng",
        "Phụ lục có yêu cầu nhưng hồ sơ nhà thầu không có dòng tương ứng.",
        "Ví dụ PL01 có máy bơm P-01 nhưng file nhà thầu không tìm thấy P-01 hoặc tên tương đương.",
        "Kết quả phải có trạng thái MISSING và mức CRITICAL.",
        "Người dùng thấy ngay nhà thầu chưa chào đủ phạm vi.",
        "Hồ sơ thiếu hàng hóa có thể được đánh giá nhầm là đầy đủ.",
    ),
    "test_s1_ce06_extra_item_is_warning": G(
        "Hạng mục phát sinh phải được thông báo",
        "Nhà thầu thêm một dòng không có trong phụ lục.",
        "Ví dụ thêm “Chi phí vận chuyển” hoặc một thiết bị ngoài danh mục.",
        "Kết quả ghi EXTRA_ITEM ở mức cảnh báo để người dùng xem xét.",
        "Phát hiện chi phí hoặc phạm vi bổ sung.",
        "Khoản phát sinh có thể bị bỏ qua trong tổng giá.",
    ),
    "test_s1_ce07_different_sheet_is_note_not_warning": G(
        "Khác sheet chỉ là ghi chú khi nội dung vẫn khớp",
        "Hai file đặt cùng hạng mục ở các sheet có tên khác nhau.",
        "Ví dụ PL01 đặt “Tủ điện LV-G.1” ở sheet “Hạ thế”, nhà thầu đặt ở sheet “HT điện”. Tên, đơn vị và số lượng vẫn giống.",
        "Hệ thống ghép thành công và chỉ ghi “khác sheet”, không tăng mức cảnh báo.",
        "Cho phép nhà thầu tổ chức workbook khác mà không bị chấm lỗi oan.",
        "Báo cáo có thể cảnh báo hàng loạt chỉ vì cách chia sheet khác nhau.",
    ),
    "test_s1_ce08_single_bidder_does_not_compare_price_against_pl01": G(
        "Không so giá một nhà thầu với PL01 khi PL01 không phải bảng giá tham chiếu",
        "Chỉ có một nhà thầu và phụ lục yêu cầu.",
        "Ví dụ nhà thầu báo 2 triệu; PL01 chỉ có khối lượng và mô tả.",
        "Không sinh PRICE_HIGH/PRICE_LOW ở giai đoạn đối chiếu phụ lục.",
        "Kết luận giá phải dựa trên dữ liệu hợp lý.",
        "Nhà thầu có thể bị báo giá bất thường sai căn cứ.",
    ),
    "test_s1_ce09_price_outlier_is_flagged_only_in_peer_stage": G(
        "Giá lệch chỉ được cảnh báo khi so giữa nhiều nhà thầu",
        "Có ít nhất ba giá cho cùng một hạng mục.",
        "Ví dụ NT1 = 100, NT2 = 105, NT3 = 200.",
        "Giai đoạn peer comparison gắn cờ cho 200; giai đoạn PL01 không tạo cờ giá này.",
        "Tách rõ đối chiếu yêu cầu và phân tích giá thị trường nội bộ.",
        "Cảnh báo giá có thể xuất hiện sai bước hoặc bị tính lặp.",
    ),
    "test_s1_ce10_formula_error_is_critical": G(
        "Lỗi công thức #REF! phải là nghiêm trọng",
        "Một ô công thức trong workbook bị hỏng tham chiếu.",
        "Ví dụ thành tiền là =D5*#REF! hoặc ô hiển thị #REF!.",
        "Hệ thống tạo FORMULA_ERROR ở mức CRITICAL và chỉ rõ sheet/dòng/ô.",
        "Người dùng biết số tiền có thể không đáng tin.",
        "Báo cáo tài chính có thể dùng số liệu sai do công thức lỗi.",
    ),
    "test_s1_ce11_configurable_quantity_threshold_is_used": G(
        "Ngưỡng cảnh báo cấu hình phải được áp dụng thật",
        "Quản trị viên đổi ngưỡng chênh khối lượng.",
        "Ví dụ giảm ngưỡng cảnh báo từ 5% xuống 3%; dữ liệu lệch 4% giờ phải cảnh báo.",
        "Kết quả thay đổi theo cấu hình mới, không dùng giá trị viết cứng trong code.",
        "Mỗi dự án có thể đặt tiêu chuẩn kiểm tra riêng.",
        "Giao diện cho phép đổi ngưỡng nhưng kết quả không thay đổi.",
    ),

    # -------------------------------------------------------------------------
    # S1 File Parser
    # -------------------------------------------------------------------------
    "test_s1_fi01_parse_valid_xlsx_and_preserve_source_row": G(
        "Đọc file XLSX hợp lệ và giữ đúng số dòng nguồn",
        "Workbook có một hạng mục ở một dòng xác định.",
        "Ví dụ “Máy bơm” nằm ở dòng Excel 12.",
        "Sau khi parse, ItemRecord vẫn ghi row_number = 12 và đúng tên sheet.",
        "Khi cảnh báo, người dùng mở đúng dòng trong file gốc.",
        "Báo cáo chỉ sai vị trí, khiến người dùng khó kiểm tra.",
    ),
    "test_s1_fi02_detect_multi_level_header": G(
        "Tự tìm tiêu đề nhiều tầng",
        "File có vài dòng tên công trình và nhóm cột trước dòng tiêu đề thật.",
        "Ví dụ dòng 5 có STT/Mô tả, dòng 6 có Đơn vị/Khối lượng/Đơn giá.",
        "Parser xác định đúng vùng tiêu đề và cột dữ liệu.",
        "Không phụ thuộc cứng vào việc header luôn nằm ở dòng 1.",
        "Toàn bộ cột có thể bị đọc sai khi nhà thầu dùng mẫu khác.",
    ),
    "test_s1_fi03_calamine_matrix_preserves_raw_rows": G(
        "Ma trận Calamine giữ nguyên dữ liệu thô",
        "Đọc sheet trước khi chuyển thành hạng mục chuẩn hóa.",
        "Ví dụ các ô trống, số 0 và chuỗi mô tả phải còn đúng vị trí.",
        "Số hàng/cột và giá trị ô quan trọng không bị thay đổi.",
        "Bảo đảm bước đọc nhanh không làm biến dạng dữ liệu.",
        "Lỗi phát sinh ngay từ bước đầu và lan sang toàn bộ phép so sánh.",
    ),
    "test_s1_fi04_formula_ref_is_detected": G(
        "Bộ đọc file phát hiện #REF!",
        "Trong file có công thức lỗi.",
        "Ví dụ ô F20 chứa =SUM(#REF!).",
        "Danh sách lỗi phải chứa vị trí ô và loại lỗi tham chiếu.",
        "Cảnh báo được tạo trước khi dùng số liệu để so sánh.",
        "Số tổng sai có thể được sử dụng như dữ liệu hợp lệ.",
    ),
    "test_s1_fi05_four_workbooks_are_loaded_in_parallel": G(
        "Bốn file được đọc song song và đủ kết quả",
        "Hệ thống nhận nhiều hồ sơ cùng lúc.",
        "Ví dụ bốn file nhỏ được giao cho bốn tác vụ đọc.",
        "Kết quả có đủ bốn workbook và nội dung giống cách đọc tuần tự.",
        "Tăng tốc mà vẫn an toàn dữ liệu.",
        "Có thể xảy ra race condition, thiếu file hoặc lẫn kết quả.",
    ),
    "test_s1_fi06_invalid_extension_is_rejected": G(
        "Từ chối định dạng không được hỗ trợ",
        "Người dùng đổi tên hoặc tải file không phải Excel.",
        "Ví dụ tải file .txt, .exe hoặc .pdf vào chức năng chỉ nhận workbook.",
        "Hệ thống dừng sớm và trả thông báo định dạng hợp lệ, không cố parse.",
        "Người dùng nhận lỗi rõ ràng và hệ thống tránh xử lý dữ liệu nguy hiểm.",
        "Có thể crash, treo job hoặc tạo báo cáo rỗng khó hiểu.",
    ),
    "test_s1_fi07_corrupt_xlsx_returns_clear_error": G(
        "File XLSX hỏng phải trả lỗi dễ hiểu",
        "Đuôi file là .xlsx nhưng nội dung ZIP bên trong bị hỏng.",
        "Ví dụ file bị cắt khi tải lên hoặc chỉ chứa vài byte.",
        "Hệ thống báo rõ file không đọc được và nêu tên file, không nuốt lỗi.",
        "Người dùng biết cần tải lại file nào.",
        "Job chỉ báo “failed” chung chung hoặc treo không kết thúc.",
    ),
    "test_s1_fi08_duplicate_code_rows_are_preserved_and_flagged": G(
        "Dòng trùng mã không bị xóa trong bước parse",
        "Một mã xuất hiện nhiều lần trong cùng sheet.",
        "Ví dụ hai dòng M-01 có mô tả hoặc khối lượng khác nhau.",
        "Parser giữ cả hai, sau đó auditor gắn cờ trùng mã.",
        "Vừa bảo toàn hồ sơ gốc vừa hỗ trợ phát hiện sai sót.",
        "Một dòng có thể bị ghi đè và biến mất.",
    ),
    "test_s1_fi09_component_without_price_is_not_false_error": G(
        "Dòng nhóm không có giá không bị báo lỗi giả",
        "Một dòng là tiêu đề hoặc cấu phần không yêu cầu đơn giá.",
        "Ví dụ “I. PHẦN ĐIỆN” chỉ dùng để phân nhóm.",
        "Parser phân loại đúng row_type và không tạo lỗi thiếu giá.",
        "Giảm cảnh báo rác trong báo cáo.",
        "Người dùng phải xem hàng trăm cảnh báo không có ý nghĩa.",
    ),

    # -------------------------------------------------------------------------
    # Security và sheet
    # -------------------------------------------------------------------------
    "test_network_guard_blocks_external": G(
        "Chế độ riêng tư phải chặn kết nối Internet",
        "Hệ thống chạy local-only và một đoạn code cố truy cập máy chủ bên ngoài.",
        "Ví dụ OCR hoặc thư viện cố gọi một URL Internet để tải model/dữ liệu.",
        "Network guard chặn yêu cầu bên ngoài nhưng vẫn cho phép xử lý nội bộ cần thiết.",
        "Hồ sơ dự thầu không bị gửi ra ngoài ngoài ý muốn.",
        "Dữ liệu nhạy cảm có nguy cơ rò rỉ hoặc hệ thống phụ thuộc Internet.",
    ),
    "test_different_sheet_is_note_not_warning_when_name_and_quantity_match": G(
        "Khác sheet nhưng cùng hạng mục chỉ tạo ghi chú",
        "Tên hạng mục, đơn vị và khối lượng khớp; chỉ tên sheet khác.",
        "Ví dụ PL01 ở “2 - PHẦN TỦ HẠ THẾ”, nhà thầu ở “1. HT điện”, cùng tủ LV-G.1 và cùng số lượng.",
        "Kết quả ghép đúng, severity vẫn OK/NOTE và có mô tả “khác sheet”.",
        "Cho phép cấu trúc file linh hoạt mà vẫn phát hiện đúng hạng mục.",
        "Nhà thầu bị cảnh báo oan chỉ vì sắp xếp workbook khác.",
    ),
    "test_price_difference_between_bidders_still_warns_after_cross_sheet_match": G(
        "Sau khi ghép khác sheet, chênh giá thật vẫn phải cảnh báo",
        "Hai nhà thầu đặt cùng hạng mục ở sheet khác nhau và báo giá lệch nhau.",
        "Ví dụ NT1 báo 100, NT2 báo 180; tên, đơn vị và số lượng đều khớp.",
        "Hệ thống không cảnh báo vì khác sheet, nhưng vẫn cảnh báo giá 180 lệch khỏi giá ngang hàng.",
        "Không để ghi chú “khác sheet” che mất bất thường giá.",
        "Một chênh lệch giá quan trọng có thể bị bỏ qua sau khi ghép chéo sheet.",
    ),

    # -------------------------------------------------------------------------
    # S1 Normalizer
    # -------------------------------------------------------------------------
    "test_s1_nr01_parse_vietnamese_and_international_numbers": G(
        "Chuẩn hóa số Việt Nam và quốc tế",
        "Cùng một giá trị có thể được viết theo nhiều quy ước.",
        "Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.",
        "Tất cả phải được chuyển thành số thực đúng để có thể tính toán.",
        "Tránh sai giá trị khi nhận file từ nhiều nhà thầu.",
        "Một đơn giá có thể bị hiểu sai hàng nghìn lần.",
    ),
    "test_s1_nr02_normalize_square_metre_variants": G(
        "Chuẩn hóa mọi cách viết mét vuông",
        "Đơn vị diện tích có nhiều kiểu ký hiệu.",
        "Ví dụ m2, M2, m², m^2, “mét vuông”.",
        "Tất cả phải trở thành một giá trị chuẩn là m².",
        "Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.",
        "Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.",
    ),
    "test_s1_nr03_normalize_cubic_metre_variants": G(
        "Chuẩn hóa mọi cách viết mét khối",
        "Đơn vị thể tích có nhiều kiểu ký hiệu.",
        "Ví dụ m3, M3, m³, m^3, “mét khối”.",
        "Tất cả phải trở thành m³.",
        "Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.",
        "Có thể phát sinh cảnh báo đơn vị giả.",
    ),
    "test_s1_nr04_normalize_common_units": G(
        "Chuẩn hóa các đơn vị phổ biến",
        "Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.",
        "Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.",
        "Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.",
        "Tăng khả năng ghép đúng hạng mục.",
        "Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.",
    ),
    "test_s1_nr05_normalize_item_codes": G(
        "Chuẩn hóa mã vật tư",
        "Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.",
        "Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.",
        "Mã tương đương có cùng dạng chuẩn.",
        "So khớp mã ổn định giữa các biểu mẫu.",
        "Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.",
    ),
    "test_s1_nr06_normalize_stt": G(
        "Chuẩn hóa số thứ tự",
        "STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.",
        "Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.",
        "STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.",
        "Giảm ghép nhầm dựa trên số thứ tự giả.",
        "Công thức Excel có thể bị hiểu nhầm là mã hạng mục.",
    ),
    "test_s1_nr07_normalize_vietnamese_names_and_symbols": G(
        "Chuẩn hóa tên có dấu và ký hiệu kỹ thuật",
        "Tên vật tư có thể viết có dấu/không dấu và dùng ký hiệu ×, ².",
        "Ví dụ “Cáp điện 3×2.5 mm²” phải cùng khóa với “cap dien 3x2 5 mm2”.",
        "Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau.",
        "Tên kỹ thuật vẫn ghép được dù định dạng khác.",
        "Ký tự mũ hoặc dấu nhân bị mất có thể làm ghép sai vật tư.",
    ),
    "test_s1_nr08_safe_amount_respects_explicit_zero": G(
        "Giữ nguyên thành tiền 0 khi 0 là dữ liệu thật",
        "Ô thành tiền có thể là 0 hoặc để trống.",
        "Ví dụ quantity=2, price=100, amount=0 phải giữ 0; amount trống mới tính thành 200.",
        "Không thay số 0 bằng phép nhân dự phòng.",
        "Tôn trọng dữ liệu gốc và phân biệt 0 với thiếu dữ liệu.",
        "Tổng tiền có thể bị tự động tăng sai.",
    ),
    "test_s1_nr09_percent_delta": G(
        "Tính đúng phần trăm chênh lệch",
        "So sánh giá trị nhà thầu với giá trị chuẩn.",
        "Ví dụ từ 100 lên 108 là +8%; từ 100 xuống 95 là -5%.",
        "Hàm trả đúng dấu và đúng tỷ lệ.",
        "Mức cảnh báo dựa trên con số chính xác.",
        "Hệ thống có thể phân loại sai WARNING/CRITICAL.",
    ),
    "test_s1_nr10_hybrid_match_is_one_to_one": G(
        "Ghép hạng mục một-một",
        "Nhiều dòng có tên gần nhau.",
        "Ví dụ hai dòng chuẩn và hai dòng nhà thầu phải tạo đúng hai cặp, không dùng một dòng hai lần.",
        "Mỗi dòng chỉ xuất hiện trong tối đa một cặp ghép.",
        "Không đếm lặp dữ liệu.",
        "Một giá hoặc khối lượng có thể bị gán cho nhiều hạng mục.",
    ),
    "test_s1_nr11_exact_name_can_match_across_different_sheets": G(
        "Tên chính xác vẫn ghép được khi khác sheet",
        "Hai workbook đặt cùng vật tư ở hai sheet khác tên.",
        "Ví dụ tủ LV-G.1…LV-G.6 nằm ở “PHẦN TỦ HẠ THẾ” và “HT điện”.",
        "Matcher tạo EXACT_NAME với điểm cao và ghi chú khác sheet.",
        "Cấu trúc workbook không cản trở đối chiếu.",
        "Hạng mục đúng có thể bị báo thiếu.",
    ),
    "test_s1_nr12_different_names_are_not_forced_into_exact_name_match": G(
        "Không ép hai tên khác nhau thành khớp chính xác",
        "Hai dòng không có mã và tên hoàn toàn khác.",
        "Ví dụ “Tủ điện phân phối tổng” và “Ống nước HDPE D110”.",
        "Không được tạo cặp EXACT_NAME giữa hai dòng này.",
        "Ngăn ghép nhầm vật tư.",
        "Giá và khối lượng của hai loại thiết bị khác nhau có thể bị so sánh với nhau.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases - thông báo lỗi thân thiện cho người dùng
    # -------------------------------------------------------------------------
    "test_format_job_error_message_non_xlsx_extension": G(
        "Báo lỗi dễ hiểu khi file thực ra là .xls/.xlsb đổi tên",
        "Người dùng đổi đuôi file Excel cũ (.xls/.xlsb) thành .xlsx rồi tải lên.",
        "Ví dụ tải “Bảng KLMT của Hacom.xls” đã đổi tên thành .xlsx.",
        "Thông báo cho người dùng phải nêu đúng tên file gốc và hướng dẫn Save As sang .xlsx thật.",
        "Người dùng biết chính xác cần làm gì (Save As) thay vì đọc lỗi kỹ thuật khó hiểu.",
        "Người dùng nhận một thông báo lỗi mơ hồ và không biết file nào, phải làm gì để sửa.",
    ),
    "test_format_job_error_message_bad_zip_file": G(
        "Báo lỗi dễ hiểu khi file không phải là Excel thật",
        "Người dùng đổi đuôi một file bất kỳ (txt, pdf...) thành .xlsx rồi tải lên.",
        "Ví dụ “Chào giá Nhà Thầu A Gốc.xlsx” thực chất là file không phải Excel.",
        "Thông báo phải nói rõ '...không phải là file Excel' và nêu đúng tên file gốc người dùng đã chọn.",
        "Người dùng phát hiện ngay nguyên nhân tải nhầm file.",
        "Người dùng tưởng hệ thống lỗi và không biết file nào cần kiểm tra lại.",
    ),
    "test_format_job_error_message_corrupt_format": G(
        "Báo lỗi dễ hiểu khi file Excel bị hỏng nội dung",
        "File có đuôi .xlsx hợp lệ nhưng cấu trúc bên trong bị hỏng (do tải lên bị lỗi, bị sửa tay...).",
        "Ví dụ file 'NhaThauB_BaoGia.xlsx' báo lỗi cấu trúc sheet khi đọc.",
        "Thông báo phải nói '...không đúng định dạng Excel' kèm tên file gốc, không lộ chi tiết kỹ thuật nội bộ.",
        "Người dùng biết cần tải lại file gốc thay vì gửi yêu cầu hỗ trợ vô ích.",
        "Người dùng nhận thông báo lỗi kỹ thuật khó hiểu (ví dụ traceback Python) gây hoang mang.",
    ),
    "test_format_job_error_message_backend_error": G(
        "Lỗi nội bộ của hệ thống không được hiển thị chi tiết kỹ thuật cho người dùng",
        "Một lỗi lập trình (ví dụ thiếu dữ liệu, sai kiểu) xảy ra bất ngờ trong quá trình xử lý.",
        "Ví dụ lỗi AttributeError/TypeError/KeyError phát sinh trong code xử lý.",
        "Người dùng chỉ nhận thông báo chung 'lỗi file', không thấy traceback hay tên biến nội bộ.",
        "Bảo vệ người dùng khỏi thông tin kỹ thuật vô nghĩa và tránh lộ chi tiết mã nguồn.",
        "Người dùng hoảng vì thấy thông báo lỗi kỹ thuật như 'NoneType object has no attribute' mà không hiểu gì.",
    ),
    "test_package_pipeline_with_corrupt_files": G(
        "Toàn luồng xử lý gói thầu phải dừng đúng cách khi cả PL01 và file nhà thầu đều hỏng",
        "Cả file Phụ lục 01 và file nhà thầu được tải lên đều là file giả (không phải Excel thật).",
        "Ví dụ 'PL01_Gốc_Hacom.xlsx' và 'BaoGia_NhaThauA.xlsx' đều là dữ liệu rác.",
        "Hệ thống phải dừng xử lý, nêu rõ tên file gốc nào bị lỗi và thông báo '...không phải là file Excel.'",
        "Không tạo báo cáo giả từ dữ liệu rác; người dùng biết chính xác file nào cần tải lại.",
        "Hệ thống có thể tạo ra báo cáo sai lệch hoàn toàn từ dữ liệu rác mà không ai biết.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - file giả mạo / sai định dạng
    # -------------------------------------------------------------------------
    "test_txt_renamed_to_xlsx_is_rejected_not_silently_parsed": G(
        "File văn bản đổi đuôi thành .xlsx phải bị từ chối, không được đọc nhầm",
        "Một file .txt chứa nội dung lung tung được đổi đuôi thành .xlsx rồi tải lên.",
        "Ví dụ file ghi 'nội dung linh tinh không liên quan gì đến excel cả' nhưng đặt tên .xlsx.",
        "Hệ thống phải báo lỗi (vì không phải file ZIP/Excel thật), không được coi đó là workbook hợp lệ.",
        "Ngăn người dùng (vô tình hoặc cố ý) đưa dữ liệu rác vào hệ thống so sánh.",
        "Hệ thống có thể bị treo, lỗi ngầm, hoặc tạo báo cáo vô nghĩa từ nội dung text ngẫu nhiên.",
    ),
    "test_zero_byte_file_with_xlsx_extension_is_rejected": G(
        "File .xlsx rỗng (0 byte) phải bị từ chối",
        "File tải lên bị lỗi giữa đường, kết quả là một file .xlsx hoàn toàn trống.",
        "Ví dụ file 'empty.xlsx' có kích thước 0 byte.",
        "Hệ thống phải báo lỗi khi cố đọc file, không được trả về một workbook giả vờ hợp lệ.",
        "Phát hiện sớm sự cố tải file thay vì xử lý tiếp với dữ liệu trống.",
        "Hệ thống có thể chạy tiếp với workbook trống và tạo báo cáo sai mà không cảnh báo.",
    ),
    "test_uppercase_extension_is_still_accepted": G(
        "Đuôi file viết hoa (.XLSX) vẫn phải được chấp nhận như .xlsx",
        "Người dùng tải file có đuôi viết hoa, ví dụ do hệ điều hành hoặc thiết bị khác đặt tên.",
        "Ví dụ file 'valid.XLSX' (chữ hoa) chứa dữ liệu hợp lệ.",
        "Hệ thống phải đọc được file này giống như đuôi '.xlsx' viết thường.",
        "Người dùng không bị từ chối oan chỉ vì cách viết hoa/thường của tên file.",
        "Người dùng dùng máy/thiết bị đặt tên đuôi hoa sẽ bị từ chối file hợp lệ một cách vô lý.",
    ),
    "test_xls_extension_gives_clear_vietnamese_error": G(
        "File .xls (Excel đời cũ) phải báo lỗi tiếng Việt rõ ràng, hướng dẫn cách sửa",
        "Người dùng tải file Excel theo định dạng cũ .xls (chưa chuyển sang .xlsx).",
        "Ví dụ file 'old.xls'.",
        "Thông báo lỗi phải nhắc đến '.xlsx' để người dùng biết cần Save As sang định dạng mới.",
        "Người dùng tự sửa được vấn đề mà không cần hỏi hỗ trợ kỹ thuật.",
        "Người dùng nhận lỗi mơ hồ và không biết phải làm gì với file Excel đời cũ của mình.",
    ),
    "test_zip_bomb_style_wrong_internal_structure_does_not_crash_silently": G(
        "File là ZIP hợp lệ nhưng không phải cấu trúc Excel thì phải báo lỗi, không được bỏ qua",
        "File có đuôi .xlsx và đúng là một file ZIP, nhưng bên trong không phải dữ liệu Excel (OOXML) thật.",
        "Ví dụ file ZIP chỉ chứa một văn bản 'hello.txt', không có cấu trúc bảng tính nào.",
        "Hệ thống phải phát hiện thiếu cấu trúc Excel và báo lỗi, không được trả về kết quả rỗng coi như thành công.",
        "Tránh trường hợp file giả dạng tinh vi (ZIP đúng nhưng nội dung sai) lọt qua kiểm tra.",
        "Một file ZIP giả mạo có thể đi qua các bước kiểm tra cơ bản và làm hỏng luồng xử lý phía sau.",
    ),
    "test_truncated_xlsx_raises_clear_error_not_garbage_data": G(
        "File Excel bị đứt giữa đường khi tải lên phải báo lỗi rõ ràng",
        "Quá trình tải file lên bị ngắt giữa đường (mất mạng, đóng tab...), file lưu lại chỉ có một nửa.",
        "Ví dụ file gốc đầy đủ bị cắt còn lại 50% dữ liệu byte.",
        "Hệ thống phải phát hiện file hỏng và báo lỗi, không được đọc ra dữ liệu thiếu rồi coi là kết quả đúng.",
        "Người dùng được yêu cầu tải lại file thay vì nhận một báo cáo thiếu sót mà không biết.",
        "Báo cáo có thể chỉ chứa một phần dữ liệu thật, dẫn đến kết luận sai về hồ sơ nhà thầu.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - file hợp lệ nhưng nội dung vô nghĩa
    # -------------------------------------------------------------------------
    "test_completely_empty_sheet_does_not_crash": G(
        "Sheet hoàn toàn trống không được làm crash hệ thống",
        "Nhà thầu tải lên một file Excel hợp lệ nhưng sheet bên trong không có bất kỳ dữ liệu nào.",
        "Ví dụ file chỉ có một sheet rỗng tên 'Sheet1'.",
        "Hệ thống đọc xong và trả về danh sách hạng mục rỗng kèm cảnh báo 'không đọc được hạng mục dữ liệu nào'.",
        "Hệ thống xử lý êm các file rỗng thay vì dừng đột ngột giữa quy trình của nhiều nhà thầu khác.",
        "Một file trống của một nhà thầu có thể làm toàn bộ tác vụ so sánh (gồm cả các nhà thầu khác) bị lỗi.",
    ),
    "test_random_text_without_any_header_keyword_yields_no_items_not_garbage": G(
        "Nội dung không liên quan gì đến hồ sơ thầu không được bịa ra hạng mục giả",
        "File Excel hợp lệ nhưng nội dung là những câu chữ ngẫu nhiên, không phải bảng khối lượng/giá thầu.",
        "Ví dụ các ô ghi 'con mèo', 'con chó', 'hôm nay trời đẹp'...",
        "Hệ thống không tìm thấy tiêu đề bảng hợp lệ nên phải trả về danh sách hạng mục rỗng, không tự suy diễn dữ liệu.",
        "Tránh tạo ra một báo cáo so sánh từ dữ liệu hoàn toàn không liên quan đến đấu thầu.",
        "Hệ thống có thể hiểu nhầm các ô chữ ngẫu nhiên là tên hạng mục/khối lượng và tạo báo cáo vô nghĩa.",
    ),
    "test_header_only_no_data_rows": G(
        "File chỉ có dòng tiêu đề, chưa có dữ liệu thì không được báo có hạng mục",
        "Nhà thầu tải lên file đã đặt đúng tiêu đề cột nhưng chưa kịp điền số liệu nào.",
        "Ví dụ dòng tiêu đề 'STT, Mã hiệu, Tên hạng mục...' nhưng không có dòng dữ liệu nào theo sau.",
        "Hệ thống phải nhận diện đúng tiêu đề nhưng trả về 0 hạng mục, không bịa thêm dữ liệu.",
        "Phân biệt rõ giữa 'chưa có dữ liệu' và 'có lỗi đọc file'.",
        "Hệ thống có thể báo lỗi sai hoặc tạo hạng mục ảo từ dòng tiêu đề.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - đọc số liệu bất thường
    # -------------------------------------------------------------------------
    "test_garbage_returns_none_not_exception": G(
        "Ô chứa chữ rác lẫn số không được hiểu nhầm thành một con số",
        "Một ô khối lượng/đơn giá vô tình bị nhập text rác hoặc mã hàng có lẫn chữ số.",
        "Ví dụ ô ghi 'abc123xyz' hoặc 'lung tung beng' thay vì một con số thật.",
        "Hàm đọc số phải trả về 'không có giá trị' (None), không được tự suy ra số 123 từ chuỗi chữ đó.",
        "Tránh lấy nhầm một đoạn số vô nghĩa trong text rác làm khối lượng/giá thật.",
        "Khối lượng hoặc đơn giá của một hạng mục có thể bị tính sai hoàn toàn mà không ai phát hiện (lỗi đã tìm thấy và sửa).",
    ),
    "test_math_error_detects_klxdg_mismatch": G(
        "Phải phát hiện khi Khối lượng × Đơn giá không khớp với Thành tiền ghi trong file",
        "File nhà thầu tự ghi cột 'thành tiền' nhưng số liệu không khớp với khối lượng nhân đơn giá.",
        "Ví dụ 10 (khối lượng) × 1.000 (đơn giá) = 10.000, nhưng cột thành tiền lại ghi 5.000.",
        "Hệ thống phải tính ra mức chênh lệch và gắn cờ cảnh báo sai phép tính.",
        "Phát hiện lỗi tính toán hoặc gian lận số liệu trong hồ sơ chào giá.",
        "Một khoản tiền sai có thể lọt vào báo cáo tổng hợp mà không bị phát hiện.",
    ),
    "test_math_error_none_when_any_input_missing": G(
        "Không được báo lỗi phép tính khi thiếu dữ liệu để tính",
        "Một trong ba giá trị (khối lượng, đơn giá, thành tiền) bị bỏ trống.",
        "Ví dụ chỉ có khối lượng và đơn giá, không có thành tiền để so sánh.",
        "Hệ thống phải trả về 'không xác định được lỗi' thay vì báo sai phép tính một cách giả tạo.",
        "Tránh tạo cảnh báo sai (báo động giả) khi đơn giản là thiếu dữ liệu để kiểm tra.",
        "Báo cáo có thể tràn ngập cảnh báo giả, làm người kiểm tra mất niềm tin vào hệ thống.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - luồng so sánh phụ lục/nhà thầu (tender_package)
    # -------------------------------------------------------------------------
    "test_no_bidder_files_raises_value_error": G(
        "Không cho phép chạy so sánh khi chưa có file nhà thầu nào",
        "Người dùng bấm chạy chức năng so sánh phụ lục nhưng chưa tải lên file nhà thầu nào.",
        "Ví dụ chỉ có file PL01, danh sách hồ sơ nhà thầu để trống.",
        "Hệ thống phải dừng ngay và báo 'Cần ít nhất 1 hồ sơ nhà thầu để đối chiếu phụ lục'.",
        "Tránh chạy một tác vụ vô nghĩa (không có gì để so sánh) gây lãng phí thời gian xử lý.",
        "Hệ thống có thể chạy treo, lỗi mơ hồ, hoặc tạo báo cáo trống không rõ nguyên nhân.",
    ),
    "test_no_appendix_at_all_raises_value_error": G(
        "Không cho phép chạy so sánh khi không có Phụ lục 01 lẫn Phụ lục 02",
        "Người dùng chỉ tải lên hồ sơ nhà thầu mà quên tải phụ lục làm căn cứ đối chiếu.",
        "Ví dụ chỉ có file 'bidder.xlsx', không có PL01 và PL02.",
        "Hệ thống phải dừng ngay và báo 'Cần tải lên ít nhất một phụ lục: Phụ lục 01 hoặc Phụ lục 02'.",
        "Người dùng biết ngay cần bổ sung phụ lục, tránh chờ kết quả của một tác vụ vô nghĩa.",
        "Hệ thống không có cơ sở pháp lý/kỹ thuật nào để đối chiếu nhưng vẫn cố chạy, dẫn đến lỗi khó hiểu hoặc kết quả sai.",
    ),
    "test_missing_pl2_file_on_disk_raises_clear_error": G(
        "Báo lỗi rõ ràng khi file Phụ lục 02 bị thiếu trên đĩa khi xử lý",
        "Đường dẫn tới file Phụ lục 02 được truyền vào nhưng file thực tế không tồn tại (ví dụ do lỗi lưu file tạm).",
        "Ví dụ hệ thống được yêu cầu đọc 'khong_ton_tai.xlsx' nhưng file này không có thật trên đĩa.",
        "Lỗi trả về phải nêu rõ đang xảy ra ở bước đọc PHỤ LỤC 02, không phải lỗi chung mơ hồ.",
        "Người vận hành/hỗ trợ xác định nhanh đúng bước nào trong quy trình bị lỗi.",
        "Lỗi tệp tin chung chung khiến khó xác định do thiếu PL01, PL02 hay file nhà thầu.",
    ),
    "test_pl2_without_recognizable_headers_does_not_crash_but_warns": G(
        "Khi file Phụ lục 02 không đúng mẫu (thiếu cột Thương hiệu/Xuất xứ), hệ thống vẫn phải chạy xong và cảnh báo rõ",
        "Người dùng tải nhầm một file Excel khác vào ô Phụ lục 02, không có cột yêu cầu vật tư/thương hiệu/xuất xứ.",
        "Ví dụ file chỉ có 'Cột A, Cột B, Cột C' không liên quan gì đến yêu cầu vật tư.",
        "Báo cáo vẫn phải được tạo ra, nhưng phải có cảnh báo rõ là không đọc được yêu cầu nào từ Phụ lục 02.",
        "Người dùng biết ngay là đã tải nhầm file, không lầm tưởng rằng việc kiểm tra thương hiệu/xuất xứ đã được thực hiện đầy đủ.",
        "Người dùng có thể tưởng nhầm hồ sơ đã được kiểm tra đầy đủ thương hiệu/xuất xứ, trong khi thực tế bước đó chưa từng chạy.",
    ),
    "test_single_bidder_with_zero_items_produces_empty_but_valid_report": G(
        "Khi nhà thầu nộp file trống (không có hạng mục nào), hệ thống phải báo đầy đủ các hạng mục đó là 'thiếu'",
        "Có Phụ lục 01 quy định rõ các hạng mục cần chào giá, nhưng file nhà thầu hoàn toàn trống.",
        "Ví dụ PL01 yêu cầu 2 hạng mục, nhưng nhà thầu nộp file Excel có sheet trống không một dòng dữ liệu.",
        "Báo cáo phải đếm đủ 2 hạng mục đó ở trạng thái 'thiếu' (MISSING), không được bỏ qua.",
        "Phát hiện ngay trường hợp nhà thầu nộp nhầm/thiếu hồ sơ chào giá.",
        "Một hồ sơ thực chất trống rỗng có thể bị đánh giá nhầm là 'không có vấn đề gì' vì không có dữ liệu để so sánh.",
    ),
    "test_single_bidder_disables_peer_price_comparison": G(
        "Khi chỉ có một nhà thầu duy nhất, hệ thống không được tự so sánh giá của họ với ai",
        "Chỉ có đúng một hồ sơ nhà thầu được nộp, không có nhà thầu thứ hai để đối chiếu giá.",
        "Ví dụ chỉ một nhà thầu 'NT duy nhất' chào giá cho các hạng mục trong PL01.",
        "Audit của báo cáo phải ghi rõ 'không so sánh giá ngang hàng' kèm lý do, vì không có đối tượng thứ hai để so.",
        "Tránh đưa ra nhận định 'giá cao/giá thấp' khi không có cơ sở để so sánh, gây hiểu nhầm cho người đánh giá thầu.",
        "Một mức giá hợp lý có thể bị gắn nhãn bất thường một cách vô căn cứ chỉ vì so sánh sai logic.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - đọc Phụ lục 02 (pl2_reader)
    # -------------------------------------------------------------------------
    "test_pl2_wrong_extension_raises": G(
        "Phụ lục 02 sai định dạng (.xls) phải bị từ chối ngay từ đầu",
        "Người dùng tải file Phụ lục 02 ở định dạng Excel cũ chưa chuyển sang .xlsx.",
        "Ví dụ file 'pl2.xls'.",
        "Hệ thống phải báo lỗi yêu cầu định dạng .xlsx, không cố đọc tiếp.",
        "Tránh xử lý một file mà hệ thống chắc chắn không đọc đúng được.",
        "Hệ thống có thể cố đọc và trả về kết quả rác hoặc lỗi không rõ nguyên nhân.",
    ),
    "test_pl2_empty_workbook_returns_empty_with_warning": G(
        "Phụ lục 02 trống phải trả về danh sách yêu cầu rỗng kèm cảnh báo rõ ràng",
        "File Phụ lục 02 hợp lệ về định dạng nhưng không có nội dung gì bên trong.",
        "Ví dụ file chỉ có một sheet trống.",
        "Hệ thống trả về danh sách yêu cầu vật tư rỗng và một cảnh báo 'Không đọc được yêu cầu vật tư nào từ Phụ lục 02'.",
        "Người dùng biết chính xác lý do không có kiểm tra thương hiệu/xuất xứ nào được áp dụng.",
        "Việc thiếu Phụ lục 02 thực chất có thể bị hiểu lầm thành 'đã kiểm tra và không có vấn đề gì'.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - tải file lên ở tầng giao diện (app.py)
    # -------------------------------------------------------------------------
    "test_sanitize_strips_path_traversal": G(
        "Tên file độc hại kiểu '../../etc/passwd' phải bị làm sạch, không được ghi ra ngoài thư mục cho phép",
        "Người dùng (hoặc kẻ tấn công) đặt tên file tải lên chứa các ký tự '..' và '/' để cố thoát khỏi thư mục lưu file.",
        "Ví dụ tên file '../../../etc/passwd.xlsx'.",
        "Tên file sau khi xử lý không còn chứa '..' hay dấu '/'.",
        "Ngăn chặn kiểu tấn công Path Traversal ghi đè file hệ thống ngoài ý muốn.",
        "Kẻ tấn công có thể lợi dụng tên file để ghi đè hoặc truy cập file ngoài phạm vi cho phép của ứng dụng.",
    ),
    "test_sanitize_strips_path_traversal_windows_style": G(
        "Tên file độc hại kiểu Windows '..\\\\..\\\\Windows\\\\...' cũng phải bị làm sạch",
        "Giống tấn công path traversal nhưng dùng dấu gạch chéo ngược kiểu đường dẫn Windows.",
        "Ví dụ tên file '..\\\\..\\\\Windows\\\\System32\\\\evil.xlsx'.",
        "Tên file sau khi xử lý không còn chứa '..' hay dấu '\\\\'.",
        "Đảm bảo việc làm sạch tên file hoạt động trên cả hai kiểu đường dẫn Windows và Unix.",
        "Hệ thống chạy trên Windows có thể bị tấn công bằng kiểu đường dẫn đặc thù mà bộ lọc Unix bỏ sót.",
    ),
    "test_sanitize_empty_name_falls_back": G(
        "Tên file rỗng phải được thay bằng một tên mặc định hợp lệ",
        "Trường hợp hiếm khi trình duyệt gửi lên tên file rỗng hoặc không hợp lệ.",
        "Ví dụ tên file gửi lên là chuỗi rỗng ''.",
        "Hệ thống phải tự đặt một tên file mặc định thay vì lưu file không tên.",
        "Tránh lỗi hệ thống file khi gặp tên rỗng.",
        "Việc lưu file có thể thất bại với lỗi khó hiểu nếu tên file rỗng không được xử lý.",
    ),
    "test_save_upload_rejects_disallowed_extension": G(
        "Từ chối ngay các file có đuôi không được phép (ví dụ .exe) trước khi lưu vào đĩa",
        "Người dùng tải lên một file không phải Excel, ví dụ file thực thi.",
        "Ví dụ file 'evil.exe' được gửi tới chức năng chỉ chấp nhận .xlsx.",
        "Yêu cầu phải bị từ chối với mã lỗi 400 (yêu cầu không hợp lệ) và không được lưu file đó vào đĩa.",
        "Ngăn người dùng tải lên các loại file nguy hiểm hoặc không liên quan vào máy chủ.",
        "Máy chủ có thể vô tình lưu trữ file thực thi hoặc file độc hại do không kiểm tra đuôi file.",
    ),
    "test_save_upload_rejects_empty_file": G(
        "Từ chối file tải lên có dung lượng 0 byte",
        "Người dùng tải lên một file rỗng (ví dụ do lỗi mạng khi chọn file).",
        "Ví dụ file 'empty.xlsx' có nội dung trống.",
        "Yêu cầu bị từ chối với thông báo 'File tải lên rỗng' và file tạm không được giữ lại trên đĩa.",
        "Phát hiện sớm lỗi tải file, tránh xử lý tiếp với dữ liệu không có gì.",
        "Hệ thống có thể tạo một tác vụ xử lý cho một file trống, gây lãng phí và lỗi khó hiểu ở bước sau.",
    ),
    "test_save_upload_rejects_file_over_limit": G(
        "Từ chối file tải lên vượt quá giới hạn dung lượng cho phép",
        "Người dùng tải lên một file có kích thước lớn hơn mức hệ thống cho phép.",
        "Ví dụ file 2KB được tải lên trong khi giới hạn cấu hình chỉ cho phép 1KB.",
        "Yêu cầu bị từ chối với mã lỗi 413 (file quá lớn) và phần file đã ghi tạm phải được xoá sạch, không để lại rác trên đĩa.",
        "Bảo vệ máy chủ khỏi bị quá tải ổ đĩa do file tải lên quá lớn hoặc tấn công làm đầy dung lượng.",
        "Máy chủ có thể bị đầy ổ đĩa hoặc chậm dần theo thời gian do các file dở dang không bị dọn dẹp.",
    ),
    "test_save_upload_accepts_valid_small_file": G(
        "File hợp lệ, đúng định dạng và trong giới hạn dung lượng phải được lưu thành công",
        "Trường hợp bình thường: người dùng tải lên một file Excel nhỏ, hợp lệ.",
        "Ví dụ file 'ok.xlsx' với nội dung hợp lệ và dung lượng nhỏ.",
        "File phải được lưu đúng vào vị trí đích với nội dung giữ nguyên, không bị từ chối oan.",
        "Đảm bảo các bước kiểm tra an toàn (đuôi file, dung lượng) không chặn nhầm các yêu cầu hợp lệ.",
        "Các bộ lọc bảo mật quá chặt có thể vô tình chặn luôn cả người dùng hợp lệ, gây khó chịu khi sử dụng hệ thống.",
    ),

    # -------------------------------------------------------------------------
    # Negative cases mở rộng - chuyển lỗi kỹ thuật thành thông báo người dùng
    # -------------------------------------------------------------------------
    "test_encrypted_or_unknown_underlying_error_falls_back_to_generic_excel_message": G(
        "File Excel có mật khẩu/mã hoá vẫn phải báo lỗi thân thiện, không lộ chi tiết kỹ thuật",
        "Nhà thầu nộp một file Excel được đặt mật khẩu bảo vệ, hệ thống không tự mở được.",
        "Ví dụ file 'BaoGia_C_CoMatKhau.xlsx' báo lỗi 'Workbook is encrypted and password-protected'.",
        "Thông báo cho người dùng vẫn phải nêu đúng tên file gốc và nói 'không đúng định dạng Excel', không hiển thị câu lỗi kỹ thuật gốc.",
        "Người dùng biết cần gỡ mật khẩu file trước khi tải lên, dù lỗi kỹ thuật bên dưới là loại lỗi hệ thống chưa từng gặp.",
        "Người dùng nhận một câu lỗi tiếng Anh kỹ thuật khó hiểu, không biết hướng xử lý.",
    ),
    "test_unknown_request_mapping_still_returns_something_safe": G(
        "Hệ thống không bao giờ được 'câm lặng' hoặc crash khi gặp lỗi không xác định được tên file/nhà thầu",
        "Một lỗi xảy ra nhưng không khớp với bất kỳ thông tin nào trong yêu cầu (ví dụ thiếu thông tin ngữ cảnh).",
        "Ví dụ lỗi nhắc tới 'unknown.xlsx' mà không có dữ liệu request nào để tham chiếu.",
        "Hàm tạo thông báo lỗi vẫn phải trả về một chuỗi văn bản hợp lệ, không phải None và không ném thêm lỗi mới.",
        "Bảo đảm người dùng luôn nhận được một phản hồi nào đó, dù là trường hợp hiếm gặp nhất.",
        "Toàn bộ tác vụ có thể bị crash thêm lần hai ngay tại bước hiển thị lỗi, khiến người dùng không nhận được phản hồi nào cả.",
    ),

    # -------------------------------------------------------------------------
    # Báo cáo so sánh giá giữa các nhà thầu (Ma trận đơn giá)
    # -------------------------------------------------------------------------
    "test_price_matrix_marks_the_outlier_cell_directly": G(
        "Tự động tô màu và gắn ghi chú ngay trên ô giá khi nhà thầu báo giá lệch hẳn",
        "Bốn nhà thầu cùng báo giá một hạng mục: ba nhà thầu báo giá gần nhau, một nhà thầu báo giá cách biệt rất xa.",
        "Ví dụ ba nhà thầu báo 95, 100, 105; một nhà thầu báo 500 cho cùng một hạng mục 'Tủ điện tổng'.",
        "Đúng ô giá của nhà thầu báo 500 (không phải một cột riêng) phải được tô màu cảnh báo và có ghi chú (hiện khi rê chuột) nêu rõ tên nhà thầu, giá trị, trung vị và mức lệch %; ô giá của các nhà thầu báo gần nhau thì không bị tô màu và không có ghi chú.",
        "Người xem báo cáo chỉ cần rê chuột vào đúng ô giá bất thường để biết ngay vì sao nó bị đánh dấu, không cần dò một cột ghi chú riêng hay tự tính toán so sánh từng dòng.",
        "Một mức giá bất thường có thể bị bỏ lọt trong hàng nghìn dòng dữ liệu, dẫn đến đánh giá thầu sai mà không ai phát hiện kịp thời.",
    ),
    "test_price_matrix_has_no_comment_when_all_bidders_close": G(
        "Không gắn ghi chú/tô màu giả khi tất cả nhà thầu báo giá tương đương nhau",
        "Các nhà thầu báo giá cho cùng một hạng mục chỉ chênh nhau rất ít, trong phạm vi bình thường.",
        "Ví dụ ba nhà thầu báo 98, 100, 102 cho cùng một hạng mục — mức chênh chỉ vài phần trăm.",
        "Không ô giá nào trong dòng đó được tô màu cảnh báo hay gắn ghi chú, vì không có nhà thầu nào lệch đáng kể.",
        "Người xem báo cáo không bị làm phiền bởi các cảnh báo không cần thiết khi giá cả vẫn trong mức hợp lý.",
        "Báo cáo có thể tô màu và cảnh báo tràn lan dù không có vấn đề thật, làm người dùng mất niềm tin vào tính năng cảnh báo.",
    ),

    # -------------------------------------------------------------------------
    # File tổng hợp độc lập "Bảng chào giá tổng hợp" (đúng format file mẫu)
    # -------------------------------------------------------------------------
    "test_summary_has_one_sheet_per_hangmuc_with_side_by_side_blocks": G(
        "Tự sinh file tổng hợp đúng format: mỗi hạng mục một sheet, các nhà thầu xếp cạnh nhau",
        "Có nhiều nhà thầu cùng chào giá; hệ thống gộp tất cả vào một file tổng hợp riêng, mỗi hạng mục (sheet gốc) là một trang, mỗi nhà thầu một khối cột nằm cạnh nhau — giống hệt bảng chào giá tổng hợp thực tế.",
        "Ví dụ hạng mục 'HT điện' thành một sheet riêng; trong đó bốn nhà thầu xếp cạnh nhau, mỗi nhà thầu có đủ các cột KL chào, mô tả/quy cách, mã hiệu, thương hiệu, xuất xứ, các thành phần đơn giá, ĐG tổng hợp và thành tiền.",
        "Sheet mang đúng tên hạng mục gốc, dòng tiêu đề ghi đủ tên cả bốn nhà thầu, mỗi nhà thầu có cột 'ĐG tổng hợp' và 'Thành tiền NT chào' riêng, và TUYỆT ĐỐI không có cột phân tích phụ (Mức độ, Điểm bất thường).",
        "Người đánh giá thầu xem được toàn bộ nhà thầu trên đúng bảng quen thuộc của mình, không bị chèn thêm các cột kỹ thuật lạ.",
        "Nếu dựng sai cấu trúc, cột của nhà thầu này có thể lẫn sang nhà thầu khác, hoặc file lại xuất hiện các cột phân tích mà người dùng không muốn.",
    ),
    "test_summary_marks_deviating_price_cells_directly": G(
        "Đánh dấu trực tiếp lên ô giá của nhà thầu báo lệch nhiều trong file tổng hợp",
        "Trong file tổng hợp, một nhà thầu báo đơn giá cách biệt hẳn so với các nhà thầu còn lại cho cùng một hạng mục.",
        "Ví dụ ba nhà thầu báo 95, 100, 105; một nhà thầu báo 500 cho cùng hạng mục.",
        "Đúng ô 'ĐG tổng hợp' (và 'Thành tiền NT chào') của nhà thầu báo 500 được tô màu cảnh báo và gắn ghi chú ngay trên ô, nêu rõ mức lệch so với trung vị; ô của các nhà thầu báo gần nhau không bị đánh dấu.",
        "Người xem chỉ cần rê chuột vào đúng ô giá bị đánh dấu để hiểu vì sao nó bất thường, ngay trên bảng tổng hợp.",
        "Một mức giá bất thường có thể bị bỏ lọt giữa hàng nghìn dòng, dẫn đến đánh giá thầu sai.",
    ),
    "test_summary_no_marks_when_prices_close": G(
        "File tổng hợp không đánh dấu khi các nhà thầu báo giá tương đương nhau",
        "Tất cả nhà thầu báo giá cho cùng hạng mục chỉ chênh nhau rất ít.",
        "Ví dụ ba nhà thầu báo 98, 100, 102.",
        "Không ô giá nào trong file tổng hợp bị tô màu hay gắn ghi chú cảnh báo.",
        "Tránh làm người xem rối mắt với cảnh báo thừa khi giá cả vẫn hợp lý.",
        "File tô màu tràn lan sẽ làm mất ý nghĩa của việc đánh dấu.",
    ),
    "test_numbering_row_with_float_values_is_detected": G(
        "Nhận diện đúng dòng chú giải đánh số cột kể cả khi số ở dạng 1.0, 2.0",
        "Nhiều file Excel có một dòng ghi số thứ tự cột (1, 2, 3...) ngay dưới tiêu đề; khi đọc bằng máy, các số này có thể ở dạng '1.0', '2.0'.",
        "Ví dụ dòng '1, 2, 3, 4, 5, 6, 7, 8, 16=11+12+13+14+15' — chỉ là chú thích đánh số cột, không phải hàng hóa.",
        "Hệ thống phải nhận ra đây là dòng chú giải và bỏ qua, không đọc nhầm thành một hạng mục tên là '2'.",
        "Tránh để dòng đánh số cột lọt vào báo cáo như một hạng mục giả rồi bị gắn cờ 'phát sinh' oan.",
        "Báo cáo có thể chứa hàng loạt 'hạng mục' rác tên là số, làm sai số liệu và gây nhiễu cho người đánh giá.",
    ),
    "test_numbering_row_does_not_misfire_on_real_priced_row": G(
        "Không nhầm một hạng mục thật thành dòng đánh số cột",
        "Một hàng hóa thật cũng có thể bắt đầu bằng số thứ tự 1, 2, 3, 4.",
        "Ví dụ '1 | Tủ điện tổng | Cái | 4 | Schneider' — là hạng mục thật, không phải dòng chú giải.",
        "Hệ thống vẫn giữ lại dòng này như một hạng mục, không bỏ nhầm.",
        "Đảm bảo việc lọc dòng chú giải không vô tình xóa mất hàng hóa thật.",
        "Một hạng mục hợp lệ có thể biến mất khỏi báo cáo nếu bộ lọc quá tay.",
    ),
    "test_legend_and_section_subtotal_excluded_from_comparable_items": G(
        "Dòng đánh số cột và tiêu đề mục có tổng phụ không được coi là hạng mục so sánh",
        "File chào giá có dòng đánh số cột, có tiêu đề mục lớn (vd 'A. ĐẦU MỤC CÔNG VIỆC THEO KLMT') kèm một con số tổng phụ rất lớn ở cột thành tiền.",
        "Ví dụ tiêu đề mục 'A. ĐẦU MỤC...' có thành tiền 76 tỷ (là tổng của cả mục), không có đơn vị/khối lượng/đơn giá.",
        "Dòng đánh số cột bị bỏ hẳn; tiêu đề mục được giữ lại nhưng đánh dấu là dòng tổng phụ (không đem ra so sánh như một hàng hóa).",
        "Tránh việc các dòng tiêu đề/tổng phụ bị gắn cờ 'phát sinh' hoặc 'bất thường' một cách vô lý, gây nhiễu báo cáo.",
        "Báo cáo có thể đầy cảnh báo giả ở các dòng tiêu đề mục, khiến người đánh giá mất thời gian và giảm tin tưởng.",
    ),
    "test_summary_splits_multiple_hangmuc_into_separate_sheets": G(
        "Nhiều hạng mục được tách thành nhiều sheet riêng trong file tổng hợp",
        "Hồ sơ chào giá có nhiều hạng mục khác nhau (ví dụ hệ thống điện và hệ thống cấp thoát nước).",
        "Ví dụ mỗi nhà thầu có sheet 'HT điện' và sheet 'HT CTN'; file tổng hợp phải tạo đúng hai trang tương ứng.",
        "File tổng hợp có một sheet riêng cho mỗi hạng mục, mang đúng tên hạng mục gốc.",
        "Giữ đúng cách tổ chức theo hạng mục như bảng chào giá gốc, dễ tra cứu từng phần.",
        "Nếu gộp hết vào một sheet hoặc đặt sai tên, người dùng khó đối chiếu với hồ sơ gốc.",
    ),
}


# =============================================================================
# TIỆN ÍCH
# =============================================================================

def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def safe_text(value: Any, limit: int | None = None) -> str:
    try:
        text = value if isinstance(value, str) else repr(value)
    except Exception:
        text = f"<không thể hiển thị {type(value).__name__}>"
    if limit is not None and len(text) > limit:
        return text[:limit] + "\n... [đã rút gọn]"
    return text


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {safe_text(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return safe_text(value, 2_000)


def status_label(status: str) -> str:
    return {
        "passed": "PASS",
        "failed": "FAIL",
        "error": "ERROR",
        "skipped": "SKIPPED",
        "xfailed": "XFAIL",
        "xpassed": "XPASS",
        "not_run": "NOT RUN",
    }.get(status, status.upper())


def status_icon(status: str) -> str:
    return {
        "passed": "✅",
        "failed": "❌",
        "error": "💥",
        "skipped": "⏭️",
        "xfailed": "⚠️",
        "xpassed": "🟣",
        "not_run": "➖",
    }.get(status, "•")


def humanize_test_name(name: str) -> str:
    name = re.sub(r"\[.*\]$", "", name)
    name = re.sub(r"^test_", "", name)
    words = name.replace("__", "_").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else "Testcase chưa có tên mô tả"


def trim_multiline(value: str, limit: int) -> str:
    value = value or ""
    if len(value) <= limit:
        return value
    return value[:limit] + "\n... [đã rút gọn]"


def detect_git_info(project_root: Path) -> dict[str, str]:
    result = {"branch": "", "commit": "", "dirty": ""}
    commands = {
        "branch": ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        "commit": ["git", "rev-parse", "--short", "HEAD"],
        "dirty": ["git", "status", "--porcelain"],
    }
    for key, command in commands.items():
        try:
            proc = subprocess.run(
                command,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if proc.returncode == 0:
                value = proc.stdout.strip()
                result[key] = ("yes" if value else "no") if key == "dirty" else value
        except (OSError, subprocess.SubprocessError):
            pass
    return result



# =============================================================================
# KIỂM TRA ĐỘ ĐẦY ĐỦ CỦA VIỆC THU THẬP TESTCASE
# =============================================================================

def count_declared_test_functions(path: Path) -> tuple[int, str]:
    """Đếm các hàm test_* được khai báo trực tiếp trong file bằng AST.

    Trả về:
        (số hàm test, thông báo lỗi cú pháp nếu có)
    """

    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            source = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            return 0, f"Không đọc được file: {type(exc).__name__}: {exc}"
    except Exception as exc:
        return 0, f"Không đọc được file: {type(exc).__name__}: {exc}"

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return 0, f"Lỗi cú pháp dòng {exc.lineno}: {exc.msg}"

    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                count += 1

    return count, ""


def discover_test_files(
    tests_path: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    """Tìm toàn bộ file pytest theo quy tắc test_*.py hoặc *_test.py."""

    candidates: set[Path] = set()

    if tests_path.is_file():
        if tests_path.suffix.lower() == ".py":
            candidates.add(tests_path.resolve())
    else:
        for pattern in ("test_*.py", "*_test.py"):
            for path in tests_path.rglob(pattern):
                if "__pycache__" not in path.parts and path.is_file():
                    candidates.add(path.resolve())

    rows: list[dict[str, Any]] = []
    for path in sorted(candidates):
        try:
            relative = str(path.relative_to(project_root))
        except ValueError:
            relative = str(path)

        declared_count, parse_error = count_declared_test_functions(path)
        rows.append({
            "file": relative,
            "declared_test_functions": declared_count,
            "collected_testcases": 0,
            "status": "pending",
            "note": parse_error,
        })

    return rows


def build_discovery_audit(
    tests_path: Path,
    project_root: Path,
    collected_tests: Iterable["TestCaseResult"],
) -> dict[str, Any]:
    """So sánh file tồn tại trên ổ đĩa với file mà pytest thực sự thu thập."""

    rows = discover_test_files(tests_path, project_root)
    collected_counter = Counter(test.file for test in collected_tests)

    missing_files: list[str] = []
    empty_files: list[str] = []

    for row in rows:
        collected = int(collected_counter.get(row["file"], 0))
        row["collected_testcases"] = collected

        if row["note"]:
            row["status"] = "parse_error"
            missing_files.append(row["file"])
        elif row["declared_test_functions"] > 0 and collected == 0:
            row["status"] = "missing"
            row["note"] = (
                "File có hàm test_* nhưng pytest không thu thập testcase nào. "
                "Có thể đang mở báo cáo cũ, dùng bộ lọc -k/-m, file bị ignore, "
                "hoặc cấu hình pytest đã loại file này."
            )
            missing_files.append(row["file"])
        elif row["declared_test_functions"] == 0 and collected == 0:
            row["status"] = "empty"
            row["note"] = "File theo mẫu test nhưng không khai báo hàm test_*."
            empty_files.append(row["file"])
        else:
            row["status"] = "collected"
            row["note"] = (
                f"Pytest đã thu thập {collected} testcase từ "
                f"{row['declared_test_functions']} hàm test."
            )

    discovered_set = {row["file"] for row in rows}
    unexpected_collected = sorted(
        file_name
        for file_name in collected_counter
        if file_name not in discovered_set
    )

    incomplete_files = sorted(set(missing_files + empty_files))

    return {
        "discovered_file_count": len(rows),
        "collected_file_count": sum(1 for row in rows if row["collected_testcases"] > 0),
        "missing_file_count": len(missing_files),
        "empty_file_count": len(empty_files),
        "incomplete_file_count": len(incomplete_files),
        "missing_files": missing_files,
        "empty_files": empty_files,
        "incomplete_files": incomplete_files,
        "unexpected_collected_files": unexpected_collected,
        "files": rows,
    }


def get_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = get_call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def analyze_test_source(obj: Any) -> dict[str, Any]:
    """Đọc source của test để lấy assert, dữ liệu literal và các hàm được gọi."""

    result = {
        "source_code": "",
        "assertions": [],
        "literal_assignments": {},
        "called_functions": [],
    }
    if obj is None:
        return result

    try:
        source = textwrap.dedent(inspect.getsource(obj))
    except (OSError, TypeError):
        return result

    result["source_code"] = safe_text(source, MAX_SOURCE_CHARS)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    assertions: list[str] = []
    assignments: dict[str, Any] = {}
    calls: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            segment = ast.get_source_segment(source, node.test)
            assertions.append(segment or ast.dump(node.test, include_attributes=False))

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[ast.expr] = []
            value_node: ast.expr | None = None
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
                value_node = node.value
            else:
                targets = [node.target]
                value_node = node.value

            if value_node is None:
                continue
            try:
                value = ast.literal_eval(value_node)
            except Exception:
                continue
            value = json_safe(value)

            for target in targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = value

        elif isinstance(node, ast.Call):
            name = get_call_name(node.func)
            if name and name not in calls:
                calls.append(name)

    result["assertions"] = assertions[:30]
    result["literal_assignments"] = dict(list(assignments.items())[:30])
    result["called_functions"] = calls[:30]
    return result


def fallback_guide(name: str, docstring: str, analysis: dict[str, Any]) -> Guide:
    readable = docstring.splitlines()[0].strip() if docstring else humanize_test_name(name)
    assertions = analysis.get("assertions") or []
    assertion_text = "; ".join(assertions[:3]) if assertions else "các điều kiện assert trong testcase"
    return G(
        title=readable,
        scenario="Testcase tạo một tình huống cụ thể trong mã nguồn để kiểm tra chức năng tương ứng.",
        example=(
            "Báo cáo chưa có mô tả nghiệp vụ viết tay cho testcase này. "
            "Dữ liệu literal và tham số thực tế được hiển thị ở phần “Bằng chứng kỹ thuật”."
        ),
        expected=f"Tất cả điều kiện phải đúng, tiêu biểu: {assertion_text}.",
        business_meaning="Chứng minh chức năng được kiểm tra hoạt động đúng với dữ liệu test hiện tại.",
        failure_impact="Cần đọc assertion và traceback để xác định hành vi nào đang sai.",
    )


def guide_for(name: str, docstring: str, analysis: dict[str, Any]) -> Guide:
    base_name = re.sub(r"\[.*\]$", "", name)
    return KNOWN_GUIDES.get(base_name) or fallback_guide(base_name, docstring, analysis)


def result_explanation(status: str, guide: Guide, reason: str = "") -> str:
    if status == "passed":
        return (
            f"ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: "
            f"{guide.expected} Nói đơn giản: ví dụ được nêu trong testcase đã cho "
            f"kết quả đúng và không có điều kiện kiểm tra nào bị sai."
        )
    if status == "failed":
        return (
            f"CHƯA ĐẠT. Kết quả thực tế không đáp ứng yêu cầu: {guide.expected} "
            f"Xem phần traceback để biết giá trị thực tế khác giá trị mong đợi ở đâu."
            + (f" Thông tin thêm: {reason}" if reason else "")
        )
    if status == "error":
        return (
            "CHƯA THỂ KẾT LUẬN vì testcase gặp lỗi khi chuẩn bị, chạy hoặc dọn dẹp. "
            f"Hành vi cần kiểm tra vốn là: {guide.expected}"
            + (f" Lỗi ghi nhận: {reason}" if reason else "")
        )
    if status == "skipped":
        return (
            "CHƯA ĐƯỢC KIỂM TRA vì testcase bị bỏ qua. Không nên xem đây là bằng "
            "chứng chức năng đã đúng."
            + (f" Lý do: {reason}" if reason else "")
        )
    if status == "xfailed":
        return (
            "LỖI ĐÃ BIẾT. Test được dự kiến thất bại nên không làm cả phiên test đỏ, "
            "nhưng chức năng vẫn chưa đạt hoàn toàn."
            + (f" Lý do: {reason}" if reason else "")
        )
    if status == "xpassed":
        return (
            "CHỨC NĂNG CÓ THỂ ĐÃ ĐƯỢC SỬA. Test từng được đánh dấu dự kiến thất bại "
            "nhưng hiện lại chạy đúng; cần xóa hoặc cập nhật marker xfail."
        )
    return "Testcase được thu thập nhưng chưa chạy nên chưa có kết luận."


# =============================================================================
# MÔ HÌNH KẾT QUẢ
# =============================================================================

@dataclasses.dataclass
class TestCaseResult:
    nodeid: str
    name: str
    original_name: str
    file: str
    line: int
    class_name: str = ""
    docstring: str = ""
    markers: list[str] = dataclasses.field(default_factory=list)
    parameters: dict[str, Any] = dataclasses.field(default_factory=dict)
    source_code: str = ""
    assertions: list[str] = dataclasses.field(default_factory=list)
    literal_assignments: dict[str, Any] = dataclasses.field(default_factory=dict)
    called_functions: list[str] = dataclasses.field(default_factory=list)
    guide: dict[str, str] = dataclasses.field(default_factory=dict)
    status: str = "not_run"
    duration_seconds: float = 0.0
    setup_seconds: float = 0.0
    call_seconds: float = 0.0
    teardown_seconds: float = 0.0
    reason: str = ""
    traceback: str = ""
    stdout: str = ""
    stderr: str = ""
    logs: str = ""
    phases: dict[str, str] = dataclasses.field(default_factory=dict)

    @property
    def explanation(self) -> str:
        guide = Guide(**self.guide)
        return result_explanation(self.status, guide, self.reason)


@dataclasses.dataclass
class CollectionError:
    nodeid: str
    message: str
    traceback: str


# =============================================================================
# PYTEST PLUGIN
# =============================================================================

class DetailedReportPlugin:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.started_at = now_iso()
        self.finished_at = ""
        self.start_perf = time.perf_counter()
        self.elapsed_seconds = 0.0
        self.tests: dict[str, TestCaseResult] = {}
        self.collection_errors: list[CollectionError] = []
        self.exit_status: int | None = None
        self.interrupted = False

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(
        self,
        session: pytest.Session,
        config: pytest.Config,
        items: list[pytest.Item],
    ) -> None:
        for item in items:
            try:
                relative_file = str(
                    Path(str(item.path)).resolve().relative_to(self.project_root)
                )
            except (ValueError, OSError):
                relative_file = str(item.path)

            location = getattr(item, "location", ("", 0, ""))
            line = int(location[1]) + 1 if len(location) > 1 else 0

            obj = getattr(item, "obj", None)
            docstring = inspect.getdoc(obj) if obj is not None else ""
            docstring = docstring or ""
            analysis = analyze_test_source(obj)

            parameters: dict[str, Any] = {}
            callspec = getattr(item, "callspec", None)
            if callspec is not None:
                parameters = {
                    str(key): json_safe(value)
                    for key, value in callspec.params.items()
                }

            markers = sorted({marker.name for marker in item.iter_markers()})
            class_name = item.cls.__name__ if getattr(item, "cls", None) else ""
            original_name = getattr(item, "originalname", "") or item.name
            guide = guide_for(str(original_name), docstring, analysis)

            self.tests[item.nodeid] = TestCaseResult(
                nodeid=item.nodeid,
                name=item.name,
                original_name=str(original_name),
                file=relative_file,
                line=line,
                class_name=class_name,
                docstring=docstring,
                markers=markers,
                parameters=parameters,
                source_code=analysis["source_code"],
                assertions=analysis["assertions"],
                literal_assignments=analysis["literal_assignments"],
                called_functions=analysis["called_functions"],
                guide=dataclasses.asdict(guide),
            )

    @pytest.hookimpl(tryfirst=True)
    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if report.failed:
            longrepr = safe_text(report.longrepr, MAX_TRACEBACK_CHARS)
            self.collection_errors.append(
                CollectionError(
                    nodeid=report.nodeid,
                    message=longrepr.splitlines()[-1] if longrepr else "Collection error",
                    traceback=longrepr,
                )
            )

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        result = self.tests.get(report.nodeid)
        if result is None:
            fallback = fallback_guide(report.nodeid, "", {})
            result = TestCaseResult(
                nodeid=report.nodeid,
                name=report.nodeid.split("::")[-1],
                original_name=report.nodeid.split("::")[-1],
                file=report.nodeid.split("::")[0],
                line=0,
                guide=dataclasses.asdict(fallback),
            )
            self.tests[report.nodeid] = result

        result.duration_seconds += float(report.duration or 0.0)
        if report.when == "setup":
            result.setup_seconds += float(report.duration or 0.0)
        elif report.when == "call":
            result.call_seconds += float(report.duration or 0.0)
        elif report.when == "teardown":
            result.teardown_seconds += float(report.duration or 0.0)

        result.phases[report.when] = report.outcome

        for attr, field_name in (
            ("capstdout", "stdout"),
            ("capstderr", "stderr"),
            ("caplog", "logs"),
        ):
            value = getattr(report, attr, "") or ""
            if value:
                old = getattr(result, field_name)
                setattr(
                    result,
                    field_name,
                    trim_multiline("\n".join(filter(None, [old, value])), MAX_CAPTURE_CHARS),
                )

        was_xfail = getattr(report, "wasxfail", "") or ""

        if report.when == "setup":
            if report.failed:
                result.status = "error"
                result.reason = "Lỗi ở bước setup"
                result.traceback = safe_text(report.longrepr, MAX_TRACEBACK_CHARS)
            elif report.skipped:
                result.status = "xfailed" if was_xfail else "skipped"
                result.reason = safe_text(was_xfail or report.longrepr, 4_000)

        elif report.when == "call":
            if report.passed and was_xfail:
                result.status = "xpassed"
                result.reason = safe_text(was_xfail, 4_000)
            elif report.passed:
                result.status = "passed"
            elif report.skipped and was_xfail:
                result.status = "xfailed"
                result.reason = safe_text(was_xfail, 4_000)
            elif report.skipped:
                result.status = "skipped"
                result.reason = safe_text(report.longrepr, 4_000)
            elif report.failed:
                result.status = "failed"
                result.reason = (
                    f"XPASS(strict): {safe_text(was_xfail, 3_000)}"
                    if was_xfail
                    else result.reason
                )
                result.traceback = safe_text(report.longrepr, MAX_TRACEBACK_CHARS)

        elif report.when == "teardown" and report.failed:
            result.status = "error"
            result.reason = "Lỗi ở bước teardown"
            result.traceback = safe_text(report.longrepr, MAX_TRACEBACK_CHARS)

    def pytest_keyboard_interrupt(self, excinfo: Any) -> None:
        self.interrupted = True

    def pytest_sessionfinish(
        self,
        session: pytest.Session,
        exitstatus: pytest.ExitCode,
    ) -> None:
        self.exit_status = int(exitstatus)
        self.finished_at = now_iso()
        self.elapsed_seconds = time.perf_counter() - self.start_perf


# =============================================================================
# TỔNG HỢP
# =============================================================================

def build_summary(
    tests: Iterable[TestCaseResult],
    collection_errors: list[CollectionError],
    missing_test_files: list[str] | None = None,
) -> dict[str, Any]:
    items = list(tests)
    counts = Counter(item.status for item in items)
    mandatory = counts["passed"] + counts["failed"] + counts["error"] + counts["xpassed"]
    rate = round(counts["passed"] / mandatory * 100, 2) if mandatory else 0.0

    missing_test_files = list(missing_test_files or [])

    if collection_errors:
        grade = "KHÔNG ĐẠT"
        conclusion = "Có lỗi thu thập testcase nên một phần bộ kiểm thử có thể chưa chạy."
    elif missing_test_files:
        grade = "KHÔNG ĐẠT"
        conclusion = (
            "Có file test tồn tại trong thư mục nhưng pytest không thu thập. "
            "Báo cáo chưa bao phủ đầy đủ toàn bộ bộ kiểm thử."
        )
    elif counts["failed"] == counts["error"] == counts["not_run"] == 0:
        if counts["skipped"] == counts["xfailed"] == counts["xpassed"] == 0:
            grade = "ĐẠT TỐT"
            conclusion = "Tất cả testcase bắt buộc đều chạy thành công."
        else:
            grade = "ĐẠT CÓ ĐIỀU KIỆN"
            conclusion = "Không có test bắt buộc thất bại nhưng còn SKIP/XFAIL/XPASS cần rà soát."
    elif rate >= 90:
        grade = "CẦN KHẮC PHỤC NHẸ"
        conclusion = "Đa số testcase đạt nhưng vẫn còn lỗi phải sửa trước khi phát hành."
    elif rate >= 70:
        grade = "CẦN KHẮC PHỤC"
        conclusion = "Tỷ lệ đạt trung bình; cần xử lý lỗi và chạy lại."
    else:
        grade = "KHÔNG ĐẠT"
        conclusion = "Tỷ lệ đạt thấp hoặc có lỗi nghiêm trọng."

    return {
        "total": len(items),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["error"],
        "skipped": counts["skipped"],
        "xfailed": counts["xfailed"],
        "xpassed": counts["xpassed"],
        "not_run": counts["not_run"],
        "collection_errors": len(collection_errors),
        "missing_test_files": len(missing_test_files),
        "mandatory_executed": mandatory,
        "pass_rate_percent": rate,
        "grade": grade,
        "conclusion": conclusion,
    }


def module_summaries(tests: Iterable[TestCaseResult]) -> list[dict[str, Any]]:
    grouped: dict[str, list[TestCaseResult]] = defaultdict(list)
    for test in tests:
        grouped[test.file].append(test)

    rows = []
    for file_name in sorted(grouped):
        items = grouped[file_name]
        counts = Counter(item.status for item in items)
        rows.append({
            "file": file_name,
            "total": len(items),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "errors": counts["error"],
            "skipped": counts["skipped"],
            "xfailed": counts["xfailed"],
            "xpassed": counts["xpassed"],
            "not_run": counts["not_run"],
            "duration_seconds": round(sum(i.duration_seconds for i in items), 4),
        })
    return rows


def report_payload(
    plugin: DetailedReportPlugin,
    args: argparse.Namespace,
    project_root: Path,
    pytest_args: list[str],
) -> dict[str, Any]:
    tests = sorted(plugin.tests.values(), key=lambda x: (x.file, x.line, x.nodeid))
    tests_path = (project_root / args.tests).resolve()
    discovery = build_discovery_audit(tests_path, project_root, tests)

    return {
        "report_version": REPORT_VERSION,
        "generated_at": now_iso(),
        "environment": {
            "project_root": str(project_root),
            "python_version": sys.version,
            "python_executable": sys.executable,
            "pytest_version": pytest.__version__,
            "platform": platform.platform(),
            "hostname": platform.node(),
            "command": "python " + " ".join(sys.argv),
            "pytest_arguments": pytest_args,
            "git": detect_git_info(project_root),
        },
        "session": {
            "started_at": plugin.started_at,
            "finished_at": plugin.finished_at or now_iso(),
            "elapsed_seconds": round(plugin.elapsed_seconds, 4),
            "exit_status": plugin.exit_status,
            "interrupted": plugin.interrupted,
            "tests_path": str(args.tests),
        },
        "summary": build_summary(
            tests,
            plugin.collection_errors,
            discovery["incomplete_files"],
        ),
        "discovery": discovery,
        "modules": module_summaries(tests),
        "collection_errors": [dataclasses.asdict(e) for e in plugin.collection_errors],
        "tests": [
            {
                **dataclasses.asdict(test),
                "result_explanation": test.explanation,
            }
            for test in tests
        ],
    }


# =============================================================================
# XUẤT BÁO CÁO
# =============================================================================

def fenced(value: str, language: str = "text") -> str:
    fence = "```"
    while fence in value:
        fence += "`"
    return f"{fence}{language}\n{value}\n{fence}"


def write_json_report(payload: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_report(payload: dict[str, Any], path: Path) -> None:
    s = payload["summary"]
    session = payload["session"]
    env = payload["environment"]

    lines = [
        "# BÁO CÁO KIỂM THỬ GIẢI THÍCH CHI TIẾT",
        "",
        f"- **Thời gian:** {payload['generated_at']}",
        f"- **Dự án:** `{env['project_root']}`",
        f"- **Thời gian chạy:** {session['elapsed_seconds']} giây",
        f"- **Đánh giá:** **{s['grade']}**",
        f"- **Kết luận:** {s['conclusion']}",
        "",
        "## Tổng quan",
        "",
        "| Tổng | PASS | FAIL | ERROR | SKIP | XFAIL | XPASS | Tỷ lệ đạt |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        f"| {s['total']} | {s['passed']} | {s['failed']} | {s['errors']} | "
        f"{s['skipped']} | {s['xfailed']} | {s['xpassed']} | {s['pass_rate_percent']}% |",
        "",
        "## Kiểm tra độ đầy đủ của file test",
        "",
        f"- **Số file test tìm thấy trên ổ đĩa:** {payload['discovery']['discovered_file_count']}",
        f"- **Số file được pytest thu thập:** {payload['discovery']['collected_file_count']}",
        f"- **Số file bị thiếu khỏi báo cáo:** {payload['discovery']['missing_file_count']}",
        "",
        "| File | Hàm test khai báo | Testcase pytest thu thập | Trạng thái | Ghi chú |",
        "|---|---:|---:|---|---|",
    ]

    for item in payload["discovery"]["files"]:
        escaped_note = str(item["note"]).replace("|", "\\|")
        lines.append(
            f"| `{item['file']}` | {item['declared_test_functions']} | "
            f"{item['collected_testcases']} | {item['status']} | "
            f"{escaped_note} |"
        )

    lines.extend([
        "",
        "## Giải thích từng testcase",
        "",
    ])

    for idx, test in enumerate(payload["tests"], 1):
        guide = test["guide"]
        lines.extend([
            f"### {idx}. {status_icon(test['status'])} `{test['nodeid']}`",
            "",
            f"- **Tên dễ hiểu:** {guide['title']}",
            f"- **Trạng thái:** {status_label(test['status'])}",
            f"- **Tình huống kiểm tra:** {guide['scenario']}",
            f"- **Ví dụ cụ thể:** {guide['example']}",
            f"- **Kết quả mong đợi:** {guide['expected']}",
            f"- **Kết quả lần chạy:** {test['result_explanation']}",
            f"- **Ý nghĩa nghiệp vụ:** {guide['business_meaning']}",
            f"- **Nếu test thất bại:** {guide['failure_impact']}",
            f"- **Vị trí:** `{test['file']}:{test['line']}`",
            f"- **Thời gian:** {test['duration_seconds']:.6f} giây",
        ])

        if test["parameters"]:
            lines.extend([
                "",
                "**Tham số thực tế của lần test này:**",
                "",
                fenced(json.dumps(test["parameters"], ensure_ascii=False, indent=2), "json"),
            ])
        if test["literal_assignments"]:
            lines.extend([
                "",
                "**Dữ liệu ví dụ lấy trực tiếp từ code test:**",
                "",
                fenced(json.dumps(test["literal_assignments"], ensure_ascii=False, indent=2), "json"),
            ])
        if test["assertions"]:
            lines.extend([
                "",
                "**Các điều kiện kỹ thuật phải đúng:**",
                "",
                *[f"- `{a}`" for a in test["assertions"]],
            ])
        if test["traceback"]:
            lines.extend(["", "**Chi tiết lỗi:**", "", fenced(test["traceback"])])
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def html_status_class(status: str) -> str:
    return {
        "passed": "passed",
        "failed": "failed",
        "error": "error",
        "skipped": "skipped",
        "xfailed": "xfailed",
        "xpassed": "xpassed",
        "not_run": "not-run",
    }.get(status, "not-run")


def esc(value: Any) -> str:
    return html.escape(str(value))


def html_pre(value: Any) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, indent=2)
    return f"<pre>{esc(value)}</pre>"


def write_html_report(payload: dict[str, Any], path: Path) -> None:
    s = payload["summary"]
    session = payload["session"]
    env = payload["environment"]

    module_rows = "".join(
        f"""
        <tr>
          <td><code>{esc(m['file'])}</code></td>
          <td>{m['total']}</td><td class="ok">{m['passed']}</td>
          <td class="bad">{m['failed']}</td><td class="err">{m['errors']}</td>
          <td>{m['skipped']}</td><td>{m['xfailed']}</td><td>{m['xpassed']}</td>
          <td>{m['duration_seconds']:.4f}s</td>
        </tr>
        """
        for m in payload["modules"]
    )

    discovery_rows = "".join(
        f"""
        <tr class="discovery-{esc(item['status'])}">
          <td><code>{esc(item['file'])}</code></td>
          <td>{item['declared_test_functions']}</td>
          <td>{item['collected_testcases']}</td>
          <td><strong>{esc(item['status']).upper()}</strong></td>
          <td>{esc(item['note'])}</td>
        </tr>
        """
        for item in payload["discovery"]["files"]
    )

    missing_banner = ""
    if payload["discovery"]["incomplete_files"]:
        missing_list = "".join(
            f"<li><code>{esc(file_name)}</code></li>"
            for file_name in payload["discovery"]["incomplete_files"]
        )
        missing_banner = (
            "<div class='missing-banner'><strong>Phát hiện file test bị thiếu "
            "khỏi báo cáo:</strong><ul>" + missing_list + "</ul>"
            "Báo cáo được đánh giá KHÔNG ĐẠT cho tới khi các file này được "
            "pytest thu thập.</div>"
        )
    else:
        missing_banner = (
            "<div class='complete-banner'><strong>Đã kiểm tra đầy đủ:</strong> "
            "mọi file có hàm test_* đều được pytest thu thập.</div>"
        )

    cards: list[str] = []
    for idx, test in enumerate(payload["tests"], 1):
        guide = test["guide"]
        status_class = html_status_class(test["status"])

        params = (
            "<details><summary>Tham số thực tế của lần test</summary>"
            + html_pre(test["parameters"]) + "</details>"
            if test["parameters"] else ""
        )
        literals = (
            "<details><summary>Dữ liệu ví dụ lấy trực tiếp từ code</summary>"
            + html_pre(test["literal_assignments"]) + "</details>"
            if test["literal_assignments"] else ""
        )
        assertions = (
            "<details><summary>Các điều kiện kỹ thuật phải đúng</summary><ul>"
            + "".join(f"<li><code>{esc(a)}</code></li>" for a in test["assertions"])
            + "</ul></details>"
            if test["assertions"] else ""
        )
        source = (
            "<details><summary>Xem source của testcase</summary>"
            + html_pre(test["source_code"]) + "</details>"
            if test["source_code"] else ""
        )
        diagnostics = ""
        for title, key in (
            ("Chi tiết lỗi/traceback", "traceback"),
            ("Standard output", "stdout"),
            ("Standard error", "stderr"),
            ("Captured logs", "logs"),
        ):
            if test[key]:
                diagnostics += (
                    f"<details class='diagnostic'><summary>{esc(title)}</summary>"
                    f"{html_pre(test[key])}</details>"
                )

        cards.append(f"""
        <article class="test-card {status_class}" data-status="{status_class}">
          <div class="test-head">
            <div>
              <span class="index">#{idx}</span>
              <span class="badge {status_class}">
                {esc(status_icon(test['status']))} {esc(status_label(test['status']))}
              </span>
              <h3>{esc(guide['title'])}</h3>
              <div class="nodeid">{esc(test['nodeid'])}</div>
            </div>
            <div class="duration">{test['duration_seconds']:.6f}s</div>
          </div>

          <div class="explain-grid">
            <div class="explain-box">
              <h4>1. Tình huống kiểm tra</h4>
              <p>{esc(guide['scenario'])}</p>
            </div>
            <div class="explain-box example">
              <h4>2. Ví dụ cụ thể</h4>
              <p>{esc(guide['example'])}</p>
            </div>
            <div class="explain-box expected">
              <h4>3. Hệ thống phải làm gì?</h4>
              <p>{esc(guide['expected'])}</p>
            </div>
            <div class="explain-box result {status_class}">
              <h4>4. Kết quả lần chạy này</h4>
              <p>{esc(test['result_explanation'])}</p>
            </div>
            <div class="explain-box meaning">
              <h4>5. Ý nghĩa với người dùng</h4>
              <p>{esc(guide['business_meaning'])}</p>
            </div>
            <div class="explain-box risk">
              <h4>6. Nếu testcase thất bại</h4>
              <p>{esc(guide['failure_impact'])}</p>
            </div>
          </div>

          <div class="meta">
            <span><strong>Vị trí code:</strong> <code>{esc(test['file'])}:{test['line']}</code></span>
            <span><strong>Thời gian:</strong> {test['duration_seconds']:.6f} giây</span>
          </div>

          <div class="technical">
            {params}{literals}{assertions}{source}{diagnostics}
          </div>
        </article>
        """)

    collection_html = ""
    if payload["collection_errors"]:
        collection_html = "<section><h2>Lỗi thu thập testcase</h2>" + "".join(
            f"<div class='collection-error'><h3>{esc(e['nodeid'])}</h3>"
            f"<p>{esc(e['message'])}</p>{html_pre(e['traceback'])}</div>"
            for e in payload["collection_errors"]
        ) + "</section>"

    report = f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo cáo kiểm thử chi tiết</title>
<style>
:root {{
  --bg:#f3f5f7;--card:#fff;--text:#172033;--muted:#667085;--line:#dde3ea;
  --green:#137a3d;--green-bg:#eaf8ef;--red:#c62828;--red-bg:#ffeded;
  --purple:#7b1fa2;--purple-bg:#f7eafa;--amber:#946200;--amber-bg:#fff5d6;
  --blue:#175cd3;--blue-bg:#eef4ff;
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,"Segoe UI",Arial,sans-serif;line-height:1.6}}
.container{{width:min(1480px,96%);margin:24px auto 60px}}
.hero{{padding:28px 32px;border-radius:18px;color:#fff;background:linear-gradient(135deg,#172033,#344054);box-shadow:0 12px 28px rgba(0,0,0,.13)}}
.hero h1{{margin:0 0 8px;font-size:29px}} .hero p{{margin:4px 0;color:#e4e7ec}}
.grade{{margin-top:14px;padding:10px 14px;border-radius:10px;background:rgba(255,255,255,.12);font-weight:800}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:11px;margin:18px 0}}
.stat{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 4px 12px rgba(0,0,0,.035)}}
.stat b{{display:block;font-size:25px}} .stat span{{font-size:13px;color:var(--muted)}}
section{{background:#fff;border:1px solid var(--line);border-radius:16px;padding:20px;margin-top:18px}}
h2{{margin:0 0 15px}} table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{padding:10px;border-bottom:1px solid var(--line);text-align:left}} th{{background:#f8fafc}}
.ok{{color:var(--green);font-weight:800}} .bad{{color:var(--red);font-weight:800}} .err{{color:var(--purple);font-weight:800}}
.filters{{display:flex;flex-wrap:wrap;gap:7px;margin-bottom:12px}}
button{{border:1px solid var(--line);background:#fff;padding:7px 11px;border-radius:999px;cursor:pointer;font-weight:700}}
input{{width:100%;padding:11px 13px;border:1px solid var(--line);border-radius:10px;margin-bottom:12px}}
.test-card{{background:#fff;border:1px solid var(--line);border-left:7px solid #98a2b3;border-radius:15px;padding:18px;margin:13px 0}}
.test-card.passed{{border-left-color:var(--green)}} .test-card.failed{{border-left-color:var(--red)}}
.test-card.error{{border-left-color:var(--purple)}} .test-card.xfailed{{border-left-color:var(--amber)}}
.test-head{{display:flex;justify-content:space-between;gap:15px;align-items:flex-start}}
.test-head h3{{margin:8px 0 2px;font-size:18px}} .nodeid{{font-family:monospace;font-size:12px;color:var(--muted);overflow-wrap:anywhere}}
.index{{color:var(--muted);margin-right:7px}} .duration{{font-family:monospace;color:var(--muted);white-space:nowrap}}
.badge{{display:inline-block;padding:4px 9px;border-radius:999px;font-size:12px;font-weight:800;background:#eef2f6}}
.badge.passed{{color:var(--green);background:var(--green-bg)}} .badge.failed{{color:var(--red);background:var(--red-bg)}}
.badge.error{{color:var(--purple);background:var(--purple-bg)}} .badge.xfailed{{color:var(--amber);background:var(--amber-bg)}}
.explain-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:16px}}
.explain-box{{border:1px solid var(--line);border-radius:11px;padding:12px 14px;background:#fafbfc}}
.explain-box h4{{margin:0 0 5px;font-size:14px}} .explain-box p{{margin:0}}
.explain-box.example{{background:#fff9eb}} .explain-box.expected{{background:var(--blue-bg)}}
.explain-box.result.passed{{background:var(--green-bg)}} .explain-box.result.failed{{background:var(--red-bg)}}
.explain-box.result.error{{background:var(--purple-bg)}} .explain-box.meaning{{background:#f0fdf9}}
.explain-box.risk{{background:#fff3f2}}
.meta{{display:flex;flex-wrap:wrap;gap:18px;margin-top:13px;color:var(--muted);font-size:13px}}
.technical{{margin-top:10px}} details{{border-top:1px dashed var(--line);padding-top:9px;margin-top:9px}}
summary{{cursor:pointer;font-weight:750}} code,pre{{font-family:"Cascadia Code",Consolas,monospace}}
pre{{white-space:pre-wrap;word-break:break-word;background:#101828;color:#e4e7ec;border-radius:10px;padding:13px;max-height:520px;overflow:auto}}
.hidden{{display:none!important}} .footer{{text-align:center;color:var(--muted);margin-top:26px}}
.collection-error{{border-left:5px solid var(--purple);padding-left:14px}}
.missing-banner{{background:var(--red-bg);border:1px solid #f5aaaa;color:#8a1c1c;padding:13px 15px;border-radius:10px;margin-bottom:14px}}
.complete-banner{{background:var(--green-bg);border:1px solid #9bd7af;color:#105c30;padding:13px 15px;border-radius:10px;margin-bottom:14px}}
.discovery-missing td,.discovery-parse_error td{{background:#fff1f1}}
.discovery-collected td{{background:#fbfffc}}
@media(max-width:800px){{.explain-grid{{grid-template-columns:1fr}}.test-head{{flex-direction:column}}section{{overflow-x:auto}}}}
</style>
</head>
<body>
<div class="container">
<header class="hero">
  <h1>Báo cáo kiểm thử có giải thích nghiệp vụ</h1>
  <p>Thời gian tạo: {esc(payload['generated_at'])}</p>
  <p>Dự án: {esc(env['project_root'])}</p>
  <p>Thời gian chạy: {session['elapsed_seconds']} giây · Pytest {esc(env['pytest_version'])}</p>
  <div class="grade">{esc(s['grade'])} — {esc(s['conclusion'])}</div>
</header>

<div class="stats">
  <div class="stat"><b>{s['total']}</b><span>Tổng testcase</span></div>
  <div class="stat"><b class="ok">{s['passed']}</b><span>PASS</span></div>
  <div class="stat"><b class="bad">{s['failed']}</b><span>FAIL</span></div>
  <div class="stat"><b class="err">{s['errors']}</b><span>ERROR</span></div>
  <div class="stat"><b>{s['skipped']}</b><span>SKIPPED</span></div>
  <div class="stat"><b>{s['xfailed']}</b><span>XFAIL</span></div>
  <div class="stat"><b>{s['pass_rate_percent']}%</b><span>Tỷ lệ đạt</span></div>
</div>

<section>
<h2>Kết quả theo file test</h2>
<table>
<thead><tr><th>File</th><th>Tổng</th><th>PASS</th><th>FAIL</th><th>ERROR</th><th>SKIP</th><th>XFAIL</th><th>XPASS</th><th>Thời gian</th></tr></thead>
<tbody>{module_rows}</tbody>
</table>
</section>

<section>
<h2>Kiểm tra độ đầy đủ của bộ test</h2>
<p>Phần này đối chiếu trực tiếp các file <code>test_*.py</code> đang có trong thư mục với những testcase pytest thật sự thu thập.</p>
{missing_banner}
<div class="stats">
  <div class="stat"><b>{payload['discovery']['discovered_file_count']}</b><span>File test tìm thấy</span></div>
  <div class="stat"><b class="ok">{payload['discovery']['collected_file_count']}</b><span>File đã thu thập</span></div>
  <div class="stat"><b class="bad">{payload['discovery']['incomplete_file_count']}</b><span>File chưa được kiểm thử</span></div>
</div>
<table>
<thead><tr><th>File</th><th>Hàm test khai báo</th><th>Testcase thu thập</th><th>Trạng thái</th><th>Giải thích</th></tr></thead>
<tbody>{discovery_rows}</tbody>
</table>
</section>

{collection_html}

<section>
<h2>Giải thích chi tiết từng testcase</h2>
<p>Mỗi testcase được giải thích bằng tình huống thực tế, ví dụ, kết quả mong đợi, ý nghĩa nghiệp vụ và rủi ro nếu thất bại.</p>
<div class="filters">
<button onclick="filterTests('all')">Tất cả</button>
<button onclick="filterTests('passed')">PASS</button>
<button onclick="filterTests('failed')">FAIL</button>
<button onclick="filterTests('error')">ERROR</button>
<button onclick="filterTests('skipped')">SKIPPED</button>
<button onclick="filterTests('xfailed')">XFAIL</button>
</div>
<input id="search" type="search" placeholder="Tìm theo tên, ví dụ hoặc ý nghĩa..." oninput="applyFilters()">
<div id="test-list">{''.join(cards)}</div>
</section>

<div class="footer">Sinh bởi run_all_tests.py v{REPORT_VERSION}</div>
</div>
<script>
let activeFilter='all';
function filterTests(status){{activeFilter=status;applyFilters();}}
function applyFilters(){{
 const q=document.getElementById('search').value.toLowerCase();
 document.querySelectorAll('.test-card').forEach(card=>{{
   const okStatus=activeFilter==='all'||card.dataset.status===activeFilter;
   const okText=card.innerText.toLowerCase().includes(q);
   card.classList.toggle('hidden',!(okStatus&&okText));
 }});
}}
</script>
</body>
</html>
"""
    path.write_text(report, encoding="utf-8")


# =============================================================================
# CHẠY PYTEST
# =============================================================================

class TeeStream(io.TextIOBase):
    def __init__(self, primary: Any, log_file: io.TextIOBase) -> None:
        self.primary = primary
        self.log_file = log_file

    def write(self, value: str) -> int:
        self.primary.write(value)
        self.log_file.write(value)
        self.log_file.flush()
        return len(value)

    def flush(self) -> None:
        self.primary.flush()
        self.log_file.flush()

    def isatty(self) -> bool:
        try:
            return bool(self.primary.isatty())
        except Exception:
            return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chạy toàn bộ tests và tạo báo cáo giải thích dễ hiểu.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tests", default="tests")
    parser.add_argument("--output", default="reports/test_reports")
    parser.add_argument("-k", "--keyword", default="")
    parser.add_argument("-m", "--marker", default="")
    parser.add_argument("--failfast", action="store_true")
    parser.add_argument("--maxfail", type=int, default=0)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--cov-target", action="append", default=[])
    parser.add_argument("--no-junit", action="store_true")
    parser.add_argument("pytest_extra", nargs=argparse.REMAINDER)
    return parser.parse_args()


def build_pytest_args(
    args: argparse.Namespace,
    tests_path: Path,
    run_dir: Path,
) -> list[str]:
    result = [str(tests_path), "-ra", "--tb=short", "-q" if args.quiet else "-vv"]

    if args.keyword:
        result += ["-k", args.keyword]
    if args.marker:
        result += ["-m", args.marker]
    if args.failfast:
        result.append("-x")
    if args.maxfail > 0:
        result.append(f"--maxfail={args.maxfail}")
    if not args.no_junit:
        result.append(f"--junitxml={run_dir / 'junit.xml'}")

    if args.coverage:
        if importlib.util.find_spec("pytest_cov") is None:
            print("Chưa cài pytest-cov; bỏ qua coverage.", file=sys.stderr)
        else:
            for target in (args.cov_target or ["core"]):
                result.append(f"--cov={target}")
            result += [
                "--cov-report=term-missing",
                f"--cov-report=html:{run_dir / 'coverage_html'}",
                f"--cov-report=xml:{run_dir / 'coverage.xml'}",
            ]

    extra = list(args.pytest_extra)
    if extra and extra[0] == "--":
        extra = extra[1:]
    result.extend(extra)
    return result


def main() -> int:
    args = parse_args()
    project_root = Path.cwd().resolve()
    tests_path = (project_root / args.tests).resolve()

    if not tests_path.exists():
        print(f"Không tìm thấy: {tests_path}", file=sys.stderr)
        return 4

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_root = (project_root / args.output).resolve()
    run_dir = output_root / f"test_report_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (output_root / "LATEST.txt").write_text(str(run_dir), encoding="utf-8")

    plugin = DetailedReportPlugin(project_root)
    pytest_args = build_pytest_args(args, tests_path, run_dir)
    console_path = run_dir / "pytest_console.txt"

    print("=" * 80)
    print("CHẠY TOÀN BỘ TESTCASE VÀ TẠO BÁO CÁO GIẢI THÍCH CHI TIẾT")
    print(f"Tests  : {tests_path}")
    print(f"Report : {run_dir}")
    print("=" * 80)

    exit_code = 3
    with console_path.open("w", encoding="utf-8") as console_file:
        out = TeeStream(sys.stdout, console_file)
        err = TeeStream(sys.stderr, console_file)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                exit_code = int(pytest.main(pytest_args, plugins=[plugin]))
        except KeyboardInterrupt:
            plugin.interrupted = True
            exit_code = 2
        except Exception:
            plugin.collection_errors.append(CollectionError(
                nodeid="run_all_tests.py",
                message="Lỗi ngoài dự kiến khi chạy pytest",
                traceback=traceback.format_exc(),
            ))
            exit_code = 3

    if plugin.exit_status is None:
        plugin.exit_status = exit_code
    if not plugin.finished_at:
        plugin.finished_at = now_iso()
    if plugin.elapsed_seconds <= 0:
        plugin.elapsed_seconds = time.perf_counter() - plugin.start_perf

    payload = report_payload(plugin, args, project_root, pytest_args)
    write_json_report(payload, run_dir / "report.json")
    write_markdown_report(payload, run_dir / "report.md")
    write_html_report(payload, run_dir / "report.html")

    s = payload["summary"]
    print("\n" + "=" * 80)
    print(f"Tổng: {s['total']} | PASS: {s['passed']} | FAIL: {s['failed']} | ERROR: {s['errors']}")
    print(
        "File test: "
        f"tìm thấy={payload['discovery']['discovered_file_count']} | "
        f"đã thu thập={payload['discovery']['collected_file_count']} | "
        f"chưa kiểm thử={payload['discovery']['incomplete_file_count']}"
    )
    if payload["discovery"]["incomplete_files"]:
        print("Các file chưa được kiểm thử đầy đủ:")
        for file_name in payload["discovery"]["incomplete_files"]:
            print(f"  - {file_name}")
    print(f"Đánh giá: {s['grade']} — {s['conclusion']}")
    print(f"HTML: {run_dir / 'report.html'}")
    print(f"MD  : {run_dir / 'report.md'}")
    print(f"JSON: {run_dir / 'report.json'}")
    print("=" * 80)

    if payload["discovery"]["incomplete_files"] and exit_code == 0:
        return 5

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
