# QA thực tế trên iPhone — AI Study Agent Mobile

> Đây là checklist **chạy thủ công trên thiết bị**. CI/Expo export không thay thế được việc thao tác thật trong Expo Go. Không dùng tài liệu riêng tư thật hoặc tài khoản production khi chụp màn hình báo lỗi.

## Chuẩn bị

- [ ] Terminal 1, thư mục gốc: `python app.py`, server Flask đang chạy trên IP LAN.
- [ ] Điện thoại và laptop cùng Wi-Fi. Giữ cách cấu hình `mobile/.env` của dự án nếu bạn vẫn sử dụng nó.
- [ ] Terminal 2, thư mục `mobile`: `npx expo install --check` rồi `npx expo start -c`.
- [ ] Quét QR bằng Expo Go; đăng nhập tài khoản sinh viên **thử nghiệm**.
- [ ] Có một môn thử nghiệm và **1 file PDF có văn bản đọc được**, thêm một file chỉ có ảnh/scan nếu tiện.
- [ ] Tạo buổi tự học thủ công và gắn file cá nhân ở Kế hoạch học.

## 10 tình huống cần đánh dấu PASS / FAIL

| # | Thao tác trên iPhone | Kết quả mong đợi |
|---|---|---|
| 1 | Mở Mobile, chuyển qua 4 tab và vào Kế hoạch học | Không có màn hình trắng, mất nút hay tràn chữ |
| 2 | Bấm buổi tự học có gắn file từ Kế hoạch học | Mở Không gian tự học, hiện đúng tên môn / tiêu đề / tên file |
| 3 | Vào Home, bấm cùng buổi tự học trong mục sắp tới | Mở đúng Không gian tự học, không chuyển sang buổi học lộ trình |
| 4 | Bấm **Xem file gốc** với PDF (dưới 8 MB) | iOS mở file thật qua trình xem, không thấy chữ Base64, không bị hỏng PDF |
| 5 | Xem tài liệu dài và bấm **Xem thêm / Thu gọn**; chạm ô câu hỏi | Chữ và nút không bị cắt, bàn phím không che nút Hỏi Study Agent |
| 6 | Bấm **Bắt đầu học**, đợi 30 giây, **Tạm dừng**, rồi **Tiếp tục** | Trạng thái và thời gian không về 0, tăng theo thời gian học thực |
| 7 | Khi timer đang chạy, tạo Quiz 10 câu và chọn **Mở Quiz** | Timer được tạm dừng **trên server** trước khi chuyển sang Quiz |
| 8 | Từ Không gian tự học, mở lại Quiz đã tạo khi timer đang chạy | Cũng tạm dừng timer rồi mới chuyển trang; khi mất mạng thì không tự chuyển |
| 9 | Hỏi AI một câu **có căn cứ trong PDF** và một câu **không có trong PDF** | Có dẫn tên file; với câu thiếu thông tin phải nói thiếu căn cứ, không bịa |
| 10 | Tắt Wi-Fi trước lúc tạm dừng/hoàn thành, bật lại và tải lại | Hiện lỗi kết nối, không tự đánh dấu hoàn thành khi backend chưa xác nhận |

## Dữ liệu cần ghi nhận

Cho mỗi lỗi: ghi **bước số**, thiết bị/iOS, Expo Go version, tên màn hình, tình huống, ảnh hoặc video màn hình và dòng lỗi Terminal (ẩn địa chỉ hoặc dữ liệu cá nhân nếu cần).

**Tiêu chí kết thúc:** 10/10 tình huống PASS trên iPhone thật, thử ít nhất một PDF thật, không có lỗi P1 (sai quyền dữ liệu, sai giờ học, hỏng PDF, sai Quiz). Nếu chưa thử trên máy thật, trạng thái vẫn là **chưa xác nhận QA thiết bị**.

## Giới hạn có chủ ý

- File gốc >8 MB: app báo cần mở trên Web, không tải cả file lớn qua JSON.
- PDF scan không trích xuất được chữ: có thể mở file gốc, nhưng AI/Quiz không tự đọc được ảnh.
- AI và Quiz cần backend, kết nối mạng và mô hình AI có khả năng trả lời.
