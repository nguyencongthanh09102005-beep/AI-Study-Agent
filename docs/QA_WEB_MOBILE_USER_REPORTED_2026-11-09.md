# Biên bản QA Web ↔ Mobile — 09/11/2026

## Phạm vi và mức độ chứng cứ

Đây là bản ghi kết quả **người dùng báo cáo đã thao tác thủ công** trên iPhone và Web; không phải kết quả do GitHub Actions chạy trên thiết bị thật. Người dùng chưa cung cấp phiên bản iOS, số hiệu thiết bị, ảnh/video và nhật ký cho từng ca, vì vậy không tự coi đây là kiểm chứng độc lập.

Bản `main` trước khi xử lý tinh chỉnh Web: `4067ba6da3fce57c39a2946117bb1148f2f9870c`. GitHub Actions trên commit này: **PASS** (run `42506854751`). Mọi chỉnh sửa sau mốc này phải có CI riêng.

## Kết quả QA thủ công do người dùng xác nhận

| Nhóm | Kịch bản | Kết quả báo cáo |
|---|---|---|
| Mobile | Chuyển 4 tab Tổng quan, Môn học, Lịch học, Cá nhân | PASS |
| Mobile | Tên môn dài, cắt/tràn chữ và nút bấm trên màn hình nhỏ | PASS |
| Mobile | Chat AI, bàn phím và nút gửi | PASS |
| Mobile | Cuộn danh sách Quiz/tài liệu | PASS |
| Mobile | Thông báo lỗi dễ nhìn | PASS |
| Đối chiếu Web/Mobile | Đăng nhập cùng tài khoản | PASS |
| Đối chiếu Web/Mobile | Đồng bộ Kế hoạch học | PASS |
| Đối chiếu Web/Mobile | Đồng bộ Timer | PASS |
| Đối chiếu Web/Mobile | Đồng bộ Quiz/điểm yếu | PASS |
| Đối chiếu Web/Mobile | Đồng bộ tài liệu, xem file PDF gốc trên iPhone | PASS |
| Đối chiếu Web/Mobile | Ngăn xem dữ liệu riêng của tài khoản khác | PASS |

Các luồng Timer, Chat AI, Quiz và mở PDF gốc trên Mobile cũng đã được người dùng xác nhận hoạt động ở các lượt thử trước đó.

## Các vấn đề được rà và xử lý trong đợt tinh chỉnh Web

1. **Biểu đồ giờ học:** trước đây dùng thời lượng dự kiến của buổi đã hoàn thành, không đọc dữ liệu timer. Đã chuyển sang ưu tiên số giây thực tế trong `study_session_tracking` nếu có; khi buổi đã hoàn thành nhưng chưa từng dùng timer, giữ thời lượng dự kiến với nhãn giải thích. Nếu Chart.js qua CDN không tải được, hiển thị số liệu theo ngày thay vì màn hình trống.
2. **Trạng thái lộ trình:** phân biệt buổi chưa có lịch, đã xếp lịch nhưng chưa xong, đã hoàn thành, và lịch cũ khác nguồn cần rà soát. Trạng thái nguồn không còn khớp có ưu tiên cảnh báo.
3. **Tài liệu Web:** hiển thị nút **Tải file** trực tiếp ở cả danh sách tài liệu cá nhân và dùng chung, giữ nguyên endpoint và kiểm tra quyền hiện tại.

Đợt này chỉ thay đổi Web/backend Dashboard, không đổi cơ chế timer, đăng nhập, tài liệu, lịch và Quiz Mobile.

## Rủi ro/chưa xử lý

- **npm audit:** lần kiểm tra do người dùng gửi ghi **5 cảnh báo Moderate** do chuỗi phụ thuộc Expo CLI / Expo Fingerprint đến `glob` và `minimatch`. `npm audit fix --force` được đề xuất nhưng sẽ hạ Expo từ SDK 58 xuống SDK 53, gây thay đổi phá vỡ tương thích. **Chưa vá**; không được ghi là 0 cảnh báo. Không thay `mobile/package.json` hay dữ liệu `mobile/package-lock.json` riêng trên máy người dùng.
- CI/Expo build không thay thế đánh giá độ đúng AI bằng tài liệu thật, kiểm thử công khai qua HTTPS, đo hiệu năng hay QA trên nhiều loại điện thoại.
- Tinh chỉnh Web vẫn cần người dùng xem lại bố cục thực trên trình duyệt sau cập nhật.

## Điều kiện kết thúc

- CI mới nhất trên `main` PASS.
- Người dùng mở Web để xác nhận biểu đồ, màu/trạng thái lộ trình và nút tải file.
- Giữ riêng nhóm cảnh báo npm để theo dõi và xử lý bằng bản cập nhật tương thích; **không dùng `npm audit fix --force` để làm số cảnh báo về 0**.
