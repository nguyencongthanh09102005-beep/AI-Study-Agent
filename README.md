# AI Study Agent — Final MVP

Hệ thống trợ lý học tập full-stack sử dụng Flask + SQLite + Gemini API.

## Chức năng

- Đăng ký, đăng nhập, đăng xuất.
- Quản lý môn học: mã môn, tín chỉ, mục tiêu điểm và tiến độ tự động.
- Upload PDF/TXT/Markdown; gắn hoặc đổi môn học cho tài liệu.
- AI Chat dựa trên tài liệu; lịch sử từng cuộc trò chuyện được lưu trong SQLite.
- Tạo Quiz bằng Gemini từ tài liệu, theo môn học hoặc ôn riêng các chủ đề đang yếu.
- Quiz lưu topic/chapter cho từng câu, cập nhật điểm yếu theo số lần đúng/sai và tự gỡ khỏi danh sách yếu khi đã trả lời đúng đủ lần.
- AI Study Plan dùng đề cương dùng chung, tài liệu cá nhân, lịch sử Quiz, điểm yếu, mục tiêu điểm và Learning Profile để ưu tiên lộ trình.
- Shared Knowledge theo môn hỗ trợ nhập đề cương, ghi chú hoặc upload PDF/TXT/Markdown để nhiều sinh viên cùng mã môn tái sử dụng.
- Tài liệu có xem file thật, tóm tắt AI và fallback cục bộ nếu API tạm thời không phản hồi.
- Deadline & nhắc việc tích hợp trong Kế hoạch học.
- Dashboard lấy dữ liệu thật từ SQLite; biểu đồ tuần chỉ tính thời lượng của các task đã bấm Hoàn thành.
- Tiến độ môn học tự động: 60% mức hoàn thành Study Plan + 40% điểm Quiz trung bình (lấy điểm cao nhất của mỗi Quiz). Nếu chỉ có một nguồn dữ liệu thì dùng nguồn đó.

## Cách chạy Windows

```bat
run_windows.bat
```

Hoặc chạy thủ công:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Mở: `http://127.0.0.1:5000`

Có thể dùng `sample_data/ai_co_ban.txt` để test nhanh luồng Tài liệu → Quiz → AI Chat.

Tài khoản demo mặc định khi database mới được tạo:
- Email: `demo@study.local`
- Mật khẩu: `123456`

## Bật Gemini

Mở `.env` và điền:

```env
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODELS=gemini-3.7-flash,gemini-3.5-flash-lite
GEMINI_PRIMARY_RETRIES=2
```

Sau đó khởi động lại Flask.

Khi model chính gặp lỗi tạm thời như HTTP 429/503 hoặc timeout, hệ thống tự retry theo exponential backoff rồi chuyển sang các model dự phòng. Chat còn có fallback cục bộ từ tài liệu/kiến thức chung nếu toàn bộ model đều tạm thời không phản hồi.

## Lưu ý khi nộp

- Không nộp `.env` vì chứa API key.
- Không nộp `.venv`.
- Dùng `.env.example` để mô tả các biến môi trường cần thiết.
- PDF dạng ảnh scan chưa được OCR nên có thể không trích xuất được chữ.
- Đây là MVP phục vụ đồ án/thực tập, không phải hệ thống production.
