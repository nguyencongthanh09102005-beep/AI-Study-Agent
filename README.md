# AI Study Agent — Final MVP

Hệ thống trợ lý học tập full-stack sử dụng Flask + SQLite + Gemini API.

## Chức năng

- Đăng ký, đăng nhập, đăng xuất.
- Quản lý môn học: mã môn, tín chỉ, mục tiêu điểm và tiến độ tự động.
- Upload PDF/TXT/Markdown; gắn hoặc đổi môn học cho tài liệu.
- AI Chat dựa trên tài liệu; lịch sử từng cuộc trò chuyện được lưu trong SQLite.
- Tạo Quiz bằng Gemini từ tài liệu, theo môn học hoặc ôn riêng các chủ đề đang yếu.
- Quiz lưu topic/chapter cho từng câu, cập nhật điểm yếu theo số lần đúng/sai và tự gỡ khỏi danh sách yếu khi đã trả lời đúng đủ lần.
- AI Study Plan ưu tiên đề cương chuẩn dùng chung; nếu chưa có thì dùng đề cương cá nhân fallback, sau đó kết hợp tài liệu cá nhân, lịch sử Quiz, điểm yếu, mục tiêu điểm và Learning Profile để ưu tiên lộ trình.
- Shared Knowledge theo môn là lớp kiến thức chuẩn dùng chung và ở giao diện sinh viên chỉ đọc. Nếu môn chưa có đề cương chuẩn, sinh viên có thể chọn một tài liệu cá nhân của chính mình làm đề cương fallback; file này vẫn riêng tư và không được đưa vào Shared Knowledge.
- Tài liệu có xem file thật, tóm tắt AI và fallback cục bộ nếu API tạm thời không phản hồi.
- Deadline & nhắc việc tích hợp trong Kế hoạch học.
- Dashboard lấy dữ liệu thật từ SQLite; biểu đồ tuần chỉ tính thời lượng của các task đã bấm Hoàn thành.
- Tiến độ môn học tự động: 60% mức hoàn thành Study Plan + 40% điểm Quiz trung bình (lấy điểm cao nhất của mỗi Quiz). Nếu chỉ có một nguồn dữ liệu thì dùng nguồn đó.

## Admin và tài liệu dùng chung (Shared Knowledge)

Trang đăng nhập vẫn là `/login` với 3 lựa chọn: **Đăng nhập sinh viên**, **Tạo tài khoản sinh viên**, **Quản trị viên** (chỉ đăng nhập, KHÔNG có đăng ký Admin).

Tài khoản Admin được tạo **trực tiếp trên máy chạy Flask**, không có mật khẩu mặc định/công khai. Sau khi cài Python dependencies, mở Terminal trong thư mục gốc:

```bash
python scripts/create_admin.py --email admin@example.com --name "Quản trị viên"
```

Lệnh sẽ yêu cầu nhập mật khẩu hai lần, tối thiểu 10 ký tự (không hiện trên màn hình), rồi tạo tài khoản Admin trong SQLite cục bộ. Thay email bằng email do bạn kiểm soát, KHÔNG dùng email demo/mật khẩu dễ đoán. Chạy lệnh trên **máy chứa database thật** (`data/study_agent.db`), rồi chọn tab Quản trị viên tại `http://127.0.0.1:5000/login?tab=admin`. Sinh viên đăng ký bình thường luôn mang role `student`, không thể tự cấp quyền Admin. **Lưu ý:** script đã được bảo vệ để **từ chối** nếu email thuộc tài khoản sinh viên; tuyệt đối không chuyển vai trò hoặc ghi đè mật khẩu sinh viên. Nếu email thuộc tài khoản Admin sẵn có, chạy lại lệnh là đổi mật khẩu Admin.

### Khôi phục nếu từng dùng chung email để tạo tài khoản Admin

Trước bản sửa này, `scripts/create_admin.py` có thể ghi đè vai trò và mật khẩu của **chính tài khoản sinh viên**, gây lỗi khi đăng nhập tab Sinh viên. Dữ liệu học vẫn gắn với ID tài khoản cũ. **Đừng đăng ký lại sinh viên** vì tài khoản mới không có tài liệu đã lưu; **đừng xóa database**.

