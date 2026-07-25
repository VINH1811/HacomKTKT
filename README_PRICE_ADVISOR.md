# PriceAdvisor Enterprise AI v1.0 (Tư vấn đơn giá vật tư MEP)

Hệ thống tích hợp RAG (Retrieval-Augmented Generation) kết hợp cơ sở dữ liệu thầu lịch sử (PostgreSQL/SQLite) và mô hình ngôn ngữ lớn (Local LLM/Cloud LLM) để tự động hóa việc thẩm định đơn giá vật tư cơ điện (MEP). Hệ thống giúp phát hiện nhanh các đơn giá bất thường (chênh lệch quá cao hoặc quá thấp so với lịch sử thầu và giá thị trường trực tuyến).

---

## Các đặc tính nổi bật

### Tìm kiếm vector tương đồng (RAG)
- Sử dụng tìm kiếm vector tương đồng trên PostgreSQL (yêu cầu extension `pgvector`) hoặc SQLite (sử dụng thư viện `numpy` tính khoảng cách cosine cosine similarity).
- Tự động chuyển đổi tên vật tư/thiết bị thành vector biểu diễn ngữ cảnh 512 chiều để tìm kiếm chính xác các thầu cũ có mô tả tương đồng mà không bị phụ thuộc vào từ khóa gõ chính xác.

### Khai thác mô hình suy luận sâu (Reasoning LLM)
- Tối ưu hóa cho các mô hình suy luận cục bộ như `qwen3:14b` hoặc `deepseek-r1` chạy qua Ollama.
- Đã được tinh chỉnh tham số trần token sinh ra (`num_predict=4096`) giúp mô hình có không gian thực hiện các suy luận ngầm (thinking process) cực kỳ chi tiết trước khi đưa ra câu trả lời JSON chuẩn hóa.

### Web Search RAG (Tra cứu giá thị trường)
- Tự động gọi API tra cứu thông tin trực tuyến (DuckDuckGo Search) để lấy giá bán lẻ thực tế của vật tư ngoài thị trường.
- Tổng hợp khoảng giá thị trường làm thước đo so sánh độc lập với các dữ liệu thầu nội bộ.

### Hậu kiểm chống ảo giác (Validator & Egress Guard)
- Bộ lọc bảo mật EgressGuard đảm bảo dữ liệu gửi cho AI được làm sạch, tránh lộ thông tin nhạy cảm.
- Bộ thẩm định Validator tự động kiểm tra kết quả AI: phát hiện đơn vị tính bị lệch, chặn khoảng giá ngược (min > max) và tự động hạ điểm tin cậy nếu dữ liệu RAG lịch sử quá mỏng.

---

## 1. Chức năng chính

### Dự đoán đơn giá vật tư tự động
- Cho phép người dùng nhập tên vật tư, đơn vị tính và giá thầu chào.
- AI sẽ phân tích và đưa ra khoảng giá đề xuất an toàn (Cận dưới và Cận trên thầu nội bộ).
- Đưa ra điểm tin cậy (%) và lập luận lý do đề xuất rõ ràng.

### Đối chiếu dữ liệu thầu lịch sử
- Truy xuất và hiển thị danh sách các thầu cũ giống nhất (bao gồm Tên vật tư lịch sử, Quy cách kỹ thuật, Đơn giá thầu, Thương hiệu, Nhà thầu và Tên dự án tương ứng).

### So sánh chéo giá thị trường trực tuyến
- Hiển thị dải giá thị trường và các đường link trích dẫn nguồn giá để người kiểm soát bấm vào xem trực tiếp trang web gốc.
- Đưa ra nhận xét tự động: Nhà thầu đang chào cao hơn/thấp hơn bao nhiêu % so với mặt bằng lịch sử và thị trường, từ đó đưa ra khuyến nghị đàm phán.

### Ghi nhận phản hồi (Feedback Loop)
- Cho phép người dùng bấm duyệt (Accept) hoặc từ chối (Reject) giá đề xuất của AI để lưu trữ dữ liệu huấn luyện cục bộ.

---

## 2. Yêu cầu hệ thống

- Python 3.10 trở lên (Khuyến nghị **Python 3.11**).
- Thư viện kết nối CSDL: `psycopg2-binary` (đối với PostgreSQL) hoặc `sqlite3` có sẵn.
- **Ollama** cài đặt cục bộ (nếu sử dụng AI Offline).
- Tài nguyên máy khi chạy Local AI: Khuyến nghị RAM 16 GB trở lên và Card đồ họa rời (NVIDIA GPU) để Qwen3 phản hồi nhanh dưới 10 giây.

---

## 3. Cài đặt nhanh trên Windows

