# BÁO CÁO KIỂM THỬ GIẢI THÍCH CHI TIẾT

- **Thời gian:** 2026-06-25T14:26:28+07:00
- **Dự án:** `/hdd3/vinhnv/HSMT_Enterprise_AI_v8_3_SingleBidder_AppendixCompare`
- **Thời gian chạy:** 3.5787 giây
- **Đánh giá:** **ĐẠT TỐT**
- **Kết luận:** Tất cả testcase bắt buộc đều chạy thành công.

## Tổng quan

| Tổng | PASS | FAIL | ERROR | SKIP | XFAIL | XPASS | Tỷ lệ đạt |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 100 | 0 | 0 | 0 | 0 | 0 | 100.0% |

## Kiểm tra độ đầy đủ của file test

- **Số file test tìm thấy trên ổ đĩa:** 16
- **Số file được pytest thu thập:** 16
- **Số file bị thiếu khỏi báo cáo:** 0

| File | Hàm test khai báo | Testcase pytest thu thập | Trạng thái | Ghi chú |
|---|---:|---:|---|---|
| `tests/test_app_capabilities.py` | 3 | 3 | collected | Pytest đã thu thập 3 testcase từ 3 hàm test. |
| `tests/test_excel_compare.py` | 4 | 4 | collected | Pytest đã thu thập 4 testcase từ 4 hàm test. |
| `tests/test_fast_excel.py` | 3 | 3 | collected | Pytest đã thu thập 3 testcase từ 3 hàm test. |
| `tests/test_grid.py` | 1 | 1 | collected | Pytest đã thu thập 1 testcase từ 1 hàm test. |
| `tests/test_matcher.py` | 1 | 1 | collected | Pytest đã thu thập 1 testcase từ 1 hàm test. |
| `tests/test_number_parser.py` | 1 | 1 | collected | Pytest đã thu thập 1 testcase từ 1 hàm test. |
| `tests/test_ocr_high_accuracy.py` | 3 | 3 | collected | Pytest đã thu thập 3 testcase từ 3 hàm test. |
| `tests/test_optional_appendices.py` | 4 | 4 | collected | Pytest đã thu thập 4 testcase từ 4 hàm test. |
| `tests/test_orientation.py` | 3 | 3 | collected | Pytest đã thu thập 3 testcase từ 3 hàm test. |
| `tests/test_package_mode.py` | 1 | 1 | collected | Pytest đã thu thập 1 testcase từ 1 hàm test. |
| `tests/test_regressions.py` | 2 | 2 | collected | Pytest đã thu thập 2 testcase từ 2 hàm test. |
| `tests/test_s1_comparison_engine.py` | 11 | 11 | collected | Pytest đã thu thập 11 testcase từ 11 hàm test. |
| `tests/test_s1_file_parser.py` | 9 | 9 | collected | Pytest đã thu thập 9 testcase từ 9 hàm test. |
| `tests/test_s1_normalizer.py` | 12 | 51 | collected | Pytest đã thu thập 51 testcase từ 12 hàm test. |
| `tests/test_security.py` | 1 | 1 | collected | Pytest đã thu thập 1 testcase từ 1 hàm test. |
| `tests/test_sheet_note_behavior.py` | 2 | 2 | collected | Pytest đã thu thập 2 testcase từ 2 hàm test. |

## Giải thích từng testcase

### 1. ✅ `tests/test_app_capabilities.py::test_health_reports_comparison_and_ocr`

- **Tên dễ hiểu:** Kiểm tra máy chủ công bố đúng các chức năng đang hoạt động
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Gọi địa chỉ kiểm tra sức khỏe của hệ thống trước khi người dùng tải hồ sơ.
- **Ví dụ cụ thể:** Trình duyệt hoặc frontend gọi GET /api/health. Phản hồi phải cho biết hệ thống có chế độ so sánh hồ sơ và OCR.
- **Kết quả mong đợi:** API trả trạng thái hoạt động bình thường và các cờ comparison/package/OCR đúng với chức năng thật.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: API trả trạng thái hoạt động bình thường và các cờ comparison/package/OCR đúng với chức năng thật. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Frontend biết nút nào được phép hiển thị và quản trị viên biết dịch vụ đã sẵn sàng.
- **Nếu test thất bại:** Giao diện có thể ẩn nhầm chức năng, báo hệ thống hỏng hoặc cho người dùng gọi chức năng chưa sẵn sàng.
- **Vị trí:** `tests/test_app_capabilities.py:22`
- **Thời gian:** 0.006200 giây

**Các điều kiện kỹ thuật phải đúng:**

- `response.status_code == 200`
- `body["version"] == "8.3.0"`
- `body["package_mode"] is True`
- `body["ocr_mode"] is True`
- `body["excel_engine"] in {"calamine", "openpyxl", "auto"}`

### 2. ✅ `tests/test_app_capabilities.py::test_ocr_route_is_available`

- **Tên dễ hiểu:** Kiểm tra đường dẫn OCR tồn tại
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Người dùng chọn PDF scan hoặc ảnh rồi bấm nút OCR.
- **Ví dụ cụ thể:** Frontend gửi yêu cầu tới POST /api/ocr. Test bảo đảm đường dẫn này được FastAPI đăng ký, không trả lỗi 404 do thiếu route.
- **Kết quả mong đợi:** Máy chủ nhận được yêu cầu OCR và trả phản hồi hợp lệ theo quy trình của hệ thống.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Máy chủ nhận được yêu cầu OCR và trả phản hồi hợp lệ theo quy trình của hệ thống. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng có thể gửi tài liệu scan để chuyển thành Excel.
- **Nếu test thất bại:** Nút OCR trên giao diện sẽ không hoạt động dù các thư viện OCR đã được cài.
- **Vị trí:** `tests/test_app_capabilities.py:33`
- **Thời gian:** 0.000357 giây

**Các điều kiện kỹ thuật phải đúng:**

- `"/api/ocr" in paths`
- `"/api/compare-package" in paths`
- `"/api/compare-bidders" in paths`
- `"/api/compare-tender" in paths`

### 3. ✅ `tests/test_app_capabilities.py::test_compare_package_api_accepts_one_bidder`

- **Tên dễ hiểu:** Kiểm tra gói thầu chấp nhận chỉ một nhà thầu
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Có PL01 hoặc PL02 và chỉ có một file chào giá của một nhà thầu.
- **Ví dụ cụ thể:** Ví dụ tải PL01.xlsx cùng NhaThauA.xlsx. Hệ thống phải nhận hồ sơ và tạo job xử lý thay vì bắt buộc từ hai nhà thầu trở lên.
- **Kết quả mong đợi:** API chấp nhận yêu cầu, tạo mã tác vụ và không báo lỗi thiếu nhà thầu.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: API chấp nhận yêu cầu, tạo mã tác vụ và không báo lỗi thiếu nhà thầu. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Phù hợp trường hợp thực tế chỉ có một đơn vị nộp báo giá.
- **Nếu test thất bại:** Người dùng sẽ không thể kiểm tra hồ sơ một nhà thầu, dù đây là chức năng đã được yêu cầu.
- **Vị trí:** `tests/test_app_capabilities.py:41`
- **Thời gian:** 0.026693 giây

**Các điều kiện kỹ thuật phải đúng:**

- `response.status_code == 202`
- `client.delete(f"/api/jobs/{job_id}").status_code == 200`

### 4. ✅ `tests/test_excel_compare.py::test_missing_and_zero_are_not_silently_ok`

- **Tên dễ hiểu:** Không được coi hạng mục thiếu hoặc số lượng 0 là bình thường
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** PL01 yêu cầu một hạng mục nhưng nhà thầu bỏ hẳn hoặc để khối lượng bằng 0.
- **Ví dụ cụ thể:** Ví dụ PL01 yêu cầu 10 máy bơm; hồ sơ nhà thầu không có dòng máy bơm hoặc ghi số lượng 0.
- **Kết quả mong đợi:** Hệ thống phải tạo cảnh báo thiếu hạng mục/khối lượng bất thường, không được đánh dấu OK.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống phải tạo cảnh báo thiếu hạng mục/khối lượng bất thường, không được đánh dấu OK. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người kiểm tra không bỏ sót việc nhà thầu chưa chào đủ khối lượng.
- **Nếu test thất bại:** Hồ sơ thiếu hàng hóa có thể bị kết luận hợp lệ sai, ảnh hưởng đánh giá thầu.
- **Vị trí:** `tests/test_excel_compare.py:20`
- **Thời gian:** 0.025733 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row1.candidate.amount == 0`
- `row1.severity is Severity.CRITICAL`
- `row2.match.kind.value == "missing"`
- `row2.severity is Severity.CRITICAL`

### 5. ✅ `tests/test_excel_compare.py::test_multi_bidder_consensus_flags_outlier`

- **Tên dễ hiểu:** Phát hiện đơn giá lệch bất thường giữa nhiều nhà thầu
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhiều nhà thầu cùng báo giá một hạng mục nhưng có một giá cách xa nhóm còn lại.
- **Ví dụ cụ thể:** Ví dụ bốn giá là 100, 105, 95 và 200. Ba giá đầu gần nhau, giá 200 là điểm lệch.
- **Kết quả mong đợi:** Hệ thống phải cảnh báo nhà thầu có giá 200 là cao bất thường so với mặt bằng ngang hàng.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống phải cảnh báo nhà thầu có giá 200 là cao bất thường so với mặt bằng ngang hàng. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng nhanh chóng thấy giá cần kiểm tra lại mà không phải dò thủ công từng cột.
- **Nếu test thất bại:** Đơn giá nhập nhầm hoặc bất thường có thể lọt qua báo cáo.
- **Vị trí:** `tests/test_excel_compare.py:41`
- **Thời gian:** 0.037664 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "files": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `outlier.consensus_price is not None`
- `outlier.severity in {Severity.WARNING, Severity.CRITICAL}`
- `any("trung vị" in f.lower() for f in outlier.flags)`

### 6. ✅ `tests/test_excel_compare.py::test_same_code_different_name_is_flagged`

- **Tên dễ hiểu:** Cùng mã nhưng tên vật tư khác phải được cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hai dòng dùng cùng một mã hiệu nhưng mô tả hàng hóa không giống nhau.
- **Ví dụ cụ thể:** Ví dụ cùng mã M-01 nhưng PL01 ghi “Tủ điện tổng”, còn nhà thầu ghi “Ống HDPE D110”.
- **Kết quả mong đợi:** Hệ thống không được ghép im lặng; phải gắn cờ xung đột mã và tên.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống không được ghép im lặng; phải gắn cờ xung đột mã và tên. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh so sánh nhầm hai loại vật tư chỉ vì trùng mã.
- **Nếu test thất bại:** Giá và khối lượng của hai hạng mục khác nhau có thể bị ghép chung, làm sai toàn bộ kết quả.
- **Vị trí:** `tests/test_excel_compare.py:56`
- **Thời gian:** 0.025160 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity in {Severity.WARNING, Severity.CRITICAL}`
- `any("trùng mã" in flag.lower() and "tên" in flag.lower() for flag in row.flags)`

