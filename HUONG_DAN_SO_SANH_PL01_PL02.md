# Hướng dẫn so sánh PL01/PL02 và hồ sơ nhà thầu

## Dữ liệu đầu vào

Tải ít nhất một phụ lục:

- PL01: danh mục công việc, đơn vị và khối lượng mời thầu.
- PL02: yêu cầu vật tư, thương hiệu và xuất xứ.

Sau đó tải từ 2 file chào giá nhà thầu trở lên.

## Nguyên tắc

- PL01 là chuẩn công việc/khối lượng khi có.
- PL02 là chuẩn yêu cầu vật tư khi có.
- Các nhà thầu được so sánh ngang hàng.
- Không lấy nhà thầu đầu tiên làm chuẩn.
- Thương hiệu ngoài PL02 chỉ được đánh dấu cần thẩm định tương đương, không tự động kết luận không đạt.

## Kết quả

- Báo cáo tổng hợp nhiều sheet.
- Ma trận đơn giá và khối lượng.
- Danh sách thiếu/phát sinh.
- Cảnh báo dữ liệu và công thức.
- Bản sao từng file nhà thầu có `AI_TONG_QUAN`, `AI_KIEM_TRA`, `AI MỨC ĐỘ`, `AI LÝ DO`.

## Màu đánh dấu

- Xanh: không thấy sai lệch đáng kể.
- Vàng: cần xác nhận.
- Cam: sai lệch đáng kể.
- Đỏ: thiếu/phát sinh, lỗi công thức hoặc bất thường nghiêm trọng.

## `#REF!`

Hệ thống ghi rõ sheet, ô và công thức; không đổi lỗi thành 0 và không dùng ô lỗi để kết luận giá.