Để tách ra thành tài khoản sinh viên (email gốc) và Admin (email mới), trước tiên `git pull origin main`, **dừng Flask**, sau đó chạy trong thư mục gốc:

```bash
python scripts/restore_student.py --email student@gmail.com --admin-email student+admin@gmail.com
```

Ví dụ dùng `+admin` với Gmail như một địa chỉ email phụ nhưng vẫn nhận thư trong cùng hộp thư. Cũng có thể dùng một email khác do bạn kiểm soát. Script sẽ hỏi tên hiển thị sinh viên, mật khẩu **MỚI** cho sinh viên và mật khẩu **MỚI, KHÁC** cho Admin (đều >=10 ký tự). Mật khẩu cũ của sinh viên **không thể tự khôi phục** vì đã bị ghi đè bằng hash của Admin; hãy đặt mật khẩu mới mạnh và không dùng lại mật khẩu từng chia sẻ. Script **giữ nguyên user ID** và mọi dữ liệu học cá nhân, tự sao lưu database vào `data/study_agent_backup_before_account_recovery_*.db` trước khi sửa và từ chối chạy lại nếu tài khoản đã được khôi phục. Khởi động Flask lại, đăng nhập theo tab tương ứng. Không phải chạy script khôi phục này nếu bạn chưa từng gặp sự cố.



Giao diện Admin dùng **cùng giao diện, logo, sidebar và tông màu của Web sinh viên**, gồm **2 trang riêng biệt**: `/admin` để quản lý môn học và `/admin/documents` để quản lý tài liệu chung. Click từng mục trong sidebar mở trang tương ứng; upload/xóa file sẽ quay về trang tài liệu.
- **Quản lý môn học chung**: thêm môn (mã môn bắt buộc + tên + mô tả), bấm **Sửa** để chỉnh cả mã môn, tên môn và mô tả; bấm **Xóa** để xóa môn khỏi kho chung cùng tất cả tài liệu chung của môn (có xác nhận). Môn cá nhân, file cá nhân, Quiz, điểm yếu và kế hoạch của sinh viên vẫn được giữ nguyên. Nếu sửa **mã môn**, sinh viên có mã cũ sẽ không còn thấy tài liệu chung cho đến khi mã môn cá nhân được chỉnh khớp mã mới; mã trùng môn khác sẽ bị từ chối.
- **Quản lý tài liệu chung**: chọn môn, upload PDF/TXT/MD, tùy chọn đánh dấu đề cương chuẩn, xem/xóa tài liệu. Form giới hạn kích thước theo `MAX_UPLOAD_MB`.

Tài liệu dùng chung được trích xuất chữ ngay khi Admin tải lên và lưu kết quả trong `shared_documents` / `shared_knowledge`. Các tài khoản sinh viên có môn **trùng mã môn** tự thấy file chung ở trang Tài liệu và chi tiết môn (Web/Mobile). Chat AI và Quiz sử dụng văn bản đã trích xuất từ kho chung, không phải đọc PDF lại ở mỗi yêu cầu. **Đây là cache trích xuất PDF, không phải Gemini trả lời sẵn**; tạo câu trả lời và Quiz vẫn cần gọi Gemini. PDF scan ảnh chưa hỗ trợ OCR. Truy cập/xem file chung chỉ cho người có môn trùng mã hoặc Admin; tải lên/xóa bị kiểm tra quyền Admin và CSRF ở backend.

Kiểm thử: `python tests/test_admin_shared.py` sử dụng SQLite tạm, có 2 sinh viên chung mã môn và 1 sinh viên khác môn để xác minh phân quyền và tự đồng bộ. CI chạy tự động bài test này.

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

## Chạy Mobile bằng Expo Go

**iPhone Expo Go hiện dùng SDK 58; Mobile AI Study Agent đã nâng lên Expo SDK 58 (React Native 0.88, React 19.3).** Trên máy Windows phải dùng **Node.js 22.13 trở lên**: kiểm tra bằng `node -v` trước khi chạy. Nếu bản Node cũ, cập nhật Node.js rồi mở lại VS Code/Terminal. Không thay đổi Flask hoặc database chỉ vì nâng Expo.

Mobile dùng cùng Flask backend và SQLite với Web.

Android Emulator có thể dùng mặc định `http://10.0.2.2:5000`.

