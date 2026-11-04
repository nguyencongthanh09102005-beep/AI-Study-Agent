# Kiểm thử hiệu năng AI Study Agent (đo dữ liệu thật, không suy đoán)

## 1. Phạm vi đã chuẩn bị
- Công cụ: `scripts/loadtest.py` (Python `requests`, cài sẵn qua `requirements.txt`).
- Bốn kịch bản đọc: Dashboard Mobile, danh sách môn, tài liệu, thời khóa biểu Web.
- Tùy chọn `--chat`: đo API Chat đang dùng thực tế (`/api/chat`), **có gọi dịch vụ AI thật**.
- Mặc định: 10, 25, 50 người đồng thời; 20 yêu cầu/người; 3 lượt/mức, không bật Chat.
- Đầu ra: `ketqua_hieunang/tonghop.md`, `tonghop.csv`, `chitiet.csv`, `thongtin.json`.
- p50/p95 đo thời gian HTTP của yêu cầu thành công. Tỷ lệ lỗi tính mọi HTTP khác 2xx và lỗi mạng. Đây **không phải TTFB**. Các kịch bản đọc có một lượt làm nóng GET/người không tính vào mẫu.
- Các bài test trong CI chỉ chứng minh script hoạt động theo hợp đồng; **không tạo số liệu hiệu năng thực**.

## 2. An toàn dữ liệu: chạy trên thư mục dự án riêng

`app.py` dùng đường dẫn SQLite cố định: `data/study_agent.db` nằm **trong thư mục của app.py**. Không chạy Load Test trên bản chính đang lưu dữ liệu học tập.

Trên PowerShell, tạo **bản clone mới ở một thư mục khác** (không chép `data/` và `uploads/` của bản chính vào):

```powershell
cd ..
git clone https://github.com/nguyencongthanh09102005-beep/AI-Study-Agent.git AI-Study-Agent-LOADTEST
cd AI-Study-Agent-LOADTEST
py -m pip install -r requirements.txt
```

Mở terminal thứ nhất **trong bản clone**:

```powershell
$env:FLASK_HOST = "127.0.0.1"
$env:FLASK_PORT = "5000"
$env:FLASK_DEBUG = "0"
py app.py
```

Giữ Flask chạy, mở terminal thứ hai trong cùng thư mục clone.

## 3. Đo tải

Thử nhỏ trước (không gọi AI):

```powershell
py scripts/loadtest.py --users 2 --requests 3 --runs 1 --allow-setup-writes --note "Smoke test; Flask local; database mới"
```

Khi thử thành công, chạy kiểm thử chính:

```powershell
py scripts/loadtest.py --users 10 25 50 --requests 20 --runs 3 --allow-setup-writes --note "Commit: <SHA>; OS/CPU/RAM: <cau-hinh>; Flask local; SQLite TEST; localhost"
```

Lệnh chính gửi tổng cộng **20.400 yêu cầu GET được tính mẫu** (4 kịch bản × (10 + 25 + 50) × 20 × 3), chưa tính bước khởi tạo và làm nóng. Tùy máy có thể tải nặng. Không chạy trên máy chủ production hoặc dữ liệu thật.

Khi **chủ động chấp thuận tốn quota AI**, có thể đo riêng Chat nhẹ:

```powershell
py scripts/loadtest.py --users 1 --requests 1 --runs 1 --chat --chat-users 1 --chat-requests 2 --allow-setup-writes --out ketqua_chat --note "Chat API thật; 2 câu hỏi; môi trường TEST"
```

Lưu ý: lệnh Chat cũng đo lại 4 kịch bản GET ở mức đã cấu hình. `--chat-requests 2` chỉ tạo **2 lượt Chat AI có tính mẫu**, không warmup Chat.

## 4. Cách đưa vào báo cáo Chương 5

Chỉ sau khi lệnh chạy trên Flask thật thành công, đưa các cột của `tonghop.csv` vào bảng kết quả:
- kịch bản, người đồng thời, số mẫu;
- p50, p95, thời gian lớn nhất;
- tỷ lệ lỗi và thông lượng (HTTP 2xx/giây);
- ngày giờ, cấu hình CPU/RAM, phiên bản commit, backend Flask dev và SQLite.

Dán bảng từ `tonghop.md` vào báo cáo sau khi rà soát. Lưu `chitiet.csv` và `thongtin.json` làm minh chứng, **không commit các tệp chứa dữ liệu tài khoản, truy vấn riêng hoặc thông tin máy cá nhân**.

Không khẳng định hệ thống hỗ trợ 50 người ổn định chỉ vì script hoàn tất: phải đối chiếu p95, tỷ lệ lỗi và môi trường đo. Nếu toàn bộ yêu cầu đều lỗi, p50/p95 hiển thị `N/A`, không làm giả thời gian phản hồi.

## 5. So sánh Agent và Gemini trực tiếp là bài đo riêng

`evaluation/benchmark_agent_vs_gemini.py` cần `GEMINI_API_KEY` và chỉ gọi dịch vụ thật khi có `--live`. Câu hỏi mẫu trong `evaluation/cases_example.json` là **dữ liệu giả lập**, không thay thế giáo trình. Cần bộ 10–20 câu từ tài liệu thật, phản hồi hai nhánh, hai người chấm theo `docs/evaluation-protocol-c5.md` và lưu phiếu chấm độc lập. Không điền điểm, kết luận vượt trội hoặc trích dẫn giả khi chưa có thực nghiệm.

Xem mẫu biểu ghi kết quả tại `evaluation/human_review_template.md`.
