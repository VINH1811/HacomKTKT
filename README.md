# HSMT Enterprise AI v8.3

Hệ thống hỗ trợ kiểm tra hồ sơ đấu thầu, so sánh nhiều hồ sơ nhà thầu, đánh dấu trực tiếp các dòng cần xem lại và quét PDF/ảnh scan sang Excel. Toàn bộ tác vụ được tách riêng theo mã công việc để nhiều người có thể sử dụng cùng lúc mà không ghi đè dữ liệu của nhau.

## Điểm mới trong v8.3

### Đối chiếu phụ lục với một hoặc nhiều nhà thầu

- Chức năng **Phụ lục & nhà thầu** nhận từ **một hồ sơ nhà thầu** thay vì bắt buộc tối thiểu hai file.
- Có thể mở trình chọn file nhiều lần để thêm từng hồ sơ; file đã chọn trước đó không bị thay thế.
- Khi chỉ có một hồ sơ, hệ thống đối chiếu riêng với dữ liệu có trong PL01/PL02: hạng mục, mã hiệu, đơn vị, khối lượng mời thầu, khối lượng chào, thương hiệu, xuất xứ và yêu cầu vật tư tương ứng.
- Khi có từ hai hồ sơ, hệ thống vẫn đối chiếu từng hồ sơ với phụ lục và chỉ bổ sung so sánh ngang các trường về giá giữa các nhà thầu.
- Ngưỡng cảnh báo giá trên giao diện tự khóa khi mới có một hồ sơ vì lúc đó chưa có đối tượng để so sánh giá ngang hàng.
- Nếu chỉ có PL02 mà không có PL01, hệ thống kiểm tra yêu cầu vật tư có trong PL02 nhưng không thể kết luận chính thức hạng mục thiếu/thừa hoặc chênh lệch khối lượng mời thầu.

### Quy tắc khác sheet

- Tên sheet khác nhau **không phải bất thường** khi hệ thống đã ghép đúng hạng mục.
- Nếu tên hạng mục, đơn vị và khối lượng khớp, dòng giữ mức `OK`.
- Thông tin khác sheet chỉ xuất hiện ở cột `Ghi chú` của báo cáo và `AI GHI CHÚ` trong file nhà thầu đã đánh dấu.
- Ghi chú khác sheet không làm tăng điểm bất thường, không xuất hiện trong `AI_KIEM_TRA` và không tính vào thống kê cảnh báo.
- Giá không so với Phụ lục 01. Cảnh báo giá được tạo bằng so sánh ngang giữa các nhà thầu.

### Cải tiến OCR được giữ nguyên

- Sửa lỗi PDF scan ngang bị chọn nhầm chiều 0/180 độ.
- OCR nhanh vùng tiêu đề để nhận biết các cụm `STT`, `Diễn giải`, `Khối lượng`, `Đơn giá`, `Thành tiền` trước khi đọc toàn bảng.
- Không còn dùng schema 19 cột làm bằng chứng chọn chiều trang.
- Nhật ký OCR ghi rõ phương pháp, điểm và từ khóa dùng để quyết định xoay.
- Đã kiểm tra bằng PDF scan thực tế `20260616045331942(2).pdf` gồm 2 trang bảng dày đặc.

## 1. Chức năng chính

### Đối chiếu Phụ lục 01/02 với một hoặc nhiều nhà thầu

- Chấp nhận PL01, PL02 hoặc đồng thời cả hai.
- Chấp nhận một hồ sơ để kiểm tra độc lập theo phụ lục.
- Khi có từ hai hồ sơ, bổ sung so sánh giá ngang hàng giữa các nhà thầu.
- PL01 dùng để kiểm tra tên hạng mục, mã, đơn vị, khối lượng mời thầu và khối lượng nhà thầu chào; không dùng giá trong PL01 làm giá chuẩn.
- PL02 dùng để kiểm tra vật tư, thương hiệu, xuất xứ và yêu cầu kỹ thuật có trong phụ lục.
- Nhận diện tên viết tắt hoặc cách trình bày khác nhau bằng chuẩn hóa và ghép gần đúng.
- Quét lỗi `#REF!`, lỗi công thức và liên kết đến workbook ngoài.
- Xuất báo cáo tổng, bản sao từng file nhà thầu đã tô màu và một gói ZIP đầy đủ.

### So sánh ngang nhiều nhà thầu

- Không lấy nhà thầu đầu tiên làm chuẩn.
- Tạo cụm hạng mục đồng thuận từ toàn bộ hồ sơ.
- So sánh min/median/max, độ lệch giá, khối lượng và thông số.
- Phát hiện điểm bất thường bằng thống kê bền vững.

### Đối chiếu một HSMT với nhiều HSDT

- Dùng HSMT làm nguồn yêu cầu.
- Kiểm tra một hoặc nhiều HSDT.
- Chỉ rõ thiếu mục, thừa mục, khác khối lượng, khác giá và khác thông số.

### OCR PDF hoặc ảnh scan sang Excel