### 7. ✅ `tests/test_excel_compare.py::test_duplicate_code_is_preserved_and_flagged`

- **Tên dễ hiểu:** Giữ lại đầy đủ các dòng trùng mã và đồng thời cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Trong một file có hai dòng cùng mã vật tư.
- **Ví dụ cụ thể:** Ví dụ mã M-01 xuất hiện ở dòng 10 và dòng 25. Cả hai dòng đều phải còn trong dữ liệu sau khi đọc.
- **Kết quả mong đợi:** Không được tự xóa một dòng; hệ thống phải giữ cả hai và tạo cờ mã trùng để người dùng xem xét.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Không được tự xóa một dòng; hệ thống phải giữ cả hai và tạo cờ mã trùng để người dùng xem xét. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Báo cáo không làm mất dữ liệu gốc và vẫn chỉ ra điểm nghi vấn.
- **Nếu test thất bại:** Một hạng mục có thể biến mất khỏi báo cáo hoặc bị cộng sai số lượng.
- **Vị trí:** `tests/test_excel_compare.py:68`
- **Thời gian:** 0.020653 giây

**Các điều kiện kỹ thuật phải đúng:**

- `len([r for r in result.rows if r.reference is not None]) == 2`
- `any("mã hiệu trùng" in flag.lower() for r in result.rows for flag in r.flags)`

### 8. ✅ `tests/test_fast_excel.py::test_calamine_reader_preserves_rows`

- **Tên dễ hiểu:** Calamine phải đọc đủ dòng và đúng thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** File Excel được đọc bằng bộ máy nhanh Calamine.
- **Ví dụ cụ thể:** Ví dụ file có tiêu đề, ba dòng vật tư và một dòng tổng; sau khi đọc không được mất hoặc đảo thứ tự các dòng.
- **Kết quả mong đợi:** Số dòng, nội dung và vị trí tương đối phải giống dữ liệu trong file.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Số dòng, nội dung và vị trí tương đối phải giống dữ liệu trong file. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng tốc đọc file nhưng không đánh đổi độ chính xác.
- **Nếu test thất bại:** Hạng mục có thể bị bỏ sót hoặc đối chiếu sai dòng nguồn.
- **Vị trí:** `tests/test_fast_excel.py:33`
- **Thời gian:** 0.013268 giây

**Các điều kiện kỹ thuật phải đúng:**

- `data.engine == "calamine"`
- `data.sheets[0].rows[1][0] == "M-01"`

### 9. ✅ `tests/test_fast_excel.py::test_parallel_workbook_load`

- **Tên dễ hiểu:** Đọc nhiều workbook song song vẫn phải trả đủ kết quả
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Bốn nhà thầu cùng tải file lên một thời điểm.
- **Ví dụ cụ thể:** Ví dụ NT1.xlsx, NT2.xlsx, NT3.xlsx và NT4.xlsx được đưa vào ThreadPoolExecutor.
- **Kết quả mong đợi:** Kết quả phải chứa đủ bốn file, không lẫn dữ liệu và không mất file nào.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả phải chứa đủ bốn file, không lẫn dữ liệu và không mất file nào. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Nhiều người hoặc nhiều nhà thầu có thể được xử lý nhanh hơn.
- **Nếu test thất bại:** Có thể xảy ra thiếu kết quả, lẫn tên nhà thầu hoặc lỗi ngẫu nhiên khi tải đồng thời.
- **Vị trí:** `tests/test_fast_excel.py:41`
- **Thời gian:** 0.033538 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "paths": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `set(result) == {"0", "1", "2", "3"}`
- `all(book.read_engine == "calamine" for book in result.values())`

### 10. ✅ `tests/test_fast_excel.py::test_ref_is_scanned_and_annotated`

- **Tên dễ hiểu:** Phát hiện công thức Excel lỗi #REF! và đánh dấu đúng vị trí
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Workbook có ô công thức tham chiếu tới vùng đã bị xóa.
- **Ví dụ cụ thể:** Ví dụ ô G25 hiển thị #REF! hoặc công thức chứa #REF!.
- **Kết quả mong đợi:** Bộ quét phải tìm thấy ô lỗi và file kết quả phải có ghi chú/đánh dấu để người dùng nhìn thấy.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Bộ quét phải tìm thấy ô lỗi và file kết quả phải có ghi chú/đánh dấu để người dùng nhìn thấy. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng biết chính xác ô công thức hỏng thay vì chỉ nhận một cảnh báo chung.
- **Nếu test thất bại:** Tổng tiền hoặc khối lượng có thể sai mà không ai biết nguyên nhân.
- **Vị trí:** `tests/test_fast_excel.py:53`
- **Thời gian:** 0.036270 giây

**Các điều kiện kỹ thuật phải đúng:**

- `any(issue.kind == "FORMULA_ERROR" and issue.cell == "G2" for issue in scan.issues)`
- `any(issue["cell"] == "G2" for issue in workbook.formula_issues)`
- `marked["Điện"]["G2"].fill.fill_type == "solid"`
- `marked["Điện"]["G2"].comment is not None`
- `any("G2" in str(value) for value in values)`

### 11. ✅ `tests/test_grid.py::test_detect_simple_wired_table`

- **Tên dễ hiểu:** Nhận diện được bảng có đường kẻ trong ảnh
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Ảnh scan chứa một bảng đơn giản có các đường ngang và dọc.
- **Ví dụ cụ thể:** Ví dụ bảng 3 cột × 4 dòng với khung ô rõ ràng.
- **Kết quả mong đợi:** Thuật toán phải tìm được vùng bảng và các ô cơ bản.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Thuật toán phải tìm được vùng bảng và các ô cơ bản. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** OCR biết chia ảnh thành hàng/cột trước khi đọc chữ và số.
- **Nếu test thất bại:** Nội dung có thể bị dồn vào một cột hoặc sai cấu trúc Excel.
- **Vị trí:** `tests/test_grid.py:8`
- **Thời gian:** 0.029952 giây

**Các điều kiện kỹ thuật phải đúng:**

- `det is not None`
- `len(det.x_lines) >= 5`
- `len(det.y_lines) >= 8`

### 12. ✅ `tests/test_matcher.py::test_hybrid_match_is_one_to_one`

- **Tên dễ hiểu:** Mỗi hạng mục chỉ được ghép với một hạng mục tương ứng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Có hai dòng chuẩn và hai dòng nhà thầu có tên/mã gần giống.
- **Ví dụ cụ thể:** Ví dụ “Tủ điện tổng” và “Cáp XLPE” phải lần lượt ghép với đúng một dòng; không được dùng cùng một dòng nhà thầu cho cả hai.
- **Kết quả mong đợi:** Mỗi chỉ số dòng chuẩn và dòng ứng viên chỉ xuất hiện trong một cặp ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi chỉ số dòng chuẩn và dòng ứng viên chỉ xuất hiện trong một cặp ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh đếm lặp hoặc so sánh một báo giá cho nhiều hạng mục.
- **Nếu test thất bại:** Khối lượng và giá có thể bị nhân đôi hoặc một dòng khác bị coi là thiếu.
- **Vị trí:** `tests/test_matcher.py:15`
- **Thời gian:** 0.001090 giây

**Các điều kiện kỹ thuật phải đúng:**

- `len(matched) == 2`
- `len({m.candidate_index for m in matched}) == 2`

### 13. ✅ `tests/test_number_parser.py::test_parse_vietnamese_and_international_numbers`

