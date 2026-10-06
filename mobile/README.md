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

- Nếu chạy trên điện thoại thật, đổi `API_BASE_URL` trong `src/api.js` thành IP LAN của máy chạy Flask, ví dụ `http://192.168.1.10:5000`.
- Khi deploy thật, dùng domain HTTPS thay cho địa chỉ local.
