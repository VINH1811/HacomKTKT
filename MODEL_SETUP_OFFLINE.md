# Cài model OCR offline — GPU khoảng 20 GB

## Bộ model sử dụng

1. `PP-OCRv6_medium` cho phát hiện và nhận dạng chữ/số chính.
2. `PaddleOCR-VL-1.6-0.9B` cho kiểm tra chéo toàn trang và vùng bảng khó.
3. `PP-TableMagic` cho cấu trúc bảng.
4. `PP-StructureV3` cho tài liệu có bố cục hỗn hợp.
5. Tesseract 5 chỉ là kiểm tra chéo dự phòng.

## Phiên bản phần mềm

```powershell
pip install "paddleocr[doc-parser]==3.7.0"
```

Cài `paddlepaddle-gpu` đúng CUDA của máy theo hướng dẫn chính thức.

## Quy trình bảo mật

Trên máy staging có Internet:

1. Tải model từ nguồn chính thức.
2. Ghi SHA-256 cho từng thư mục hoặc gói model.
3. Quét mã độc.
4. Chuyển model qua kho nội bộ.
5. Máy production đặt:

```env
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HSMT_ALLOW_NETWORK=0
```

Không để PaddleOCR tự tải model trong lần chạy production đầu tiên.

## Cấu hình GPU 20 GB

Dùng `.env.example` làm mẫu. `bf16` chỉ phù hợp khi GPU hỗ trợ; nếu không, đổi sang `fp16`.

Giữ `HSMT_PADDLE_VL_MAX_CONCURRENCY=1` để dành VRAM cho ảnh bảng độ phân giải cao. Nếu chạy đồng thời nhiều job, mỗi job phải có GPU riêng hoặc giảm giới hạn pixel.