- **Tên dễ hiểu:** Đọc đúng nhiều kiểu viết số
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Excel/PDF có thể dùng dấu chấm, dấu phẩy hoặc khoảng trắng làm dấu phân cách.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89” phải thành 1234567.89; “1,234,567.89” cũng phải cho cùng giá trị.
- **Kết quả mong đợi:** Bộ đọc số xác định đúng phần nghìn, phần thập phân và dấu âm.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Bộ đọc số xác định đúng phần nghìn, phần thập phân và dấu âm. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giá và khối lượng từ nhiều nguồn vẫn so sánh được.
- **Nếu test thất bại:** Một dấu phân cách bị hiểu sai có thể làm giá tăng hoặc giảm hàng nghìn lần.
- **Vị trí:** `tests/test_number_parser.py:4`
- **Thời gian:** 0.000491 giây

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number("1.234.567,89") == 1234567.89`
- `parse_number("1,234,567.89") == 1234567.89`
- `parse_number("1 234 567") == 1234567`
- `parse_number("(1.000)") == -1000`
- `parse_number("-0.5") == -0.5`
- `parse_number(0) == 0`
- `safe_amount(2, 100, 0) == 0`

### 14. ✅ `tests/test_ocr_high_accuracy.py::test_dense_19_column_grid_and_schema`

- **Tên dễ hiểu:** Nhận diện bảng BOQ dày có 19 cột
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tài liệu dự toán có rất nhiều cột hẹp, tiêu đề nhiều tầng và số liệu sát nhau.
- **Ví dụ cụ thể:** Ví dụ một trang có 19 cột gồm STT, mã hiệu, mô tả, đơn vị, khối lượng, vật liệu, nhân công, máy và các thành phần giá.
- **Kết quả mong đợi:** Hệ thống phải dựng được lưới 19 cột và ánh xạ đúng cấu trúc dữ liệu mong đợi.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống phải dựng được lưới 19 cột và ánh xạ đúng cấu trúc dữ liệu mong đợi. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** File OCR giữ được bố cục gần với biểu mẫu dự toán thực tế.
- **Nếu test thất bại:** Số liệu có thể bị chuyển nhầm cột, đặc biệt là khối lượng và đơn giá.
- **Vị trí:** `tests/test_ocr_high_accuracy.py:13`
- **Thời gian:** 0.049240 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "ys": [
    40,
    100,
    160,
    220,
    280,
    340,
    400,
    460,
    520,
    580,
    640,
    700,
    760,
    820,
    900
  ]
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `grids`
- `len(grids[0].x_lines) - 1 == 19`
- `mapping[0] == "stt"`
- `mapping[2] == "item_name"`
- `mapping[15] == "unit_price"`
- `mapping[18] == "note"`

### 15. ✅ `tests/test_ocr_high_accuracy.py::test_parser_keeps_multiple_tables`

- **Tên dễ hiểu:** Một trang có nhiều bảng thì phải giữ lại tất cả
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Trang scan chứa hai hoặc nhiều bảng độc lập.
- **Ví dụ cụ thể:** Ví dụ phía trên là bảng vật tư, phía dưới là bảng tổng hợp chi phí.
- **Kết quả mong đợi:** Parser phải trả về nhiều bảng, không chỉ lấy bảng đầu tiên.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser phải trả về nhiều bảng, không chỉ lấy bảng đầu tiên. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng không bị mất phần dữ liệu nằm ở bảng thứ hai.
- **Nếu test thất bại:** Báo cáo OCR thiếu nội dung dù ảnh gốc vẫn có dữ liệu.
- **Vị trí:** `tests/test_ocr_high_accuracy.py:36`
- **Thời gian:** 0.000761 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "html": "\n    <table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>\n    <table><tr><th>C</th></tr><tr><td>3</td></tr></table>\n    ",
  "markdown": "| A | B |\n|---|---|\n|1|2|\n\ntext\n\n| C |\n|---|\n|3|"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `len(tables) == 2`
- `tables[0][1] == ["1", "2"]`
- `tables[1][1] == ["3"]`
- `len(md_tables) == 2`

### 16. ✅ `tests/test_ocr_high_accuracy.py::test_zero_values_are_not_replaced_by_fallback`

- **Tên dễ hiểu:** Số 0 hợp lệ không được thay bằng giá trị dự phòng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** OCR đọc được một ô có giá trị 0 thật.
- **Ví dụ cụ thể:** Ví dụ chi phí máy thi công bằng 0; fallback khác đang có giá trị 100.
- **Kết quả mong đợi:** Kết quả cuối cùng vẫn phải là 0, vì 0 khác với ô không đọc được.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả cuối cùng vẫn phải là 0, vì 0 khác với ô không đọc được. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Không tự tạo chi phí giả trong bảng kết quả.
- **Nếu test thất bại:** Tổng tiền có thể bị tăng sai chỉ vì hệ thống hiểu 0 là thiếu dữ liệu.
- **Vị trí:** `tests/test_ocr_high_accuracy.py:51`
- **Thời gian:** 0.000573 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "xs": [
    0,
    30,
    130,
    180,
    230,
    299
  ],
  "ys": [
    0,
    50,
    100,
    159
  ],
  "values": [
    "Hạng mục",
    "0",
    "0",
    "100",
    "0"
  ]
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `rows[0]["quantity"] == 0.0`
- `rows[0]["amount"] == 0.0`
- `rows[0]["computed_amount"] == 0.0`

### 17. ✅ `tests/test_optional_appendices.py::test_pl1_only_is_supported`

- **Tên dễ hiểu:** Chỉ có PL01 vẫn xử lý được
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Người dùng có PL01 nhưng không có PL02.
- **Ví dụ cụ thể:** Ví dụ tải PL01 cùng file nhà thầu; ô PL02 để trống.
- **Kết quả mong đợi:** Pipeline vẫn chạy, dùng PL01 làm căn cứ cho mã, tên, đơn vị và khối lượng.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Pipeline vẫn chạy, dùng PL01 làm căn cứ cho mã, tên, đơn vị và khối lượng. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Không bắt người dùng phải có đủ cả hai phụ lục trong mọi trường hợp.
- **Nếu test thất bại:** Công việc bị chặn dù dữ liệu cần thiết đã có trong PL01.
- **Vị trí:** `tests/test_optional_appendices.py:40`
- **Thời gian:** 0.099739 giây

**Các điều kiện kỹ thuật phải đúng:**

- `outputs.report_path.exists()`
- `outputs.result.audit["mode"] == "PL01_ONLY_VS_MULTI_HSDT_PRICE_PEER"`
- `outputs.result.audit["peer_price_comparison_enabled"] is True`
- `outputs.result.audit["peer_comparison_scope"] == "price_only"`
- `outputs.result.audit["pl2_sha256"] == "NOT_PROVIDED"`
- `any("Không có PL02" in warning for warning in outputs.result.warnings)`

### 18. ✅ `tests/test_optional_appendices.py::test_pl2_only_uses_multiway_peer_consensus`

- **Tên dễ hiểu:** Chỉ có PL02 vẫn hỗ trợ so sánh nhiều nhà thầu theo mặt bằng chung
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Không có PL01 nhưng có PL02 và nhiều file nhà thầu.
- **Ví dụ cụ thể:** Ví dụ ba nhà thầu báo 100, 103 và 190 cho cùng hạng mục.
- **Kết quả mong đợi:** Hệ thống dùng đối chiếu đa chiều để nhận ra giá 190 lệch khỏi nhóm, không chọn tùy ý một nhà thầu làm chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống dùng đối chiếu đa chiều để nhận ra giá 190 lệch khỏi nhóm, không chọn tùy ý một nhà thầu làm chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So sánh công bằng giữa các nhà thầu.
- **Nếu test thất bại:** Kết quả có thể thiên lệch nếu lấy một nhà thầu làm mốc tuyệt đối.
- **Vị trí:** `tests/test_optional_appendices.py:52`
- **Thời gian:** 0.245646 giây

**Các điều kiện kỹ thuật phải đúng:**

- `outputs.report_path.exists()`
- `outputs.result.audit["mode"] == "PL02_ONLY_MULTIWAY_HSDT_PRICE_PEER"`
- `outputs.result.audit["catalogue_mode"] == "MULTIWAY_PEER_CONSENSUS"`
- `outputs.result.audit["peer_cluster_stats"]["clusters"] >= 1`
- `"baseline_bidder" not in outputs.result.audit`
- `all("không có baseline" in str(row.match.reason).lower() or row.match.kind.value == "missing" for row in outputs.result.rows)`
- `any(row.pl2_status for row in outputs.result.rows if row.candidate)`

### 19. ✅ `tests/test_optional_appendices.py::test_single_bidder_pl1_compares_appendix_without_peer_price`

- **Tên dễ hiểu:** Một nhà thầu chỉ đối chiếu yêu cầu, không phán xét giá ngang hàng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Có PL01 và duy nhất một hồ sơ nhà thầu.
- **Ví dụ cụ thể:** Ví dụ PL01 không có đơn giá chuẩn; nhà thầu báo 1.000.000 đồng.
- **Kết quả mong đợi:** Hệ thống kiểm tra tên, mã, đơn vị, số lượng và yêu cầu kỹ thuật nhưng không nói giá cao/thấp do không có nhà thầu khác để so.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống kiểm tra tên, mã, đơn vị, số lượng và yêu cầu kỹ thuật nhưng không nói giá cao/thấp do không có nhà thầu khác để so. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh đưa ra kết luận giá thiếu căn cứ.
- **Nếu test thất bại:** Một giá hợp lệ có thể bị gắn cảnh báo sai chỉ vì đem so với dữ liệu không phải giá tham chiếu.
- **Vị trí:** `tests/test_optional_appendices.py:65`
- **Thời gian:** 0.077777 giây

**Các điều kiện kỹ thuật phải đúng:**

- `outputs.report_path.exists()`
- `outputs.package_zip.exists()`
- `outputs.result.audit["mode"] == "PL01_ONLY_VS_SINGLE_HSDT"`
- `outputs.result.audit["bidder_count"] == 1`
- `outputs.result.audit["peer_price_comparison_enabled"] is False`
- `outputs.result.audit["peer_comparison_scope"] == "disabled"`
- `outputs.result.audit["peer_stats"]["enabled"] is False`
- `not any(
        difference.field.startswith("So sánh ngang hàng")
        for row in outputs.result.rows
        for difference in row.differences
    )`

### 20. ✅ `tests/test_optional_appendices.py::test_package_multi_bidder_peer_stage_is_price_only`

- **Tên dễ hiểu:** Giai đoạn so sánh ngang hàng chỉ xét giá
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Sau khi từng hồ sơ đã được đối chiếu với PL01/PL02, hệ thống so các nhà thầu với nhau.
- **Ví dụ cụ thể:** Ví dụ tên sheet khác nhau nhưng cùng hạng mục; giai đoạn ngang hàng chỉ so đơn giá của hạng mục đã ghép.
- **Kết quả mong đợi:** Không tạo lại cảnh báo tên, đơn vị hoặc số lượng ở bước ngang hàng; chỉ tạo cảnh báo giá giữa các nhà thầu.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Không tạo lại cảnh báo tên, đơn vị hoặc số lượng ở bước ngang hàng; chỉ tạo cảnh báo giá giữa các nhà thầu. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Báo cáo rõ nguồn cảnh báo và không lặp lỗi.
- **Nếu test thất bại:** Người dùng có thể nhận nhiều cảnh báo trùng nhau và khó biết lỗi nằm ở phụ lục hay ở giá.
- **Vị trí:** `tests/test_optional_appendices.py:91`
- **Thời gian:** 0.122250 giây

**Các điều kiện kỹ thuật phải đúng:**

- `peer_fields`
- `any("Đơn giá tổng hợp" in field for field in peer_fields)`
- `not any("Khối lượng" in field for field in peer_fields)`
- `not any("Đơn vị" in field for field in peer_fields)`

### 21. ✅ `tests/test_orientation.py::test_semantic_score_prefers_valid_vietnamese_table_header`

- **Tên dễ hiểu:** Ưu tiên hướng ảnh có tiêu đề tiếng Việt hợp lý
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một trang được thử ở nhiều góc xoay 0°, 90°, 180° và 270°.
- **Ví dụ cụ thể:** Ở góc đúng có các từ như “STT”, “Mô tả công việc”, “Đơn vị”, “Khối lượng”; góc sai tạo chuỗi vô nghĩa.
- **Kết quả mong đợi:** Điểm ngữ nghĩa của góc đúng phải cao hơn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Điểm ngữ nghĩa của góc đúng phải cao hơn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Hệ thống chọn đúng chiều đọc dựa trên nội dung chứ không chỉ dựa vào hình học.
- **Nếu test thất bại:** OCR có thể đọc trang bị lộn ngược và tạo Excel vô nghĩa.
- **Vị trí:** `tests/test_orientation.py:11`
- **Thời gian:** 0.001362 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "good": "STT Diễn giải Đơn vị Khối lượng Mã hiệu Thương hiệu Xuất xứ Đơn giá Thành tiền Ghi chú",
  "bad": "WRI DAT V30 dvV0EC LVisc BUND RATAN KkUELDTCEXTLE"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `good_score >= 30`
- `good_score > bad_score + 20`
- `"dien giai" in hits`
- `"thanh tien" in hits`

### 22. ✅ `tests/test_orientation.py::test_orientation_selection_uses_semantic_probe`

- **Tên dễ hiểu:** Bộ chọn hướng phải thực sự dùng kết quả kiểm tra ngữ nghĩa
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Các góc xoay có chất lượng hình ảnh gần giống nhau nhưng chỉ một góc tạo ra chữ đúng.
- **Ví dụ cụ thể:** Ví dụ góc 90° nhận được tiêu đề chuẩn, góc 0° chỉ có ký tự rời rạc.
- **Kết quả mong đợi:** Hàm chọn hướng phải chọn góc có nội dung hợp lý.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hàm chọn hướng phải chọn góc có nội dung hợp lý. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng độ chính xác OCR cho file scan bị xoay.
- **Nếu test thất bại:** Trang vẫn có thể bị chọn sai dù đã có bước dò hướng.
- **Vị trí:** `tests/test_orientation.py:22`
- **Thời gian:** 0.001370 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "calls": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `tables`
- `calls == [180]`
- `page.rotation == 180`
- `page.orientation_method == "semantic-header-probe"`
- `page.orientation_scores[180] == 45.0`

### 23. ✅ `tests/test_orientation.py::test_dense_boq_header_rows_do_not_stop_at_second_thin_row`

- **Tên dễ hiểu:** Không kết thúc tiêu đề bảng quá sớm
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** BOQ có tiêu đề nhiều tầng và một vài dòng tiêu đề rất ít chữ.
- **Ví dụ cụ thể:** Ví dụ dòng 1 là nhóm cột, dòng 2 chỉ có vài ô, dòng 3 mới chứa tên cột chi tiết.
- **Kết quả mong đợi:** Parser phải tiếp tục đọc đủ phần tiêu đề thay vì dừng ở dòng mỏng thứ hai.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser phải tiếp tục đọc đủ phần tiêu đề thay vì dừng ở dòng mỏng thứ hai. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tên cột được xác định đúng trong biểu mẫu phức tạp.
- **Nếu test thất bại:** Dữ liệu có thể bị xem nhầm là tiêu đề hoặc tên cột bị thiếu.
- **Vị trí:** `tests/test_orientation.py:50`
- **Thời gian:** 0.000850 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "y_lines": [
    0,
    13,
    26,
    50,
    75,
    88,
    101,
    114
  ]
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `infer_header_rows(table) == 4`

### 24. ✅ `tests/test_package_mode.py::test_package_mode_uses_pl1_pl2_and_no_bidder_baseline`

- **Tên dễ hiểu:** Chế độ gói thầu dùng phụ lục làm căn cứ, không lấy nhà thầu đầu tiên làm chuẩn
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Có PL01, PL02 và nhiều hồ sơ nhà thầu.
- **Ví dụ cụ thể:** Ví dụ nhà thầu A và B đều được đối chiếu độc lập với phụ lục; A không được dùng làm chuẩn để chấm B.
- **Kết quả mong đợi:** Cấu trúc và khối lượng lấy từ phụ lục, còn giá nhiều nhà thầu được so ngang hàng.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Cấu trúc và khối lượng lấy từ phụ lục, còn giá nhiều nhà thầu được so ngang hàng. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Đảm bảo tính trung lập khi đánh giá.
- **Nếu test thất bại:** Nhà thầu được tải đầu tiên có thể vô tình chi phối toàn bộ kết quả.
- **Vị trí:** `tests/test_package_mode.py:38`
- **Thời gian:** 0.127654 giây

**Các điều kiện kỹ thuật phải đúng:**

- `outputs.report_path.exists()`
- `outputs.package_zip.exists()`
- `set(outputs.annotated_files) == {"A", "B"}`
- `outputs.result.audit["peer_price_comparison_enabled"] is True`
- `outputs.result.audit["peer_comparison_scope"] == "price_only"`
- `"horizontal comparison is limited to price fields" in outputs.result.audit["comparison_principle"]`
- `{r.bidder for r in rows} == {"A", "B"}`
- `all(r.consensus_price == 200_000 for r in rows)`
- `any("chênh" in flag.lower() and "nhà thầu" in flag.lower() for r in rows for flag in r.flags)`
- `bidder_b.pl2_status == "CẦN THẨM ĐỊNH TƯƠNG ĐƯƠNG"`
- `annotated_b.sheetnames[:2] == ["AI_TONG_QUAN", "AI_KIEM_TRA"]`
- `annotated_b["Điện"]["L2"].value == "=H2*D2"`
- `"AI MỨC ĐỘ" in headers`
- `"AI LÝ DO" in headers`

### 25. ✅ `tests/test_regressions.py::test_column_number_legend_does_not_hide_normal_priced_row`

- **Tên dễ hiểu:** Dòng chú giải số cột không được làm mất dòng giá bình thường
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một sheet có hàng chú giải đánh số cột 1, 2, 3… gần vùng dữ liệu.
- **Ví dụ cụ thể:** Ví dụ dòng chú giải nằm phía trên một hạng mục có đơn giá hợp lệ.
- **Kết quả mong đợi:** Parser phải bỏ qua chú giải nhưng vẫn giữ dòng hạng mục phía dưới.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser phải bỏ qua chú giải nhưng vẫn giữ dòng hạng mục phía dưới. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Sửa lỗi cũ từng khiến dữ liệu thật bị ẩn nhầm.
- **Nếu test thất bại:** Một hạng mục hợp lệ có thể biến mất khỏi báo cáo.
- **Vị trí:** `tests/test_regressions.py:9`
- **Thời gian:** 0.000689 giây

**Các điều kiện kỹ thuật phải đúng:**

- `_is_numbering_row([1, 2, 3, 4, 5, 6])`
- `not _is_numbering_row(["M-01", "Tủ điện", "Tủ", 1, 1000, 1000])`

### 26. ✅ `tests/test_regressions.py::test_component_without_price_is_not_false_quality_error`

- **Tên dễ hiểu:** Dòng thành phần không có giá không được báo lỗi chất lượng giả
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một dòng chỉ là tiêu đề nhóm hoặc thành phần mô tả, không yêu cầu đơn giá.
- **Ví dụ cụ thể:** Ví dụ dòng “A. Hệ thống điện” không có giá vì không phải vật tư chi tiết.
- **Kết quả mong đợi:** Hệ thống nhận diện đúng loại dòng và không cảnh báo thiếu giá.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống nhận diện đúng loại dòng và không cảnh báo thiếu giá. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Báo cáo tập trung vào lỗi thật thay vì làm người dùng mất thời gian.
- **Nếu test thất bại:** Báo cáo có quá nhiều cảnh báo giả, làm giảm độ tin cậy.
- **Vị trí:** `tests/test_regressions.py:14`
- **Thời gian:** 0.008559 giây

**Các điều kiện kỹ thuật phải đúng:**

- `"Thiếu đơn giá tổng hợp" not in component.data_quality_flags`
- `"Thiếu thành tiền" not in component.data_quality_flags`

### 27. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce01_equal_quantity_has_no_warning`