Với iPhone thật / Expo Go, điện thoại và laptop nên cùng Wi-Fi. Trong thư mục `mobile`, tạo file `.env` từ `.env.example` rồi thay IPv4 LAN của máy Windows:

```env
EXPO_PUBLIC_API_URL=http://192.168.1.15:5000
```

Flask phải lắng nghe LAN:

```env
FLASK_HOST=0.0.0.0
```

Sau đó:

```bash
cd mobile
npm install
npx expo install --check
npx expo start --clear
```

Mở Expo Go SDK 58 trên iPhone và quét QR. Nếu đổi `EXPO_PUBLIC_API_URL`, restart Expo để nạp lại biến môi trường. Nếu `npx expo install --check` báo lệch phiên bản, chạy `npx expo install --fix` rồi `npx expo-doctor@latest` và `npx expo start --clear`. Chỉ chạy các lệnh này trong thư mục `mobile`. Nếu có lỗi cache sau khi nâng SDK, tắt Expo, xóa thư mục `mobile/node_modules` (không xóa `data/` hoặc thư mục uploads), chạy lại `npm install`, sau đó khởi động Expo với `--clear`.

### Chức năng Mobile (React Native / Expo)

- Sinh viên đăng ký/đăng nhập và dùng chung tài khoản với Web; có nút Hiện/Ẩn mật khẩu. **Admin chỉ đăng nhập Web** bằng tab Quản trị viên, không có đăng ký Admin/Mobile Admin.
- Dashboard: thống kê môn/tài liệu/bài Quiz và đề xuất Next Best Action theo tiến độ thực tế.
- Môn học: tạo, sửa, xóa, mở chi tiết, xem điểm yếu và tiến độ.
- Tài liệu cá nhân: upload PDF/TXT/MD từ ứng dụng Tệp, xem chữ đã trích xuất, tóm tắt AI, đổi môn, xóa, chọn/bỏ đề cương fallback.
- Study Agent: chat theo môn và mở lại lịch sử câu hỏi đã lưu trên Web.
- Quiz: tạo theo môn/tài liệu/điểm yếu, chọn 10/20/30 câu, xem danh sách Quiz, làm lại, xem kết quả và đáp án.
- Lộ trình học: tạo AI Study Plan theo đề cương; lịch **Tuần** (chọn ngày, chuyển tuần, về hôm nay) và **Danh sách**; thẻ tiến độ/số giờ học của tuần; thêm/sửa/xóa/tick hoàn thành buổi học. Deadline chưa hoàn thành hiện trước, nhóm đã hoàn thành thu gọn/mở lại và vẫn có thể sửa/xóa/đánh dấu lại. Các deadline thủ công được giữ nguyên khi tạo lại kế hoạch AI.
- Hồ sơ: phong cách học, thời gian ưu tiên, thời lượng học, mục tiêu, ghi chú.

Đợt đồng bộ giao diện Mobile đã tăng độ tương phản chữ phụ/mô tả, cỡ chữ và nhãn thanh điều hướng, giữ bảng màu xanh–tím của Web. Web có chế độ lịch Tháng đầy đủ; Mobile ưu tiên lịch Tuần và Danh sách để vừa màn hình iPhone. Các phần dùng chung backend và SQLite với Web. Tài liệu cá nhân không được đưa lên Shared Knowledge. Mobile hiện hiển thị deadline/nhắc việc bên trong ứng dụng, **chưa có push notification nền**. PDF scan/ảnh chưa có OCR; màn đọc tài liệu trên Mobile hiển thị **văn bản trích xuất** thay vì trình xem trang PDF gốc.

### Kịch bản nghiệm thu một lần trên iPhone