Mở PowerShell tại thư mục dự án `c:\KHMT\HacomHoldings\HacomKTKT`:

### Bước 1: Khởi tạo và kích hoạt môi trường conda chuẩn của dự án
```powershell
conda env create -f environment.yml
conda activate hsmt-enterprise-v8
```

### Bước 2: Cài đặt thư viện kết nối cơ sở dữ liệu PostgreSQL
```powershell
pip install psycopg2-binary
```

### Bước 3: Cài đặt máy chủ AI cục bộ (Ollama)
1. Tải và cài đặt Ollama từ: https://ollama.com/
2. Mở Command Prompt chạy lệnh để tải mô hình Qwen3 14B:
   ```cmd
   ollama run qwen3:14b
   ```

---

## 4. Thiết lập cấu hình `.env`

Sao chép tệp cấu hình `.env` và mở lên điều chỉnh các tham số cấu hình riêng cho PriceAdvisor:

```env
# Kích hoạt module PriceAdvisor (1: Bật, 0: Tắt)
PRICE_ADVISOR_ENABLED=1

# Cấu hình Cơ sở dữ liệu thầu (postgres hoặc sqlite)
PRICE_ADVISOR_DB_PROVIDER=postgres
PRICE_ADVISOR_DB_HOST=localhost
PRICE_ADVISOR_DB_PORT=5432
PRICE_ADVISOR_DB_NAME=priceadvisor
PRICE_ADVISOR_DB_USER=postgres
PRICE_ADVISOR_DB_PASSWORD=your_password_here

# Cấu hình nhà cung cấp LLM (ollama | google | openai)
PRICE_ADVISOR_LLM_PROVIDER=ollama
PRICE_ADVISOR_LLM_MODEL=qwen3:14b
PRICE_ADVISOR_BASE_URL=http://localhost:50050
PRICE_ADVISOR_LLM_TEMPERATURE=0.1
PRICE_ADVISOR_LLM_MAX_TOKENS=4096
PRICE_ADVISOR_LLM_THINK=1

# Cấu hình nhà cung cấp Embeddings (local | google | openai)
PRICE_ADVISOR_EMBEDDING_PROVIDER=local
PRICE_ADVISOR_EMBEDDING_MODEL=all-MiniLM-L6-v2
PRICE_ADVISOR_EMBEDDING_DIMENSIONS=512
```

---

## 5. Các tập lệnh bổ trợ (Command Line Tools)

### A. Tiền xử lý dữ liệu thầu Excel thô
Hệ thống hỗ trợ quét các file chào giá thô của các nhà thầu gửi đến, tự động bóc tách đơn giá tổng hợp, hãng sản xuất và gộp tên nhà thầu tương ứng:
```powershell
python scripts/preprocess_raw_data.py
```
*(Kết quả file Excel sạch sẽ được lưu tại `data/cleaned_prices.xlsx`)*

### B. Nạp dữ liệu Excel sạch vào CSDL PostgreSQL
```powershell
python scripts/import_price_data.py --input data/cleaned_prices.xlsx
```

### C. Dọn sạch dữ liệu cũ trong CSDL
```powershell
python scratch/clear_price_records.py
```

### D. Chạy thử nghiệm chẩn đoán đơn giá bằng dòng lệnh
Chẩn đoán trực tiếp RAG và cuộc gọi LLM cho một vật tư cụ thể:
```powershell
python scratch/diagnose_predict.py
```

---

## 6. Cách sử dụng giao diện Web

1. Đảm bảo máy chủ Web đang chạy:
   ```powershell
   conda run -n hsmt-enterprise-v8 python -m uvicorn app:app --host 0.0.0.0 --port 8004
   ```
2. Mở trình duyệt truy cập: `http://localhost:8004`
3. Chọn mục **Dự đoán giá AI** ở cuối thanh Sidebar.
4. Nhập đầy đủ thông tin:
   - **Mô tả vật tư / Thiết bị:** Nhập tên chi tiết (Ví dụ: `Dây cáp điện Cu/XLPE/PVC (1x240)mm2`).
   - **Đơn vị tính (ĐVT):** Nhập đúng đơn vị đo (Ví dụ: `m` hoặc `bộ`).
   - **Đơn giá nhà thầu chào:** Không bắt buộc, dùng để đối chiếu so sánh chênh lệch phần trăm.
5. Chọn mô hình xử lý (**Ollama Local** hoặc **Gemini**) và nhấn **Bắt đầu phân tích**.
6. Kết quả khoảng giá đề xuất cùng lập luận phân tích và bảng thầu lịch sử sẽ hiển thị trực quan trên màn hình.