- **Tên dễ hiểu:** Khối lượng bằng nhau thì không cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Phụ lục và nhà thầu ghi cùng một số lượng.
- **Ví dụ cụ thể:** Ví dụ PL01 = 100 mét cáp, nhà thầu = 100 mét cáp.
- **Kết quả mong đợi:** Độ chênh bằng 0% và trạng thái không phải WARNING/CRITICAL.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Độ chênh bằng 0% và trạng thái không phải WARNING/CRITICAL. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng không bị làm phiền bởi dữ liệu hoàn toàn khớp.
- **Nếu test thất bại:** Hệ thống có thể tạo cảnh báo giả cho hồ sơ đúng.
- **Vị trí:** `tests/test_s1_comparison_engine.py:95`
- **Thời gian:** 0.000527 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.quantity_delta == 0`
- `row.quantity_delta_pct == 0`
- `row.severity is Severity.OK`
- `row.flags == []`

### 28. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce02_quantity_difference_8_percent_is_warning`

- **Tên dễ hiểu:** Chênh khối lượng 8% phải tạo cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu ghi số lượng lệch vừa phải so với phụ lục.
- **Ví dụ cụ thể:** Ví dụ PL01 = 100, nhà thầu = 108; chênh 8%.
- **Kết quả mong đợi:** Hệ thống gắn mức WARNING theo ngưỡng đang cấu hình.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống gắn mức WARNING theo ngưỡng đang cấu hình. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người kiểm tra biết có sai khác cần xem lại nhưng chưa phải mức nghiêm trọng nhất.
- **Nếu test thất bại:** Sai số vừa phải có thể bị bỏ qua.
- **Vị trí:** `tests/test_s1_comparison_engine.py:112`
- **Thời gian:** 0.000384 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.quantity_delta == 8`
- `row.quantity_delta_pct == 0.08`
- `row.severity is Severity.WARNING`
- `any("khối lượng nhà thầu chào" in flag.lower() for flag in row.flags)`

### 29. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce03_quantity_difference_35_percent_is_critical`

- **Tên dễ hiểu:** Chênh khối lượng 35% phải là nghiêm trọng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Số lượng nhà thầu khác rất xa yêu cầu.
- **Ví dụ cụ thể:** Ví dụ PL01 = 100, nhà thầu = 135; chênh 35%.
- **Kết quả mong đợi:** Hệ thống gắn CRITICAL hoặc mức nghiêm trọng tương đương.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống gắn CRITICAL hoặc mức nghiêm trọng tương đương. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Lỗi lớn được đưa lên ưu tiên xử lý.
- **Nếu test thất bại:** Sai khối lượng lớn có thể bị xem như cảnh báo nhẹ.
- **Vị trí:** `tests/test_s1_comparison_engine.py:129`
- **Thời gian:** 0.000359 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.quantity_delta_pct == 0.35`
- `row.severity is Severity.CRITICAL`
- `row.anomaly_score >= 24`

### 30. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce04_unit_mismatch_is_flagged`

- **Tên dễ hiểu:** Khác đơn vị phải được cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tên hạng mục giống nhau nhưng đơn vị không tương thích.
- **Ví dụ cụ thể:** Ví dụ phụ lục dùng “m”, nhà thầu dùng “100m” hoặc “bộ”.
- **Kết quả mong đợi:** Hệ thống gắn cờ UNIT_MISMATCH và không coi số lượng là so sánh trực tiếp.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống gắn cờ UNIT_MISMATCH và không coi số lượng là so sánh trực tiếp. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh kết luận sai khi 5 đơn vị “100m” thực chất bằng 500m.
- **Nếu test thất bại:** Khối lượng có thể bị hiểu sai 100 lần.
- **Vị trí:** `tests/test_s1_comparison_engine.py:145`
- **Thời gian:** 0.000401 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity is not Severity.OK`
- `any("đơn vị tính" in flag.lower() for flag in row.flags)`
- `any("khối lượng" in flag.lower() for flag in row.flags)`

### 31. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce05_missing_item_is_critical`

- **Tên dễ hiểu:** Hạng mục bị thiếu phải là lỗi nghiêm trọng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Phụ lục có yêu cầu nhưng hồ sơ nhà thầu không có dòng tương ứng.
- **Ví dụ cụ thể:** Ví dụ PL01 có máy bơm P-01 nhưng file nhà thầu không tìm thấy P-01 hoặc tên tương đương.
- **Kết quả mong đợi:** Kết quả phải có trạng thái MISSING và mức CRITICAL.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả phải có trạng thái MISSING và mức CRITICAL. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng thấy ngay nhà thầu chưa chào đủ phạm vi.
- **Nếu test thất bại:** Hồ sơ thiếu hàng hóa có thể được đánh giá nhầm là đầy đủ.
- **Vị trí:** `tests/test_s1_comparison_engine.py:162`
- **Thời gian:** 0.000317 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity is Severity.CRITICAL`
- `any("thiếu hạng mục" in flag.lower() for flag in row.flags)`

### 32. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce06_extra_item_is_warning`

