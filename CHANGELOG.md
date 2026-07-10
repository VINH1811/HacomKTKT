# HSMT Enterprise AI v8.3

## 8.3.0

- Bảng tổng hợp giữ ĐÚNG cấu trúc sheet của **file nhà thầu (file gốc)** — ví dụ `1. HT điện`, `2. HT điện nhẹ`... Hạng mục khớp PL01 KHÔNG còn bị đổi sang tên sheet khó hiểu của PL01; chỉ dòng nhà thầu không chào (thiếu so với PL01) mới nằm ở sheet của PL01. Phát sinh nằm ở cuối đúng trang.
- File nhà thầu đã đánh dấu KHÔNG còn thêm cột `AI MỨC ĐỘ`/`AI LÝ DO`/`AI GHI CHÚ` bên cạnh dữ liệu; thay vào đó **tô màu và gắn chú thích (comment) trực tiếp lên ĐÚNG ô có sai lệch** — di chuột để xem. Chỉ đánh dấu đúng ô sai (tên khác thì bôi ô tên, khối lượng khác thì bôi ô khối lượng...), không bôi cả dòng. Hạng mục khớp — kể cả khớp nhưng khác tên sheet — không bị đánh dấu. Vẫn giữ hai sheet `AI_TONG_QUAN` và `AI_KIEM_TRA`.
- Cho phép chức năng đối chiếu phụ lục nhận một hoặc nhiều hồ sơ nhà thầu.
- Khi có một hồ sơ, chỉ kiểm tra theo PL01/PL02 và không tạo cảnh báo so sánh giá ngang hàng.
- Khi có từ hai hồ sơ, bổ sung so sánh ngang chỉ cho các trường giá; tên, đơn vị và khối lượng tiếp tục được kiểm tra riêng theo phụ lục.
- Giao diện cho phép thêm từng file qua nhiều lần mở trình chọn file mà không làm mất danh sách đã chọn.
- Hiển thị rõ chế độ một nhà thầu hoặc nhiều nhà thầu; tự khóa ngưỡng giá khi mới có một hồ sơ.
- Bổ sung mode/audit riêng cho đối chiếu một nhà thầu và trạng thái `peer_price_comparison_enabled`.

## 8.2.0

- Khác tên sheet/hệ thống chỉ được ghi vào **Ghi chú** và cột **AI GHI CHÚ**.
- Khác sheet không làm tăng điểm bất thường, không đổi mức độ và không xuất hiện trong `AI_KIEM_TRA`.
- Khi tên, đơn vị và khối lượng đúng, dòng giữ trạng thái `OK`; cảnh báo giá chỉ đến từ so sánh ngang giữa các nhà thầu.
- Bộ ghép tên chính xác hoạt động xuyên sheet; tên sheet chỉ là tín hiệu phụ.

# Changelog

## 8.1.0

- Sửa nhận dạng chiều 180 độ cho PDF scan ngang và bảng BOQ dày đặc.
- Thêm semantic header probe sử dụng vùng đầu trang thay cho confidence OCR đơn thuần.
- Tách ánh xạ tiêu đề thực nhận dạng khỏi positional schema để tránh chọn sai chiều.
- Ghi orientation method, score và keyword hits vào audit.
- Thêm kiểm thử hồi quy cho lựa chọn chiều trang.


## 8.0.0

- Hợp nhất lõi đọc Excel nhanh và xử lý song song của v7.6 với OCR của v7.5.
- Thiết kế lại toàn bộ giao diện theo quy trình đơn giản, rõ ràng.
- Bổ sung quét PDF/ảnh scan, tải từng file OCR và tải ZIP.
- Bổ sung hiển thị kết quả OCR theo từng tài liệu.
- Bổ sung lịch sử tác vụ gần đây trong trình duyệt.
- Bổ sung bộ requirements mặc định, CPU nâng cao và GPU.
- Bổ sung script khởi động Windows/Linux.
- Bổ sung README cài đặt, vận hành, hiệu năng, bảo mật và xử lý lỗi.
- Giữ nguyên kiểm tra `#REF!`, external links, so sánh ngang và file đánh dấu.
