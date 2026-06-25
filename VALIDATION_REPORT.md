# Báo cáo kiểm thử HSMT Enterprise AI v8.3

Ngày kiểm tra: 25/06/2026

## Kết quả tự động

- `pytest -q`: **29/29 bài kiểm thử đạt**.
- `python -m compileall -q app.py cli.py core ocr security`: đạt.
- `node --check web/app.js`: đạt.
- API health trả phiên bản `8.3.0`.
- API `/api/compare-package` chấp nhận đúng một Phụ lục 01 và một hồ sơ nhà thầu.

## Quy tắc số lượng hồ sơ ở chức năng Phụ lục

### Một hồ sơ nhà thầu

- Cho phép chạy với một PL01 hoặc PL02 và đúng một hồ sơ nhà thầu.
- Không chạy so sánh giá ngang hàng.
- Không sinh các khác biệt có trường bắt đầu bằng `So sánh ngang hàng`.
- Vẫn xuất báo cáo tổng, file nhà thầu đã đánh dấu, manifest và gói ZIP.
- Audit ghi:
  - `peer_price_comparison_enabled = false`;
  - `peer_comparison_scope = disabled`;
  - mode tương ứng `PL01_ONLY_VS_SINGLE_HSDT`, `PL01_PL02_VS_SINGLE_HSDT` hoặc `PL02_ONLY_VS_SINGLE_HSDT`.

### Từ hai hồ sơ nhà thầu

- Mỗi hồ sơ vẫn được đối chiếu độc lập với PL01/PL02.
- So sánh ngang chỉ bổ sung cho các trường giá: đơn giá tổng hợp, thành tiền và các thành phần giá.
- Không tạo so sánh ngang cho khối lượng, đơn vị, vật tư, thương hiệu hoặc xuất xứ trong chế độ Phụ lục; các nội dung này được đánh giá theo phụ lục.
- Audit ghi `peer_price_comparison_enabled = true` và `peer_comparison_scope = price_only`.

## Kiểm thử bằng file thực tế

Đã chạy một hồ sơ Linh Anh với Phụ lục 01 thực tế:

- Phụ lục: `2025.10.12  PCO KLMT DIEN(2).xlsx`.
- Hồ sơ nhà thầu: `1. 2025.12.08 Chao gia ME Hacom Mall Linh Anh V2(1).xlsx`.
- Mode kết quả: `PL01_ONLY_VS_SINGLE_HSDT`.
- Tổng số dòng đối chiếu: `4.624`.
- Số khác biệt so sánh ngang: `0`.
- Báo cáo và ZIP được tạo thành công.

Hạng mục kiểm thử hồi quy:

`Tủ điện LV-G.1+LV-G.2+LV-G.3+LV-G.4+LV-G.5+LV-G.6`

- Phụ lục 01: sheet `2 - PHAN TU HA THE`.
- Linh Anh: sheet `1. HT điện`.
- Kiểu ghép: `EXACT_NAME`.
- Mức độ: `OK`.
- Cờ cảnh báo: trống.
- Ghi chú: `Khớp đúng hạng mục nhưng khác sheet: 2 - PHAN TU HA THE ↔ 1. HT điện`.

## Giao diện đã xác nhận

- Có thể chọn một file rồi mở trình chọn file lần nữa để thêm file tiếp theo.
- Danh sách file cũ không bị thay thế khi thêm file mới.
- Một file hiển thị rõ chế độ đối chiếu phụ lục, không so sánh giá.
- Từ hai file hiển thị rõ chế độ đối chiếu phụ lục kết hợp so sánh giá.
- Hai ngưỡng cảnh báo giá tự khóa khi chưa đủ hai hồ sơ trong chức năng Phụ lục.
- Chức năng `So sánh nhà thầu` độc lập vẫn yêu cầu tối thiểu hai hồ sơ và giữ đầy đủ so sánh ngang hiện có.

## Các file lõi đã sửa

- `app.py`: API Phụ lục nhận tối thiểu một hồ sơ; trả trạng thái chế độ so sánh giá trong kết quả.
- `core/tender_package.py`: hỗ trợ một hoặc nhiều hồ sơ, tách mode một nhà thầu và nhiều nhà thầu.
- `core/peer_analysis.py`: bổ sung chế độ `price_only` cho quy trình Phụ lục.
- `web/app.js`: thêm file theo kiểu tích lũy, xác thực một file, hiển thị trạng thái chế độ và khóa ngưỡng giá phù hợp.
- `web/index.html`, `web/styles.css`: cập nhật hướng dẫn và hộp thông báo chế độ.
- `cli.py`: `compare-package` nhận từ một `--hsdt`.
- `tests/test_optional_appendices.py`, `tests/test_package_mode.py`, `tests/test_app_capabilities.py`: kiểm thử hồi quy một nhà thầu, nhiều nhà thầu và API.