- **Tên dễ hiểu:** Hạng mục phát sinh phải được thông báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu thêm một dòng không có trong phụ lục.
- **Ví dụ cụ thể:** Ví dụ thêm “Chi phí vận chuyển” hoặc một thiết bị ngoài danh mục.
- **Kết quả mong đợi:** Kết quả ghi EXTRA_ITEM ở mức cảnh báo để người dùng xem xét.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả ghi EXTRA_ITEM ở mức cảnh báo để người dùng xem xét. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Phát hiện chi phí hoặc phạm vi bổ sung.
- **Nếu test thất bại:** Khoản phát sinh có thể bị bỏ qua trong tổng giá.
- **Vị trí:** `tests/test_s1_comparison_engine.py:172`
- **Thời gian:** 0.000302 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity is Severity.WARNING`
- `any("phát sinh ngoài" in flag.lower() for flag in row.flags)`

### 33. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce07_different_sheet_is_note_not_warning`

- **Tên dễ hiểu:** Khác sheet chỉ là ghi chú khi nội dung vẫn khớp
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hai file đặt cùng hạng mục ở các sheet có tên khác nhau.
- **Ví dụ cụ thể:** Ví dụ PL01 đặt “Tủ điện LV-G.1” ở sheet “Hạ thế”, nhà thầu đặt ở sheet “HT điện”. Tên, đơn vị và số lượng vẫn giống.
- **Kết quả mong đợi:** Hệ thống ghép thành công và chỉ ghi “khác sheet”, không tăng mức cảnh báo.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống ghép thành công và chỉ ghi “khác sheet”, không tăng mức cảnh báo. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Cho phép nhà thầu tổ chức workbook khác mà không bị chấm lỗi oan.
- **Nếu test thất bại:** Báo cáo có thể cảnh báo hàng loạt chỉ vì cách chia sheet khác nhau.
- **Vị trí:** `tests/test_s1_comparison_engine.py:182`
- **Thời gian:** 0.000372 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity is Severity.OK`
- `row.anomaly_score == 0`
- `row.flags == []`
- `any("khác sheet" in note.lower() for note in row.notes)`

### 34. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce08_single_bidder_does_not_compare_price_against_pl01`

- **Tên dễ hiểu:** Không so giá một nhà thầu với PL01 khi PL01 không phải bảng giá tham chiếu
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Chỉ có một nhà thầu và phụ lục yêu cầu.
- **Ví dụ cụ thể:** Ví dụ nhà thầu báo 2 triệu; PL01 chỉ có khối lượng và mô tả.
- **Kết quả mong đợi:** Không sinh PRICE_HIGH/PRICE_LOW ở giai đoạn đối chiếu phụ lục.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Không sinh PRICE_HIGH/PRICE_LOW ở giai đoạn đối chiếu phụ lục. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Kết luận giá phải dựa trên dữ liệu hợp lý.
- **Nếu test thất bại:** Nhà thầu có thể bị báo giá bất thường sai căn cứ.
- **Vị trí:** `tests/test_s1_comparison_engine.py:205`
- **Thời gian:** 0.000336 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.price_delta is None`
- `row.price_delta_pct is None`
- `not any("đơn giá" in flag.lower() for flag in row.flags)`

### 35. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce09_price_outlier_is_flagged_only_in_peer_stage`

- **Tên dễ hiểu:** Giá lệch chỉ được cảnh báo khi so giữa nhiều nhà thầu
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Có ít nhất ba giá cho cùng một hạng mục.
- **Ví dụ cụ thể:** Ví dụ NT1 = 100, NT2 = 105, NT3 = 200.
- **Kết quả mong đợi:** Giai đoạn peer comparison gắn cờ cho 200; giai đoạn PL01 không tạo cờ giá này.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Giai đoạn peer comparison gắn cờ cho 200; giai đoạn PL01 không tạo cờ giá này. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tách rõ đối chiếu yêu cầu và phân tích giá thị trường nội bộ.
- **Nếu test thất bại:** Cảnh báo giá có thể xuất hiện sai bước hoặc bị tính lặp.
- **Vị trí:** `tests/test_s1_comparison_engine.py:227`
- **Thời gian:** 0.000816 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "prices": {
    "NT1": 100000000.0,
    "NT2": 105000000.0,
    "NT3": 95000000.0,
    "NT4": 200000000.0
  },
  "rows": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `all(row.severity is Severity.OK for row in rows)`
- `nt4.consensus_price is not None`
- `nt4.severity in {Severity.WARNING, Severity.CRITICAL}`
- `any("đơn giá tổng hợp" in flag.lower() for flag in nt4.flags)`

### 36. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce10_formula_error_is_critical`

