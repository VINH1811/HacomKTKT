# OCR chính xác cao — HSMT Enterprise AI v8.1

## Mục tiêu

Ưu tiên sai số âm thầm gần bằng 0 đối với số tiền, thay vì cố gắng tự động chấp nhận mọi ô.

## Kiến trúc

- Grid-first để giữ đúng hàng/cột.
- PP-OCRv6-medium đọc từng ô.
- Mọi ô số được chạy ensemble ở chế độ Ultra.
- PaddleOCR-VL-1.6 chạy toàn trang để kiểm tra chéo.
- Nếu hai model bất đồng, giữ kết quả có confidence tốt hơn nhưng bắt buộc đưa ô vào danh sách duyệt.
- PP-TableMagic và PP-StructureV3 xử lý trường hợp lưới hỏng hoặc bố cục phức tạp.

## GPU 20 GB

Cấu hình được tối ưu để chạy một job nặng tại một thời điểm. Tham số pixel cao giúp model nhìn rõ bảng rộng, nhưng không thể tái tạo nét chữ đã mất ở ảnh nguồn quá mờ.

## Công thức xác minh

- KLMT × đơn giá = thành tiền theo KLMT.
- Khối lượng nhà thầu × đơn giá = thành tiền nhà thầu.
- Tổng năm thành phần = đơn giá tổng hợp.
- Tổng chi tiết = tổng bảng tổng hợp.

Mọi phép tính sai hoặc ô bắt buộc trống đều được đánh dấu.

## PDF bị xoay ngang hoặc lộn ngược

Từ v8.1, hệ thống không chỉ dựa vào Tesseract OSD hoặc mật độ đường kẻ. Trước khi OCR toàn bảng, hệ thống đọc nhanh vùng đầu trang theo hai chiều 0° và 180°, sau đó chấm các cụm nghiệp vụ như `STT`, `Diễn giải`, `Khối lượng`, `Mã hiệu`, `Xuất xứ`, `Đơn giá`, `Thành tiền` và `Ghi chú`.

Cấu hình mặc định:

```env
HSMT_OCR_USE_OSD=1
HSMT_OCR_ORIENTATION_PROBE=1
HSMT_OCR_ORIENTATION_TOP_RATIO=0.30
HSMT_OCR_ORIENTATION_TARGET_WIDTH=3000
HSMT_OCR_ORIENTATION_MIN_GAP=6.0
HSMT_OCR_ORIENTATION_TIMEOUT=20
```

Trong sheet **Nhật ký OCR**, mục `page_sources` ghi:

- `rotation`: góc xoay cuối cùng;
- `orientation_method`: phương pháp quyết định;
- `orientation_scores`: điểm của hai chiều 0° và 180°;
- `orientation_keywords`: các cụm từ được nhận ra để làm bằng chứng.

Không nên tắt `HSMT_OCR_ORIENTATION_PROBE` với PDF scan ngang hoặc bảng BOQ có chữ nhỏ.