1. Bật Flask và Expo, mở Expo Go cùng Wi-Fi.
2. Tạo tài khoản thử (hoặc đăng nhập Web account) từ Mobile.
3. Vào Môn học → tạo môn mới → chỉnh tín chỉ/mục tiêu.
4. Upload một file PDF/TXT có chữ → xem nội dung → tóm tắt → chọn làm đề cương cá nhân.
5. Mở Kế hoạch → chọn ngày trong lịch Tuần, chuyển sang Danh sách, xác nhận % tiến độ; tạo kế hoạch AI với deadline (nút chọn nhanh 7/14/30 ngày) và kiểm tra nhóm deadline đã hoàn thành có thể thu/mở.
6. Tạo buổi học thủ công → hoàn thành → kiểm tra tiến độ trên Mobile và Web.
7. Hỏi AI theo môn, kiểm tra lịch sử hiển thị trên Web.
8. Tạo Quiz theo môn/tài liệu; trả lời sai có chủ đích → kiểm tra điểm yếu và Adaptive task.
9. Mở Quiz ôn điểm yếu → trả lời đúng → kiểm tra tiến độ và đề xuất học tập thay đổi.
10. Tạo/sửa/xóa deadline, chỉnh hồ sơ; xác minh Web đọc được dữ liệu.
11. Đăng xuất, đăng nhập tài khoản thứ hai để xác nhận không thấy tài liệu, chat, quiz và kế hoạch riêng của tài khoản trước.

Các bài test CI sử dụng Flask test_client và Expo iOS export; **vẫn cần chạy thủ công trên iPhone thật** để xác nhận giao diện, quyền chọn tệp và trải nghiệm cảm ứng.


Có thể dùng `sample_data/ai_co_ban.txt` để test nhanh luồng Tài liệu → Quiz → AI Chat.

Tài khoản demo **chỉ tự tạo khi** đặt `DEMO_ACCOUNT_ENABLED=1` trong `.env` trước lần khởi tạo database:
- Email: `demo@study.local`
- Mật khẩu: `123456`

Mặc định `DEMO_ACCOUNT_ENABLED=0`, để tránh tự sinh tài khoản dùng chung mật khẩu yếu khi triển khai. Nếu database cũ đã có tài khoản demo, cần xóa hoặc đổi mật khẩu bằng biện pháp quản trị an toàn trước khi mở Internet. Khi chạy HTTPS production, dùng `SESSION_COOKIE_SECURE=1`. Khi demo qua HTTP LAN trên iPhone, giữ `SESSION_COOKIE_SECURE=0`.

### Chất lượng Quiz

Quiz yêu cầu đủ số câu hợp lệ từ Gemini. Nếu AI lỗi hoặc sinh thiếu, hệ thống báo lỗi để thử lại, **không tự bù bằng câu điền từ vô nghĩa**. Khi xóa Quiz hoặc tài liệu sinh Quiz, điểm yếu và nhiệm vụ Adaptive chưa hoàn thành được tính lại từ các lượt làm Quiz còn lại. Mobile thử khôi phục cookie session khi mở lại; nếu phiên không còn hợp lệ, người dùng đăng nhập lại.

## Tải tài liệu và lỗi 413

Tệp PDF/TXT/MD được giới hạn mặc định theo `MAX_UPLOAD_MB=50` trong `.env`.
Đây là giới hạn toàn bộ request HTTP (bao gồm multipart). Có thể thay đổi trong khoảng 5–100 MB rồi khởi động lại Flask.
Giao diện Web kiểm tra dung lượng khi chọn file; nếu quá giới hạn, hệ thống hiển thị thông báo thay cho trang lỗi trắng. API Mobile trả JSON kèm mã HTTP 413.
PDF ảnh scan vẫn chưa hỗ trợ OCR; tệp rất lớn có thể trích xuất chậm nên ưu tiên tài liệu PDF có chữ, hoặc chia theo chương.

## Bật Gemini

Mở `.env` và điền:

```env
GEMINI_API_KEY=YOUR_KEY
GEMINI_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_MODELS=gemini-3.6-flash,gemini-3.5-flash-lite
GEMINI_PRIMARY_RETRIES=2
GEMINI_REQUEST_TIMEOUT=25
```

Sau đó khởi động lại Flask.

Khi model chính gặp lỗi tạm thời như HTTP 429/503 hoặc timeout, hệ thống tự retry theo exponential backoff rồi chuyển sang các model dự phòng. Chat còn có fallback cục bộ từ tài liệu/kiến thức chung nếu toàn bộ model đều tạm thời không phản hồi.

## Lưu ý khi nộp

- Không nộp `.env` vì chứa API key.
- Không nộp `.venv`.
- Dùng `.env.example` để mô tả các biến môi trường cần thiết.
- PDF dạng ảnh scan chưa được OCR nên có thể không trích xuất được chữ.
- Đây là MVP phục vụ đồ án/thực tập, không phải hệ thống production.