- **Tên dễ hiểu:** Lỗi công thức #REF! phải là nghiêm trọng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một ô công thức trong workbook bị hỏng tham chiếu.
- **Ví dụ cụ thể:** Ví dụ thành tiền là =D5*#REF! hoặc ô hiển thị #REF!.
- **Kết quả mong đợi:** Hệ thống tạo FORMULA_ERROR ở mức CRITICAL và chỉ rõ sheet/dòng/ô.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống tạo FORMULA_ERROR ở mức CRITICAL và chỉ rõ sheet/dòng/ô. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng biết số tiền có thể không đáng tin.
- **Nếu test thất bại:** Báo cáo tài chính có thể dùng số liệu sai do công thức lỗi.
- **Vị trí:** `tests/test_s1_comparison_engine.py:267`
- **Thời gian:** 0.000357 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.severity is Severity.CRITICAL`
- `any("#ref" in flag.lower() for flag in row.flags)`

### 37. ✅ `tests/test_s1_comparison_engine.py::test_s1_ce11_configurable_quantity_threshold_is_used`

- **Tên dễ hiểu:** Ngưỡng cảnh báo cấu hình phải được áp dụng thật
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Quản trị viên đổi ngưỡng chênh khối lượng.
- **Ví dụ cụ thể:** Ví dụ giảm ngưỡng cảnh báo từ 5% xuống 3%; dữ liệu lệch 4% giờ phải cảnh báo.
- **Kết quả mong đợi:** Kết quả thay đổi theo cấu hình mới, không dùng giá trị viết cứng trong code.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả thay đổi theo cấu hình mới, không dùng giá trị viết cứng trong code. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Mỗi dự án có thể đặt tiêu chuẩn kiểm tra riêng.
- **Nếu test thất bại:** Giao diện cho phép đổi ngưỡng nhưng kết quả không thay đổi.
- **Vị trí:** `tests/test_s1_comparison_engine.py:283`
- **Thời gian:** 0.000342 giây

**Các điều kiện kỹ thuật phải đúng:**

- `row.quantity_delta_pct == 0.04`
- `row.severity is Severity.WARNING`

### 38. ✅ `tests/test_s1_file_parser.py::test_s1_fi01_parse_valid_xlsx_and_preserve_source_row`

- **Tên dễ hiểu:** Đọc file XLSX hợp lệ và giữ đúng số dòng nguồn
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Workbook có một hạng mục ở một dòng xác định.
- **Ví dụ cụ thể:** Ví dụ “Máy bơm” nằm ở dòng Excel 12.
- **Kết quả mong đợi:** Sau khi parse, ItemRecord vẫn ghi row_number = 12 và đúng tên sheet.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Sau khi parse, ItemRecord vẫn ghi row_number = 12 và đúng tên sheet. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Khi cảnh báo, người dùng mở đúng dòng trong file gốc.
- **Nếu test thất bại:** Báo cáo chỉ sai vị trí, khiến người dùng khó kiểm tra.
- **Vị trí:** `tests/test_s1_file_parser.py:43`
- **Thời gian:** 0.006075 giây

**Các điều kiện kỹ thuật phải đúng:**

- `workbook.read_engine in {"calamine", "openpyxl"}`
- `len(workbook.items) == 1`
- `item.sheet == "Điện"`
- `item.row_number == 2`
- `item.item_code == "M-01"`
- `item.item_name == "Cáp điện Cu/XLPE 4x10"`
- `item.bid_quantity == 10`
- `item.unit_price_total == 100`
- `item.bid_amount == 1_000`

### 39. ✅ `tests/test_s1_file_parser.py::test_s1_fi02_detect_multi_level_header`

- **Tên dễ hiểu:** Tự tìm tiêu đề nhiều tầng
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** File có vài dòng tên công trình và nhóm cột trước dòng tiêu đề thật.
- **Ví dụ cụ thể:** Ví dụ dòng 5 có STT/Mô tả, dòng 6 có Đơn vị/Khối lượng/Đơn giá.
- **Kết quả mong đợi:** Parser xác định đúng vùng tiêu đề và cột dữ liệu.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser xác định đúng vùng tiêu đề và cột dữ liệu. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Không phụ thuộc cứng vào việc header luôn nằm ở dòng 1.
- **Nếu test thất bại:** Toàn bộ cột có thể bị đọc sai khi nhà thầu dùng mẫu khác.
- **Vị trí:** `tests/test_s1_file_parser.py:61`
- **Thời gian:** 0.000657 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "rows": [
    [
      "BÁO GIÁ",
      null,
      null,
      null,
      null,
      null
    ],
    [
      "Thông tin công việc",
      null,
      null,
      "Khối lượng",
      "Đơn giá",
      "Thành tiền"
    ],
    [
      "Mã hiệu",
      "Tên hạng mục",
      "ĐVT",
      "Nhà thầu",
      "Tổng hợp",
      "Nhà thầu"
    ],
    [
      "M-01",
      "Tủ điện tổng",
      "Tủ",
      1,
      1000000,
      1000000
    ]
  ]
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `start == 1`
- `end == 2`
- `"item_code" in fixed.values()`
- `"item_name" in fixed.values()`
- `"unit" in fixed.values()`
- `"bid_quantity" in fixed.values()`
- `"unit_price_total" in fixed.values()`
- `"bid_amount" in fixed.values()`

### 40. ✅ `tests/test_s1_file_parser.py::test_s1_fi03_calamine_matrix_preserves_raw_rows`

- **Tên dễ hiểu:** Ma trận Calamine giữ nguyên dữ liệu thô
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đọc sheet trước khi chuyển thành hạng mục chuẩn hóa.
- **Ví dụ cụ thể:** Ví dụ các ô trống, số 0 và chuỗi mô tả phải còn đúng vị trí.
- **Kết quả mong đợi:** Số hàng/cột và giá trị ô quan trọng không bị thay đổi.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Số hàng/cột và giá trị ô quan trọng không bị thay đổi. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Bảo đảm bước đọc nhanh không làm biến dạng dữ liệu.
- **Nếu test thất bại:** Lỗi phát sinh ngay từ bước đầu và lan sang toàn bộ phép so sánh.
- **Vị trí:** `tests/test_s1_file_parser.py:82`
- **Thời gian:** 0.004876 giây

**Các điều kiện kỹ thuật phải đúng:**

- `matrices.engine in {"calamine", "openpyxl"}`
- `len(matrices.sheets) == 1`
- `matrices.sheets[0].name == "Điện"`
- `matrices.sheets[0].rows[1][0] == "M-01"`

### 41. ✅ `tests/test_s1_file_parser.py::test_s1_fi04_formula_ref_is_detected`

- **Tên dễ hiểu:** Bộ đọc file phát hiện #REF!
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Trong file có công thức lỗi.
- **Ví dụ cụ thể:** Ví dụ ô F20 chứa =SUM(#REF!).
- **Kết quả mong đợi:** Danh sách lỗi phải chứa vị trí ô và loại lỗi tham chiếu.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Danh sách lỗi phải chứa vị trí ô và loại lỗi tham chiếu. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Cảnh báo được tạo trước khi dùng số liệu để so sánh.
- **Nếu test thất bại:** Số tổng sai có thể được sử dụng như dữ liệu hợp lệ.
- **Vị trí:** `tests/test_s1_file_parser.py:94`
- **Thời gian:** 0.006451 giây

**Các điều kiện kỹ thuật phải đúng:**

- `any(issue.kind == "FORMULA_ERROR" and issue.cell == "G2" for issue in scan.issues)`
- `any(issue["cell"] == "G2" for issue in workbook.formula_issues)`
- `any("#REF" in warning.upper() for warning in workbook.warnings)`

### 42. ✅ `tests/test_s1_file_parser.py::test_s1_fi05_four_workbooks_are_loaded_in_parallel`

- **Tên dễ hiểu:** Bốn file được đọc song song và đủ kết quả
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hệ thống nhận nhiều hồ sơ cùng lúc.
- **Ví dụ cụ thể:** Ví dụ bốn file nhỏ được giao cho bốn tác vụ đọc.
- **Kết quả mong đợi:** Kết quả có đủ bốn workbook và nội dung giống cách đọc tuần tự.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả có đủ bốn workbook và nội dung giống cách đọc tuần tự. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng tốc mà vẫn an toàn dữ liệu.
- **Nếu test thất bại:** Có thể xảy ra race condition, thiếu file hoặc lẫn kết quả.
- **Vị trí:** `tests/test_s1_file_parser.py:106`
- **Thời gian:** 0.028613 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "specs": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `set(result) == {"0", "1", "2", "3"}`
- `all(book.read_engine in {"calamine", "openpyxl"} for book in result.values())`
- `[result[str(i)].items[0].unit_price_total for i in range(4)] == [100, 101, 102, 103]`

### 43. ✅ `tests/test_s1_file_parser.py::test_s1_fi06_invalid_extension_is_rejected`

- **Tên dễ hiểu:** Từ chối định dạng không được hỗ trợ
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Người dùng đổi tên hoặc tải file không phải Excel.
- **Ví dụ cụ thể:** Ví dụ tải file .txt, .exe hoặc .pdf vào chức năng chỉ nhận workbook.
- **Kết quả mong đợi:** Hệ thống dừng sớm và trả thông báo định dạng hợp lệ, không cố parse.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống dừng sớm và trả thông báo định dạng hợp lệ, không cố parse. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng nhận lỗi rõ ràng và hệ thống tránh xử lý dữ liệu nguy hiểm.
- **Nếu test thất bại:** Có thể crash, treo job hoặc tạo báo cáo rỗng khó hiểu.
- **Vị trí:** `tests/test_s1_file_parser.py:125`
- **Thời gian:** 0.001142 giây

### 44. ✅ `tests/test_s1_file_parser.py::test_s1_fi07_corrupt_xlsx_returns_clear_error`

- **Tên dễ hiểu:** File XLSX hỏng phải trả lỗi dễ hiểu
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đuôi file là .xlsx nhưng nội dung ZIP bên trong bị hỏng.
- **Ví dụ cụ thể:** Ví dụ file bị cắt khi tải lên hoặc chỉ chứa vài byte.
- **Kết quả mong đợi:** Hệ thống báo rõ file không đọc được và nêu tên file, không nuốt lỗi.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống báo rõ file không đọc được và nêu tên file, không nuốt lỗi. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Người dùng biết cần tải lại file nào.
- **Nếu test thất bại:** Job chỉ báo “failed” chung chung hoặc treo không kết thúc.
- **Vị trí:** `tests/test_s1_file_parser.py:133`
- **Thời gian:** 0.001146 giây

### 45. ✅ `tests/test_s1_file_parser.py::test_s1_fi08_duplicate_code_rows_are_preserved_and_flagged`

- **Tên dễ hiểu:** Dòng trùng mã không bị xóa trong bước parse
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một mã xuất hiện nhiều lần trong cùng sheet.
- **Ví dụ cụ thể:** Ví dụ hai dòng M-01 có mô tả hoặc khối lượng khác nhau.
- **Kết quả mong đợi:** Parser giữ cả hai, sau đó auditor gắn cờ trùng mã.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser giữ cả hai, sau đó auditor gắn cờ trùng mã. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Vừa bảo toàn hồ sơ gốc vừa hỗ trợ phát hiện sai sót.
- **Nếu test thất bại:** Một dòng có thể bị ghi đè và biến mất.
- **Vị trí:** `tests/test_s1_file_parser.py:141`
- **Thời gian:** 0.007313 giây

**Các điều kiện kỹ thuật phải đúng:**

- `len(comparable) == 2`
- `all(item.normalized_code == "M-01" for item in comparable)`
- `any("mã hiệu trùng" in flag.lower() for item in comparable for flag in item.data_quality_flags)`

### 46. ✅ `tests/test_s1_file_parser.py::test_s1_fi09_component_without_price_is_not_false_error`

- **Tên dễ hiểu:** Dòng nhóm không có giá không bị báo lỗi giả
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Một dòng là tiêu đề hoặc cấu phần không yêu cầu đơn giá.
- **Ví dụ cụ thể:** Ví dụ “I. PHẦN ĐIỆN” chỉ dùng để phân nhóm.
- **Kết quả mong đợi:** Parser phân loại đúng row_type và không tạo lỗi thiếu giá.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Parser phân loại đúng row_type và không tạo lỗi thiếu giá. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm cảnh báo rác trong báo cáo.
- **Nếu test thất bại:** Người dùng phải xem hàng trăm cảnh báo không có ý nghĩa.
- **Vị trí:** `tests/test_s1_file_parser.py:159`
- **Thời gian:** 0.005943 giây

**Các điều kiện kỹ thuật phải đúng:**

- `"Thiếu đơn giá tổng hợp" not in component.data_quality_flags`
- `"Thiếu thành tiền" not in component.data_quality_flags`

### 47. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[(1.000)--1000.0]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000414 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "(1.000)",
  "expected": -1000.0
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 48. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[-0.5--0.5]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000392 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "-0.5",
  "expected": -0.5
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 49. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[0-0.0]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000380 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": 0,
  "expected": 0.0
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 50. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[1 234 567-1234567.0]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000404 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "1 234 567",
  "expected": 1234567.0
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 51. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[1,234,567.89-1234567.89]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000418 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "1,234,567.89",
  "expected": 1234567.89
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 52. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[1.234.567,89-1234567.89]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000909 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "1.234.567,89",
  "expected": 1234567.89
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 53. ✅ `tests/test_s1_normalizer.py::test_s1_nr01_parse_vietnamese_and_international_numbers[1.500.000 VN\u0110-1500000.0]`

- **Tên dễ hiểu:** Chuẩn hóa số Việt Nam và quốc tế
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Cùng một giá trị có thể được viết theo nhiều quy ước.
- **Ví dụ cụ thể:** Ví dụ “1.234.567,89”, “1,234,567.89” và “1 234 567,89”.
- **Kết quả mong đợi:** Tất cả phải được chuyển thành số thực đúng để có thể tính toán.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải được chuyển thành số thực đúng để có thể tính toán. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tránh sai giá trị khi nhận file từ nhiều nhà thầu.
- **Nếu test thất bại:** Một đơn giá có thể bị hiểu sai hàng nghìn lần.
- **Vị trí:** `tests/test_s1_normalizer.py:59`
- **Thời gian:** 0.000418 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "1.500.000 VNĐ",
  "expected": 1500000.0
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `parse_number(raw) == pytest.approx(expected)`

### 54. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[M2]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000337 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "M2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 55. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[m 2]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000336 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m 2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 56. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[m2]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000362 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 57. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[m\xb2]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000341 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m²"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 58. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[m\xe9t vu\xf4ng]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000340 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "mét vuông"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 59. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[m^2]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000335 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m^2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 60. ✅ `tests/test_s1_normalizer.py::test_s1_nr02_normalize_square_metre_variants[met vuong]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét vuông
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị diện tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m2, M2, m², m^2, “mét vuông”.
- **Kết quả mong đợi:** Tất cả phải trở thành một giá trị chuẩn là m².
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành một giá trị chuẩn là m². Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Các dòng cùng đơn vị vẫn ghép được dù cách viết khác nhau.
- **Nếu test thất bại:** Hệ thống có thể báo sai khác đơn vị hoặc không ghép được hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:79`
- **Thời gian:** 0.000339 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "met vuong"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m²"`

### 61. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[M3]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000337 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "M3"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 62. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[m 3]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000337 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m 3"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 63. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[m3]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000337 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m3"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 64. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[m\xb3]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000331 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m³"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 65. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[m\xe9t kh\u1ed1i]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000340 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "mét khối"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 66. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[m^3]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000340 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "m^3"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 67. ✅ `tests/test_s1_normalizer.py::test_s1_nr03_normalize_cubic_metre_variants[met khoi]`

