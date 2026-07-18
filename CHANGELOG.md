# HSMT Enterprise AI v8.3

## 8.3.0

- **Bảo vệ khi bản chuẩn (PL01/HSMT) bị chọn nhầm hoặc không bao phủ phạm vi hồ sơ.** Trước đây, nếu nạp một PL01 sai phạm vi (ví dụ PL01 vài hạng mục đèn/công tắc cho hồ sơ vài nghìn hạng mục tủ điện/cáp), gần như MỌI hạng mục nhà thầu đều không ghép được → bị coi là "phát sinh ngoài" GIẢ → bị dồn hết xuống mục B, khiến **phần A rỗng ruột (chỉ còn tiêu đề nhóm và nhãn "Đầu vào:/Đầu ra:")** và file kết quả trở nên vô nghĩa. Nay hệ thống: (1) **CẢNH BÁO rõ** kèm tỷ lệ cụ thể (`4580/4585 (100%) hạng mục KHÔNG ghép được với Phụ lục 01 — rất có thể PL01 bị chọn nhầm...`); (2) **GIỮ NGUYÊN thứ tự file gốc** — không dời dòng nào xuống mục B, không tạo sheet sắp xếp/`— gốc` — ở cả file đánh dấu lẫn bảng tổng hợp. Ngưỡng nhận biết: hồ sơ có **từ 20 hạng mục trở lên** và **quá nửa số hạng mục không ghép được**; xét theo CẢ HỒ SƠ (bản chuẩn sai thì sai với mọi sheet). Hồ sơ nhỏ hoặc phát sinh thật (tỷ lệ thấp) không bị ảnh hưởng — phát sinh thật vẫn được dời xuống mục B như trước. Cảnh báo này bổ sung cho `low_match_warnings` (chỉ chạy khi bản chuẩn có ≥10 hạng mục, nên bỏ sót đúng trường hợp bản chuẩn quá nhỏ). **Ngay trong file đã đánh dấu**, sheet `AI_TONG_QUAN` nay có **banner đỏ nổi bật** giải thích vì sao KHÔNG có sheet sắp xếp (trước đây cảnh báo chỉ hiện trên web nên người dùng mở file lại tưởng mất tính năng).
- Bảng tổng hợp: BỎ cột **Ghi chú** trong block từng nhà thầu; sai lệch được đánh dấu (tô màu + chú thích) TRỰC TIẾP lên đúng ô lỗi. Sửa hiển thị số khối lượng: dùng định dạng `#,##0.###` (ẩn ba số 0 thừa, ví dụ `29.311` thay vì `29.311,000` gây hiểu nhầm hàng triệu) và nới rộng cột KL để không bị `########`. Cột **Mã hiệu** ở khối KLMT nay lấy mã của nhà thầu khi bản chuẩn PL01 để trống (với hạng mục mà chính file gốc không có mã — như cáp nhận diện theo mô tả — cột này vẫn trống đúng theo nguồn).

- Bảng tổng hợp (nhiều nhà thầu) nay đánh dấu ĐÚNG mọi ô có sai lệch bị gắn cờ — khớp với danh sách cảnh báo trên web, không bỏ sót: lệch **khối lượng, vật tư/quy cách, thương hiệu, xuất xứ, thành phần giá (VL chính/phụ, NC&M, quản lý, lợi nhuận), thành tiền theo KLMT** đều được tô màu + chú thích lên đúng ô. Sai lệch không có ô riêng (tên hạng mục, ĐVT, thông số) gom vào ô Ghi chú. (Trước đây chỉ tô ô đơn giá/thành tiền lệch và vi phạm PL02, nên có hạng mục cảnh báo trên web mà trong file không được đánh dấu.)
- File nhà thầu đã đánh dấu: sheet sắp xếp bám ĐÚNG cấu trúc **A / B / C** của file chào giá — CHỈ những hạng mục ĐƯỢC ĐÁNH DẤU phát sinh (không có trong PL01) đang nằm lẫn trong **phần A** mới được DỜI xuống **phần B (Phát sinh ngoài KLMT)**. Dòng đã khớp PL01 — dù đứng ngay sau một hạng mục phát sinh — KHÔNG bị dời theo (không cuốn cả khối). Giữ nguyên các mục B sẵn có; nếu file chưa có phần B thì tự tạo. Format y hệt bản gốc (sao chép nguyên style/đầu mục). Ba dòng tổng A/B/C được viết lại theo dải dòng mới (A, B là `SUBTOTAL`; C = A + B) nên số tiền luôn đúng; công thức thành tiền trong-dòng vẫn "sống". Sheet sắp xếp mang TÊN GỐC; bản gốc đổi thành `<tên> — gốc` (giữ nguyên toàn bộ) và mọi tham chiếu chéo (`Tổng hợp`, hyperlink `AI_KIEM_TRA`, chart) được viết lại trỏ đúng.
- Bảng tổng hợp (nhiều nhà thầu) tổ chức theo cấu trúc chuẩn **A / B** với tiêu đề rõ ràng: **A — ĐẦU MỤC CÔNG VIỆC THEO KLMT** (hạng mục khớp, xếp lại theo **số thứ tự STT của bản chuẩn** kể cả khi nhà thầu chào lệch thứ tự) và **B — HẠNG MỤC PHÁT SINH NGOÀI KLMT** (phát sinh dồn xuống cuối). Phân mục A/B tính theo CHÍNH từng dòng: chỉ dòng được đánh dấu phát sinh (không khớp PL01) mới xuống B; dòng đã khớp — dù đứng ngay sau một hạng mục phát sinh — vẫn ở mục A (không cuốn cả khối). Format giữ như file gốc (khối KLMT + block từng nhà thầu cạnh nhau) để so sánh nhiều nhà thầu.
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
