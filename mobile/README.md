# AI Study Agent Mobile

Đây là frontend mobile theo định hướng giảng viên: Study Agent đóng vai trò trợ lý học tập đồng hành cùng sinh viên, kết hợp tri thức dùng chung của môn học với dữ liệu học tập riêng của từng user.

## Chạy trên Android Emulator

Yêu cầu: Node.js >= 22.13, Android Studio + Android Emulator.

```bash
cd mobile
npm install
npx expo start
```

Sau đó mở Android Emulator và bấm `a` trong terminal Expo.

## Kết nối Flask backend local

Android Emulator không dùng `127.0.0.1` để truy cập máy Windows. File `src/api.js` đang dùng:

```text
http://10.0.2.2:5000
```

Backend Flask cần chạy ở port 5000 và các endpoint `/api/mobile/*` sẽ được bổ sung ở bước backend tiếp theo.

## Các màn hình đã dựng

- Login
- Trang chủ trợ lý
- Môn học: tri thức chung + hồ sơ cá nhân
- Study Agent
- Quiz thông minh
- Lộ trình học cá nhân hóa

Hiện UI mobile đã dựng trước để chốt trải nghiệm. Bước tiếp theo là nối dữ liệu thật từ Flask API và bổ sung shared knowledge + personal learning memory.