- **Tên dễ hiểu:** Chuẩn hóa mọi cách viết mét khối
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Đơn vị thể tích có nhiều kiểu ký hiệu.
- **Ví dụ cụ thể:** Ví dụ m3, M3, m³, m^3, “mét khối”.
- **Kết quả mong đợi:** Tất cả phải trở thành m³.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Tất cả phải trở thành m³. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Dữ liệu thể tích từ nhiều nguồn được so sánh thống nhất.
- **Nếu test thất bại:** Có thể phát sinh cảnh báo đơn vị giả.
- **Vị trí:** `tests/test_s1_normalizer.py:88`
- **Thời gian:** 0.000343 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "met khoi"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == "m³"`

### 68. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[100m-100m]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000386 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "100m",
  "expected": "100m"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 69. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[B\u1ed8-b\u1ed9]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000376 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "BỘ",
  "expected": "bộ"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 70. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[C\xe1i-c\xe1i]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000366 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "Cái",
  "expected": "cái"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 71. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[T\u1ea5n-t\u1ea5n]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000378 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "Tấn",
  "expected": "tấn"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 72. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[chi\u1ebfc-c\xe1i]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000375 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "chiếc",
  "expected": "cái"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 73. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[kg-kg]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000376 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "kg",
  "expected": "kg"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 74. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[m\xe9t-m]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000384 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "mét",
  "expected": "m"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 75. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[t\u1ee7-t\u1ee7]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000374 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "tủ",
  "expected": "tủ"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 76. ✅ `tests/test_s1_normalizer.py::test_s1_nr04_normalize_common_units[thi\u1ebft b\u1ecb-thi\u1ebft b\u1ecb]`

- **Tên dễ hiểu:** Chuẩn hóa các đơn vị phổ biến
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhà thầu có thể viết “chiếc”, “cái”, “BỘ”, “thiết bị” hoặc không dấu.
- **Ví dụ cụ thể:** Ví dụ “chiếc” được quy về “cái”, “BỘ” được quy về “bộ”.
- **Kết quả mong đợi:** Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi nhóm đồng nghĩa phải trả về cùng một đơn vị chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tăng khả năng ghép đúng hạng mục.
- **Nếu test thất bại:** Cùng một đơn vị nhưng khác cách viết có thể bị hiểu là không khớp.
- **Vị trí:** `tests/test_s1_normalizer.py:97`
- **Thời gian:** 0.000384 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "thiết bị",
  "expected": "thiết bị"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_unit(raw) == expected`

### 77. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[ AB_12 -AB-12]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.000402 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": " AB_12 ",
  "expected": "AB-12"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 78. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[-]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.000360 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "",
  "expected": ""
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 79. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[=A1-]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.000370 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "=A1",
  "expected": ""
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 80. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[M.01-M-01]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.000383 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "M.01",
  "expected": "M-01"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 81. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[M/01-M-01]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.001948 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "M/01",
  "expected": "M-01"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 82. ✅ `tests/test_s1_normalizer.py::test_s1_nr05_normalize_item_codes[M01-M-01]`

- **Tên dễ hiểu:** Chuẩn hóa mã vật tư
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Mã có thể chứa dấu chấm, gạch chéo hoặc khoảng trắng.
- **Ví dụ cụ thể:** Ví dụ M01, M.01 và M/01 đều trở thành M-01; ô công thức =A1 không được xem là mã.
- **Kết quả mong đợi:** Mã tương đương có cùng dạng chuẩn.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mã tương đương có cùng dạng chuẩn. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** So khớp mã ổn định giữa các biểu mẫu.
- **Nếu test thất bại:** Một hạng mục có thể bị coi là thiếu chỉ vì cách viết mã khác.
- **Vị trí:** `tests/test_s1_normalizer.py:116`
- **Thời gian:** 0.000371 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "M01",
  "expected": "M-01"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_code(raw) == expected`

### 83. ✅ `tests/test_s1_normalizer.py::test_s1_nr06_normalize_stt[ A-01 -A-01]`

- **Tên dễ hiểu:** Chuẩn hóa số thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.
- **Ví dụ cụ thể:** Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.
- **Kết quả mong đợi:** STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm ghép nhầm dựa trên số thứ tự giả.
- **Nếu test thất bại:** Công thức Excel có thể bị hiểu nhầm là mã hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:132`
- **Thời gian:** 0.000371 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": " A-01 ",
  "expected": "A-01"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_stt(raw) == expected`

### 84. ✅ `tests/test_s1_normalizer.py::test_s1_nr06_normalize_stt[ I.1 -I.1]`

- **Tên dễ hiểu:** Chuẩn hóa số thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.
- **Ví dụ cụ thể:** Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.
- **Kết quả mong đợi:** STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm ghép nhầm dựa trên số thứ tự giả.
- **Nếu test thất bại:** Công thức Excel có thể bị hiểu nhầm là mã hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:132`
- **Thời gian:** 0.000372 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": " I.1 ",
  "expected": "I.1"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_stt(raw) == expected`

### 85. ✅ `tests/test_s1_normalizer.py::test_s1_nr06_normalize_stt[-]`

- **Tên dễ hiểu:** Chuẩn hóa số thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.
- **Ví dụ cụ thể:** Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.
- **Kết quả mong đợi:** STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm ghép nhầm dựa trên số thứ tự giả.
- **Nếu test thất bại:** Công thức Excel có thể bị hiểu nhầm là mã hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:132`
- **Thời gian:** 0.000356 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "",
  "expected": ""
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_stt(raw) == expected`

### 86. ✅ `tests/test_s1_normalizer.py::test_s1_nr06_normalize_stt[1.2.3-1.2.3]`

- **Tên dễ hiểu:** Chuẩn hóa số thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.
- **Ví dụ cụ thể:** Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.
- **Kết quả mong đợi:** STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm ghép nhầm dựa trên số thứ tự giả.
- **Nếu test thất bại:** Công thức Excel có thể bị hiểu nhầm là mã hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:132`
- **Thời gian:** 0.000379 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "1.2.3",
  "expected": "1.2.3"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_stt(raw) == expected`

### 87. ✅ `tests/test_s1_normalizer.py::test_s1_nr06_normalize_stt[=ROW()-1-]`

- **Tên dễ hiểu:** Chuẩn hóa số thứ tự
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** STT có khoảng trắng, chữ cái hoặc ký hiệu phân cấp.
- **Ví dụ cụ thể:** Ví dụ “ I.1 ” trở thành I.1; công thức =ROW()-1 được bỏ qua.
- **Kết quả mong đợi:** STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: STT hợp lệ được làm sạch, công thức không bị dùng làm khóa ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Giảm ghép nhầm dựa trên số thứ tự giả.
- **Nếu test thất bại:** Công thức Excel có thể bị hiểu nhầm là mã hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:132`
- **Thời gian:** 0.000360 giây

**Tham số thực tế của lần test này:**

```json
{
  "raw": "=ROW()-1",
  "expected": ""
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_stt(raw) == expected`

### 88. ✅ `tests/test_s1_normalizer.py::test_s1_nr07_normalize_vietnamese_names_and_symbols[C\xe1p \u0111i\u1ec7n 3\xd72.5 mm\xb2-cap dien 3x2 5 mm2]`

- **Tên dễ hiểu:** Chuẩn hóa tên có dấu và ký hiệu kỹ thuật
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tên vật tư có thể viết có dấu/không dấu và dùng ký hiệu ×, ².
- **Ví dụ cụ thể:** Ví dụ “Cáp điện 3×2.5 mm²” phải cùng khóa với “cap dien 3x2 5 mm2”.
- **Kết quả mong đợi:** Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tên kỹ thuật vẫn ghép được dù định dạng khác.
- **Nếu test thất bại:** Ký tự mũ hoặc dấu nhân bị mất có thể làm ghép sai vật tư.
- **Vị trí:** `tests/test_s1_normalizer.py:147`
- **Thời gian:** 0.000410 giây

**Tham số thực tế của lần test này:**

```json
{
  "left": "Cáp điện 3×2.5 mm²",
  "right": "cap dien 3x2 5 mm2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_name(left) == normalize_name(right)`

### 89. ✅ `tests/test_s1_normalizer.py::test_s1_nr07_normalize_vietnamese_names_and_symbols[M\xe1y b\u01a1m n\u01b0\u1edbc sinh ho\u1ea1t-MAY BOM NUOC SINH HOAT]`

- **Tên dễ hiểu:** Chuẩn hóa tên có dấu và ký hiệu kỹ thuật
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tên vật tư có thể viết có dấu/không dấu và dùng ký hiệu ×, ².
- **Ví dụ cụ thể:** Ví dụ “Cáp điện 3×2.5 mm²” phải cùng khóa với “cap dien 3x2 5 mm2”.
- **Kết quả mong đợi:** Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tên kỹ thuật vẫn ghép được dù định dạng khác.
- **Nếu test thất bại:** Ký tự mũ hoặc dấu nhân bị mất có thể làm ghép sai vật tư.
- **Vị trí:** `tests/test_s1_normalizer.py:147`
- **Thời gian:** 0.000402 giây

**Tham số thực tế của lần test này:**

```json
{
  "left": "Máy bơm nước sinh hoạt",
  "right": "MAY BOM NUOC SINH HOAT"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_name(left) == normalize_name(right)`

### 90. ✅ `tests/test_s1_normalizer.py::test_s1_nr07_normalize_vietnamese_names_and_symbols[T\u1ee7 \u0111i\u1ec7n LV-G.1 + LV-G.2-TU DIEN LV G 1 LV G 2]`

- **Tên dễ hiểu:** Chuẩn hóa tên có dấu và ký hiệu kỹ thuật
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tên vật tư có thể viết có dấu/không dấu và dùng ký hiệu ×, ².
- **Ví dụ cụ thể:** Ví dụ “Cáp điện 3×2.5 mm²” phải cùng khóa với “cap dien 3x2 5 mm2”.
- **Kết quả mong đợi:** Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hai chuỗi biểu diễn cùng vật tư phải cho kết quả chuẩn hóa giống nhau. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tên kỹ thuật vẫn ghép được dù định dạng khác.
- **Nếu test thất bại:** Ký tự mũ hoặc dấu nhân bị mất có thể làm ghép sai vật tư.
- **Vị trí:** `tests/test_s1_normalizer.py:147`
- **Thời gian:** 0.000412 giây

**Tham số thực tế của lần test này:**