- Nhận PDF, PNG, JPG, JPEG, TIFF, WEBP và BMP.
- Phát hiện bảng, hướng trang, hàng/cột và vùng ô.
- Nhận dạng riêng dữ liệu chữ và dữ liệu số.
- Kiểm tra lại phép tính, khối lượng, đơn giá và thành tiền.
- Tạo sheet dữ liệu chuẩn hóa, sheet thô theo từng bảng, danh sách ô cần kiểm tra và nhật ký OCR.
- Có thể chèn ảnh gốc của ô nghi ngờ ngay trong file Excel.
- Cho phép quét nhiều tài liệu và tải toàn bộ kết quả bằng ZIP.

## 2. Yêu cầu máy

- Python 3.11 hoặc 3.12.
- RAM tối thiểu 8 GB; khuyến nghị 16 GB trở lên khi xử lý Excel lớn.
- OCR cơ bản: CPU và Tesseract OCR.
- OCR nâng cao: khuyến nghị GPU NVIDIA và model đặt sẵn trong máy nội bộ.

## 3. Cài đặt nhanh trên Windows

Mở PowerShell tại thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Cài Tesseract OCR trên Windows. Sau đó mở `.env` và kiểm tra dòng:

```env
TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
```

Khởi động:

```powershell
.\start_windows.bat
```

Hoặc:

```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8004
```

Mở trình duyệt tại:

```text
http://localhost:8004
```

## 4. Cài đặt nhanh trên Ubuntu/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-vie
cp .env.example .env
./start_linux.sh
```

Mở:

```text
http://localhost:8004
```

## 5. Cài OCR nâng cao trên CPU

Gói nâng cao lớn hơn nhiều so với bản mặc định:

```bash
python -m pip install -r requirements-ocr-cpu.txt
```

Sau khi model đã được tải và lưu cục bộ, điền các đường dẫn tương ứng trong `.env`:

```env
HSMT_PADDLE_OCR_YAML=D:/HSMT_MODELS/config/ppocr_v6_medium_local.yaml
HSMT_PADDLE_REC_MODEL_DIR=D:/HSMT_MODELS/PP-OCRv6_medium_rec
HSMT_TABLEMAGIC_YAML=D:/HSMT_MODELS/config/tablemagic_v2_local.yaml
HSMT_PPSTRUCTURE_YAML=D:/HSMT_MODELS/config/ppstructure_v3_local.yaml
HSMT_PADDLE_VL_YAML=D:/HSMT_MODELS/config/paddleocr_vl_1_6_full_local.yaml
HSMT_PADDLE_VL_LAYOUT_MODEL_DIR=D:/HSMT_MODELS/PaddleOCR-VL-1.6-layout
HSMT_PADDLE_VL_MODEL_DIR=D:/HSMT_MODELS/PaddleOCR-VL-1.6
```

Không để chương trình tự tải model trong môi trường chứa tài liệu công ty.

## 6. Cài OCR GPU

1. Cài driver NVIDIA, CUDA và cuDNN phù hợp máy.
2. Cài `paddlepaddle-gpu` đúng phiên bản CUDA.
3. Cài phần còn lại:

```bash
python -m pip install -r requirements-ocr-gpu.txt
```

Cấu hình gợi ý:

```env
HSMT_OCR_DEVICE=gpu:0
HSMT_OCR_ACCURACY_MODE=high
HSMT_OCR_DPI=500
HSMT_OCR_UPSCALE=4
HSMT_OCR_BATCH_SIZE=64
HSMT_MAX_CONCURRENT_JOBS=1
HSMT_OCR_ALLOW_TESSERACT_ONLY=0
```

Với chế độ `ultra`, nên chạy một tác vụ OCR nặng tại một thời điểm để tránh hết bộ nhớ GPU.

## 7. Cách sử dụng giao diện

1. Chọn chức năng ở menu bên trái.
2. Chọn các file theo hướng dẫn trên màn hình.
3. Kiểm tra hoặc sửa tên nhà thầu.
4. Giữ nguyên ngưỡng cảnh báo mặc định hoặc mở phần thiết lập nâng cao.
5. Nhấn nút bắt đầu.
6. Chờ thanh tiến trình hoàn tất.
7. Tải báo cáo tổng, file đã đánh dấu hoặc gói ZIP.

Đối với OCR, nên dùng:

- `Nhanh`: tài liệu rõ, ít trang.
- `Cân bằng`: lựa chọn mặc định.
- `Chính xác cao`: bảng dày, số liệu nhỏ.
- `Tối đa`: tài liệu khó và máy đủ mạnh.

## 8. Chạy bằng dòng lệnh

### So sánh HSMT và HSDT

```bash
python cli.py compare \
  --hsmt "HSMT.xlsx" \
  --hsdt "NhaThauA=A.xlsx" \
  --hsdt "NhaThauB=B.xlsx" \
  --output "Bao_cao.xlsx"
```

### So sánh ngang nhiều nhà thầu

```bash
python cli.py compare-bidders \
  --hsdt "NhaThauA=A.xlsx" \
  --hsdt "NhaThauB=B.xlsx" \
  --output "Bao_cao_ngang.xlsx"
