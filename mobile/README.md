# AI Study Agent Mobile

Frontend mobile React Native/Expo dùng **chung backend Flask và cùng dữ liệu học tập với website**.

## Chạy backend Flask trên Windows

Trong file `.env`:

```env
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
```

Sau đó chạy:

```bash
python app.py
```

Android Emulator truy cập máy Windows qua `10.0.2.2`, nên `src/api.js` mặc định dùng:

```text
http://10.0.2.2:5000
```

## Chạy mobile

Yêu cầu Node.js + Android Studio/Android Emulator.

```bash
cd mobile
npm install
npx expo start
```

Mở Android Emulator rồi bấm `a` trong terminal Expo.

## Phần đã nối dữ liệu thật

- Đăng nhập bằng tài khoản Flask/SQLite.
- Dashboard: môn học, tiến độ, điểm yếu và lịch học.
- Danh sách môn học + weakness.
- Study Agent Chat dùng đúng tài liệu/shared knowledge/personal context của website.
- Quiz theo môn và Quiz ôn điểm yếu.
- Nộp Quiz cập nhật `learning_weaknesses` và tiến độ.
- Study Plan đọc dữ liệu thật từ backend.
- Mobile và web dùng cùng database SQLite.

## Lưu ý

- Nếu chạy trên iPhone thật, vào **Cài đặt kết nối** ngay trên màn hình đăng nhập, nhập IPv4 LAN thực của máy chạy Flask (ví dụ `http://192.168.1.10:5000`) và bấm **Kiểm tra và lưu kết nối**. Thay đổi này chỉ tạm thời; muốn giữ qua lần mở app sau, ghi URL thật vào `mobile/.env`.
- Khi deploy thật, dùng domain HTTPS thay cho địa chỉ local.


## Cập nhật Mobile – lộ trình, không gian học và bong bóng AI

- **Tổng quan:** truy cập buổi học từ lịch sắp tới nếu buổi đã liên kết lộ trình.
- **Môn học:** hiện các chương trong đề cương đã xác nhận, lịch theo buổi và liên kết vào học; CRUD và tài liệu vẫn dùng API cũ.
- **Kế hoạch học:** chuyển từ buổi học thuộc lộ trình sang Không gian học tập, cảnh báo trùng giờ trước khi thêm/sửa lịch; không tự chuyển giờ hay ghi đè lịch cũ.
- **Không gian học tập:** mục tiêu, tiểu mục, hoạt động, CLO và tên các học liệu chung được duyệt; timer Bắt đầu/Tạm dừng/Tiếp tục/Hoàn thành đồng bộ trực tiếp với cùng bảng phiên học của Web. Nội dung sai chữ ký lộ trình bị từ chối.
- **Bong bóng Chat AI:** nút 🤖 có thể kéo bên trong ứng dụng (iOS/Android Expo Go), nhấn mở khung chat, thu nhỏ không mất lịch sử. Chọn môn, sử dụng cùng `/api/mobile/chat` và lịch sử Web. Khi đang ở Không gian học tập có đủ nguồn được duyệt, Chat gửi câu hỏi vào bộ tutor `/api/chat` theo chính buổi học (có kiểm chứng nguồn).
- **Quiz & điểm yếu:** giữ các màn hình tạo/làm Quiz theo môn và tài liệu, có lối tắt tạo Quiz ôn điểm yếu. Bài Quiz định sẵn **15 câu mỗi buổi / 60 câu cuối môn** vẫn dùng quy trình Web hiện tại, chưa chuyển toàn bộ giao diện làm bài có khóa thời gian sang Mobile.

### Chạy trên iPhone thật qua Expo Go

1. Máy Windows và iPhone cùng mạng Wi-Fi.
2. Flask: đặt `FLASK_HOST=0.0.0.0` trong file `.env` (môi trường phát triển), rồi chạy `python app.py` ở thư mục gốc.
3. Tìm IPv4 của máy Windows bằng `ipconfig`.
4. Trong thư mục `mobile`, tạo/sửa file `.env` (không commit IP cá nhân):

   ```env
   EXPO_PUBLIC_API_URL=http://192.168.1.15:5000
   ```

   Thay IP minh họa bằng IPv4 thực của máy; **không dùng 127.0.0.1 hoặc 10.0.2.2 trên iPhone thật**.
5. Chạy `npm install` và `npx expo start -c`; mở Expo Go trên iPhone để quét mã QR.

### Kiểm thử thủ công bắt buộc

- Đăng nhập Mobile cùng tài khoản sinh viên đang có lộ trình hợp lệ trên Web.
- Kiểm tra môn học → lộ trình → buổi được lên lịch → Không gian học tập → timer. Đổi màn hình và mở lại buổi: trạng thái timer phải lấy từ máy chủ, không tự cộng giờ giả.
- Mở nút 🤖 tại trang Tổng quan, Môn học, Quiz, Lịch học; gửi câu hỏi thường rồi so lịch sử với Chat Web.
- Mở một buổi **có học liệu chương được Admin duyệt** và hỏi AI theo buổi: phải có trích dẫn đúng chương; buổi thiếu học liệu không được tự giả làm đã có nguồn.
- Thử tạo hai buổi trùng giờ: cảnh báo hiện trước khi lưu; Hủy giữ nguyên lịch cũ.
- Thử đăng nhập tài khoản khác: tuyệt đối không xem được lộ trình, phiên học, học liệu cá nhân của người trước.
- Thử cả iPhone và Android nếu có máy; kiểm tra bàn phím khi mở Chat, kéo bong bóng và thay đổi hướng màn hình.

Giới hạn: Bong bóng chỉ nổi **bên trong AI Study Agent**, không phủ lên ứng dụng khác. Expo build và CI không thay thế kiểm thử cảm ứng/thiết bị thật.


## Giao diện tối giản (2026-10-31)

- Thanh điều hướng dưới: **Tổng quan – Môn học – Lịch học – Cá nhân** (4 tab).
- AI Chat giữ bong bóng kéo được trên mọi tab; thẻ gợi ý trên Tổng quan mở thẳng bong bóng, không còn tab Chat trùng lặp.
- Quiz không bị xóa: mở ở chi tiết môn học qua **Làm Quiz & Ôn điểm yếu**, từ Không gian học tập hoặc Cá nhân → **Kết quả Quiz & điểm yếu**. Giữ các API làm/lưu Quiz hiện tại.
- Màn hình Môn học có ô tìm kiếm và lọc theo tiến độ; trong chi tiết môn, đề cương/lộ trình, tài liệu và điểm yếu được mở khi cần.
- Cá nhân hiển thị mục cài đặt; phần sửa phong cách, giờ học, mục tiêu chỉ mở khi chọn **Tùy chỉnh học tập**.
- Đăng nhập chỉ giữ tên, email, mật khẩu, đăng ký dạng liên kết và **Cài đặt kết nối máy chủ**. IP không còn hiện trên giao diện đăng nhập.
- Màn hình Cài đặt kết nối chấp nhận 401 từ `/api/mobile/session` như một kết nối thành công khi chưa đăng nhập, nhưng không coi HTTP 500 là thành công.

**Giới hạn:** Địa chỉ kết nối chỉnh trong app chưa được lưu bền vững sau khi ứng dụng đóng hoàn toàn; cấu hình chính thức vẫn là `EXPO_PUBLIC_API_URL` trong `mobile/.env`. Không chuyển các luồng học liệu cá nhân hay Chat sang backend thứ hai.
