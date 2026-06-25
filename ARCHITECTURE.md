# Kiến trúc HSMT Enterprise AI v8.3

```text
Giao diện web
   |
   +-- So sánh PL01/PL02 + nhiều HSDT
   +-- So sánh ngang nhiều HSDT
   +-- So sánh HSMT với nhiều HSDT
   +-- OCR PDF/ảnh scan
   |
API tiếp nhận file và tạo job riêng
   |
ThreadPoolExecutor giới hạn số job đồng thời
   |
   +-- Excel pipeline
   |     +-- đọc nhiều file song song
   |     +-- quét lỗi OOXML
   |     +-- chuẩn hóa tên/mã/đơn vị/số
   |     +-- ghép hạng mục
   |     +-- phát hiện bất thường
   |     +-- báo cáo + file đánh dấu + ZIP
   |
   +-- OCR pipeline
         +-- render và xoay trang
         +-- phát hiện lưới/bảng
         +-- nhận dạng ô chữ/số
         +-- fallback bảng/tài liệu
         +-- kiểm tra phép tính
         +-- Excel kiểm chứng + ảnh ô nghi ngờ + ZIP
```

Mỗi job được cô lập trong `runtime/jobs/<job_id>`. Trạng thái được ghi nguyên tử vào JSON để giao diện có thể theo dõi tiến trình mà không dùng chung dữ liệu giữa các người dùng.

## Luồng đối chiếu phụ lục theo số lượng hồ sơ

### Một hồ sơ nhà thầu

1. Đọc PL01/PL02 và hồ sơ nhà thầu.
2. Ghép hạng mục theo cấu trúc, mã, tên chuẩn hóa và ghép gần đúng.
3. Kiểm tra các trường có căn cứ trong phụ lục: hạng mục, mã, đơn vị, khối lượng và yêu cầu vật tư.
4. Bỏ qua hoàn toàn so sánh giá ngang hàng vì không có nhà thầu thứ hai.
5. Xuất báo cáo tổng, file đánh dấu và ZIP.

### Từ hai hồ sơ nhà thầu

1. Thực hiện đầy đủ quy trình đối chiếu phụ lục cho từng hồ sơ độc lập.
2. Gom các dòng đã ghép theo `canonical_id`.
3. Chỉ so sánh ngang các trường giá; không dùng bất kỳ nhà thầu nào làm chuẩn.
4. Khối lượng và thông tin kỹ thuật tiếp tục được đánh giá theo PL01/PL02, không tạo cảnh báo chéo giữa nhà thầu trong chế độ này.