```

### So sánh PL01/PL02 và tạo file đánh dấu

Một hồ sơ nhà thầu:

```bash
python cli.py compare-package \
  --pl1 "PL01.xlsx" \
  --pl2 "PL02.xlsx" \
  --hsdt "NhaThauA=A.xlsx" \
  --output-dir "ket_qua_mot_nha_thau"
```

Từ hai hồ sơ trở lên, hệ thống bổ sung so sánh giá:

```bash
python cli.py compare-package \
  --pl1 "PL01.xlsx" \
  --pl2 "PL02.xlsx" \
  --hsdt "NhaThauA=A.xlsx" \
  --hsdt "NhaThauB=B.xlsx" \
  --output-dir "ket_qua"
```

### OCR một file

```bash
python cli.py ocr \
  --input "scan.pdf" \
  --output "scan_OCR.xlsx" \
  --accuracy balanced \
  --profile dense_boq
```

### OCR nhiều file

```bash
python cli.py ocr-batch \
  --input "scan_1.pdf" \
  --input "scan_2.jpg" \
  --output-dir "ket_qua_ocr" \
  --accuracy high
```

## 9. Cấu hình hiệu năng nhiều người dùng

```env
HSMT_MAX_CONCURRENT_JOBS=2
HSMT_EXCEL_READ_WORKERS=4
HSMT_EXCEL_WRITE_WORKERS=1
```

Nguyên tắc:

- `HSMT_MAX_CONCURRENT_JOBS`: số tác vụ độc lập chạy cùng lúc.
- `HSMT_EXCEL_READ_WORKERS`: số file Excel được đọc song song trong một tác vụ.
- Không nên đặt cả hai giá trị quá cao vì sẽ làm đầy RAM và giảm tốc độ tổng thể.
- OCR thường nặng hơn Excel; nếu dùng GPU, nên để số tác vụ đồng thời bằng 1.

## 10. Thư mục kết quả và tự xóa

Mỗi tác vụ được lưu riêng tại:

```text
runtime/jobs/<job_id>/
```

Mặc định kết quả được giữ 24 giờ:

```env
HSMT_JOB_RETENTION_HOURS=24
```

Có thể tăng hoặc giảm thời gian này trong `.env`.

## 11. Bảo mật

- Chế độ mặc định không cho phép kết nối mạng ngoài trong lúc xử lý tài liệu.
- Mỗi tác vụ có thư mục riêng.
- Tên file được làm sạch trước khi lưu.
- Có giới hạn kích thước tải lên.
- Chỉ cho tải các file thuộc đúng tác vụ.
- Tài liệu và kết quả cũ được tự dọn theo thời gian lưu cấu hình.
- Model OCR nâng cao phải được đặt sẵn trong máy hoặc máy chủ nội bộ.

## 12. Kiểm tra trước khi chạy thật

```bash
python -m pytest
python -m py_compile app.py cli.py core/*.py ocr/*.py
```

Kiểm tra cấu hình OCR/model:

```bash
python scripts/validate_models.py
python scripts/diagnose_scan.py --input "D:/TaiLieu/scan.pdf" --output "D:/TaiLieu/scan_diagnostic.json"
```

## 13. Lỗi thường gặp

### `No module named python_calamine`

```bash
python -m pip install python-calamine
```

### Không tìm thấy Tesseract

- Cài Tesseract OCR.
- Thêm thư mục Tesseract vào `PATH`, hoặc sửa `TESSERACT_CMD` trong `.env`.
- Trên Windows, kiểm tra đúng đường dẫn file `tesseract.exe`.

### PDF bị đọc lộn ngược hoặc xoay sai chiều

- Giữ `HSMT_OCR_ORIENTATION_PROBE=1` trong `.env`.
- Chạy `scripts/diagnose_scan.py` để xem điểm 0°/180°, từ khóa nhận được và góc xoay đề xuất.
- Trong file Excel kết quả, mở sheet **Nhật ký OCR** và kiểm tra `orientation_method`, `orientation_scores` và `rotation`.
- Nếu cả hai điểm đều thấp, scan có thể quá mờ; nên quét lại từ 300 DPI hoặc dùng PaddleOCR local.

### OCR báo không có engine local

- Kiểm tra Tesseract đã hoạt động.
- Hoặc cài OCR nâng cao bằng `requirements-ocr-cpu.txt`/`requirements-ocr-gpu.txt`.
- Kiểm tra các đường dẫn model trong `.env`.

### File Excel có `#REF!`

Hệ thống không thay `#REF!` bằng 0. Dòng lỗi được ghi vào báo cáo và bản sao đánh dấu để người dùng xác nhận.

### Tác vụ chạy chậm khi nhiều người cùng dùng

Giảm:

```env
HSMT_MAX_CONCURRENT_JOBS=1
HSMT_EXCEL_READ_WORKERS=2
```

Sau đó khởi động lại ứng dụng.