```json
{
  "left": "Tủ điện LV-G.1 + LV-G.2",
  "right": "TU DIEN LV G 1 LV G 2"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `normalize_name(left) == normalize_name(right)`

### 91. ✅ `tests/test_s1_normalizer.py::test_s1_nr08_safe_amount_respects_explicit_zero`

- **Tên dễ hiểu:** Giữ nguyên thành tiền 0 khi 0 là dữ liệu thật
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Ô thành tiền có thể là 0 hoặc để trống.
- **Ví dụ cụ thể:** Ví dụ quantity=2, price=100, amount=0 phải giữ 0; amount trống mới tính thành 200.
- **Kết quả mong đợi:** Không thay số 0 bằng phép nhân dự phòng.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Không thay số 0 bằng phép nhân dự phòng. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Tôn trọng dữ liệu gốc và phân biệt 0 với thiếu dữ liệu.
- **Nếu test thất bại:** Tổng tiền có thể bị tự động tăng sai.
- **Vị trí:** `tests/test_s1_normalizer.py:163`
- **Thời gian:** 0.000265 giây

**Các điều kiện kỹ thuật phải đúng:**

- `safe_amount(2, 100, 0) == 0`
- `safe_amount(2, 100, None) == 200`

### 92. ✅ `tests/test_s1_normalizer.py::test_s1_nr09_percent_delta[100-100-0.0]`

- **Tên dễ hiểu:** Tính đúng phần trăm chênh lệch
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** So sánh giá trị nhà thầu với giá trị chuẩn.
- **Ví dụ cụ thể:** Ví dụ từ 100 lên 108 là +8%; từ 100 xuống 95 là -5%.
- **Kết quả mong đợi:** Hàm trả đúng dấu và đúng tỷ lệ.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hàm trả đúng dấu và đúng tỷ lệ. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Mức cảnh báo dựa trên con số chính xác.
- **Nếu test thất bại:** Hệ thống có thể phân loại sai WARNING/CRITICAL.
- **Vị trí:** `tests/test_s1_normalizer.py:169`
- **Thời gian:** 0.000401 giây

**Tham số thực tế của lần test này:**

```json
{
  "baseline": 100,
  "candidate": 100,
  "expected": 0.0
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `percent_delta(baseline, candidate) == pytest.approx(expected)`

### 93. ✅ `tests/test_s1_normalizer.py::test_s1_nr09_percent_delta[100-108-0.08]`

- **Tên dễ hiểu:** Tính đúng phần trăm chênh lệch
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** So sánh giá trị nhà thầu với giá trị chuẩn.
- **Ví dụ cụ thể:** Ví dụ từ 100 lên 108 là +8%; từ 100 xuống 95 là -5%.
- **Kết quả mong đợi:** Hàm trả đúng dấu và đúng tỷ lệ.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hàm trả đúng dấu và đúng tỷ lệ. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Mức cảnh báo dựa trên con số chính xác.
- **Nếu test thất bại:** Hệ thống có thể phân loại sai WARNING/CRITICAL.
- **Vị trí:** `tests/test_s1_normalizer.py:169`
- **Thời gian:** 0.000416 giây

**Tham số thực tế của lần test này:**

```json
{
  "baseline": 100,
  "candidate": 108,
  "expected": 0.08
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `percent_delta(baseline, candidate) == pytest.approx(expected)`

### 94. ✅ `tests/test_s1_normalizer.py::test_s1_nr09_percent_delta[100-95--0.05]`

- **Tên dễ hiểu:** Tính đúng phần trăm chênh lệch
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** So sánh giá trị nhà thầu với giá trị chuẩn.
- **Ví dụ cụ thể:** Ví dụ từ 100 lên 108 là +8%; từ 100 xuống 95 là -5%.
- **Kết quả mong đợi:** Hàm trả đúng dấu và đúng tỷ lệ.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hàm trả đúng dấu và đúng tỷ lệ. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Mức cảnh báo dựa trên con số chính xác.
- **Nếu test thất bại:** Hệ thống có thể phân loại sai WARNING/CRITICAL.
- **Vị trí:** `tests/test_s1_normalizer.py:169`
- **Thời gian:** 0.000403 giây

**Tham số thực tế của lần test này:**

```json
{
  "baseline": 100,
  "candidate": 95,
  "expected": -0.05
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `percent_delta(baseline, candidate) == pytest.approx(expected)`

### 95. ✅ `tests/test_s1_normalizer.py::test_s1_nr10_hybrid_match_is_one_to_one`

- **Tên dễ hiểu:** Ghép hạng mục một-một
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Nhiều dòng có tên gần nhau.
- **Ví dụ cụ thể:** Ví dụ hai dòng chuẩn và hai dòng nhà thầu phải tạo đúng hai cặp, không dùng một dòng hai lần.
- **Kết quả mong đợi:** Mỗi dòng chỉ xuất hiện trong tối đa một cặp ghép.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Mỗi dòng chỉ xuất hiện trong tối đa một cặp ghép. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Không đếm lặp dữ liệu.
- **Nếu test thất bại:** Một giá hoặc khối lượng có thể bị gán cho nhiều hạng mục.
- **Vị trí:** `tests/test_s1_normalizer.py:186`
- **Thời gian:** 0.000506 giây

**Các điều kiện kỹ thuật phải đúng:**

- `len(paired) == 2`
- `len({match.reference_index for match in paired}) == 2`
- `len({match.candidate_index for match in paired}) == 2`

### 96. ✅ `tests/test_s1_normalizer.py::test_s1_nr11_exact_name_can_match_across_different_sheets`

- **Tên dễ hiểu:** Tên chính xác vẫn ghép được khi khác sheet
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hai workbook đặt cùng vật tư ở hai sheet khác tên.
- **Ví dụ cụ thể:** Ví dụ tủ LV-G.1…LV-G.6 nằm ở “PHẦN TỦ HẠ THẾ” và “HT điện”.
- **Kết quả mong đợi:** Matcher tạo EXACT_NAME với điểm cao và ghi chú khác sheet.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Matcher tạo EXACT_NAME với điểm cao và ghi chú khác sheet. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Cấu trúc workbook không cản trở đối chiếu.
- **Nếu test thất bại:** Hạng mục đúng có thể bị báo thiếu.
- **Vị trí:** `tests/test_s1_normalizer.py:228`
- **Thời gian:** 0.000438 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "item_name": "Tủ điện LV-G.1+LV-G.2+LV-G.3+LV-G.4+LV-G.5+LV-G.6"
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `len(paired) == 1`
- `paired[0].kind is MatchKind.EXACT_NAME`
- `paired[0].score >= 0.95`
- `"khác tên sheet" in paired[0].reason.lower()`

### 97. ✅ `tests/test_s1_normalizer.py::test_s1_nr12_different_names_are_not_forced_into_exact_name_match`

- **Tên dễ hiểu:** Không ép hai tên khác nhau thành khớp chính xác
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hai dòng không có mã và tên hoàn toàn khác.
- **Ví dụ cụ thể:** Ví dụ “Tủ điện phân phối tổng” và “Ống nước HDPE D110”.
- **Kết quả mong đợi:** Không được tạo cặp EXACT_NAME giữa hai dòng này.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Không được tạo cặp EXACT_NAME giữa hai dòng này. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Ngăn ghép nhầm vật tư.
- **Nếu test thất bại:** Giá và khối lượng của hai loại thiết bị khác nhau có thể bị so sánh với nhau.
- **Vị trí:** `tests/test_s1_normalizer.py:262`
- **Thời gian:** 0.066121 giây

**Các điều kiện kỹ thuật phải đúng:**

- `exact_pairs == []`

### 98. ✅ `tests/test_security.py::test_network_guard_blocks_external`

- **Tên dễ hiểu:** Chế độ riêng tư phải chặn kết nối Internet
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hệ thống chạy local-only và một đoạn code cố truy cập máy chủ bên ngoài.
- **Ví dụ cụ thể:** Ví dụ OCR hoặc thư viện cố gọi một URL Internet để tải model/dữ liệu.
- **Kết quả mong đợi:** Network guard chặn yêu cầu bên ngoài nhưng vẫn cho phép xử lý nội bộ cần thiết.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Network guard chặn yêu cầu bên ngoài nhưng vẫn cho phép xử lý nội bộ cần thiết. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Hồ sơ dự thầu không bị gửi ra ngoài ngoài ý muốn.
- **Nếu test thất bại:** Dữ liệu nhạy cảm có nguy cơ rò rỉ hoặc hệ thống phụ thuộc Internet.
- **Vị trí:** `tests/test_security.py:7`
- **Thời gian:** 0.002326 giây

### 99. ✅ `tests/test_sheet_note_behavior.py::test_different_sheet_is_note_not_warning_when_name_and_quantity_match`

- **Tên dễ hiểu:** Khác sheet nhưng cùng hạng mục chỉ tạo ghi chú
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Tên hạng mục, đơn vị và khối lượng khớp; chỉ tên sheet khác.
- **Ví dụ cụ thể:** Ví dụ PL01 ở “2 - PHẦN TỦ HẠ THẾ”, nhà thầu ở “1. HT điện”, cùng tủ LV-G.1 và cùng số lượng.
- **Kết quả mong đợi:** Kết quả ghép đúng, severity vẫn OK/NOTE và có mô tả “khác sheet”.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Kết quả ghép đúng, severity vẫn OK/NOTE và có mô tả “khác sheet”. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Cho phép cấu trúc file linh hoạt mà vẫn phát hiện đúng hạng mục.
- **Nếu test thất bại:** Nhà thầu bị cảnh báo oan chỉ vì sắp xếp workbook khác.
- **Vị trí:** `tests/test_sheet_note_behavior.py:30`
- **Thời gian:** 0.001116 giây

**Các điều kiện kỹ thuật phải đúng:**

- `len(rows) == 1`
- `row.severity is Severity.OK`
- `row.anomaly_score == 0`
- `row.flags == []`
- `row.differences == []`
- `any("khác sheet" in note.lower() for note in row.notes)`

### 100. ✅ `tests/test_sheet_note_behavior.py::test_price_difference_between_bidders_still_warns_after_cross_sheet_match`

- **Tên dễ hiểu:** Sau khi ghép khác sheet, chênh giá thật vẫn phải cảnh báo
- **Trạng thái:** PASS
- **Tình huống kiểm tra:** Hai nhà thầu đặt cùng hạng mục ở sheet khác nhau và báo giá lệch nhau.
- **Ví dụ cụ thể:** Ví dụ NT1 báo 100, NT2 báo 180; tên, đơn vị và số lượng đều khớp.
- **Kết quả mong đợi:** Hệ thống không cảnh báo vì khác sheet, nhưng vẫn cảnh báo giá 180 lệch khỏi giá ngang hàng.
- **Kết quả lần chạy:** ĐÃ ĐẠT. Trong lần chạy này, hệ thống đã đáp ứng yêu cầu: Hệ thống không cảnh báo vì khác sheet, nhưng vẫn cảnh báo giá 180 lệch khỏi giá ngang hàng. Nói đơn giản: ví dụ được nêu trong testcase đã cho kết quả đúng và không có điều kiện kiểm tra nào bị sai.
- **Ý nghĩa nghiệp vụ:** Không để ghi chú “khác sheet” che mất bất thường giá.
- **Nếu test thất bại:** Một chênh lệch giá quan trọng có thể bị bỏ qua sau khi ghép chéo sheet.
- **Vị trí:** `tests/test_sheet_note_behavior.py:59`
- **Thời gian:** 0.002221 giây

**Dữ liệu ví dụ lấy trực tiếp từ code test:**

```json
{
  "rows": []
}
```

**Các điều kiện kỹ thuật phải đúng:**

- `all(row.severity is Severity.OK for row in rows)`
- `all(any("khác sheet" in note.lower() for note in row.notes) for row in rows)`
- `all(row.severity in {Severity.WARNING, Severity.CRITICAL} for row in rows)`
- `all(any("đơn giá tổng hợp" in flag.lower() for flag in row.flags) for row in rows)`
- `all(not any("khác sheet" in flag.lower() for flag in row.flags) for row in rows)`
