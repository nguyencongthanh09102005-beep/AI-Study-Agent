# Phiếu nghiệm thu — Trang Chi tiết môn học (bố cục 50/50)

**Nhánh:** `feature/phase9-fixes`. Không chỉnh hoặc merge vào `main`.

## 1. Chuẩn bị

Lưu các sửa đổi chưa commit, đặc biệt trong `mobile/.env.example` và `mobile/package-lock.json`, trước khi chuyển nhánh:

```powershell
git status
git fetch origin
git switch --track origin/feature/phase9-fixes
python tests/test_course_overview_refresh.py
python tests/test_adaptive_phase8.py
python tests/test_final_qa.py
python app.py
```

Nếu nhánh đã tồn tại local, dùng `git switch feature/phase9-fixes`, rồi `git pull --ff-only`. Sau đó vào một môn đã có đề cương trên Web.

## 2. Bảng tự kiểm tra

| ID | Thao tác | Kết quả mong đợi |
|---|---|---|
| S1 | Mở Chi tiết môn học | Đầu trang còn 2 thao tác chính; không hiện dòng mô tả giả khi chưa có mô tả |
| S2 | Nhấn Học / Ôn ngay khi Agent xác định cần ôn | Tới Quiz ôn điểm yếu đúng môn |
| S3 | Nhấn Tiếp tục học khi có roadmap hợp lệ và không cần ôn | Vào buổi học tiếp theo, không tự sửa lịch |
| S4 | Chọn Đề cương & lộ trình | Mở trang phân tích/chốt chương; nút lộ trình và đưa vào lịch vẫn nằm trong luồng |
| S5 | Trang Chi tiết trên màn hình lớn | Đề cương trái 50%, Tài liệu theo chương phải 50%, khoảng cách hợp lý |
| S6 | Mở môn có PDF chuẩn do Admin tải | PDF hiển thị trong cột trái; nút Xem file chi tiết mở tab mới; Tải file gốc tải được |
| S7 | Mở môn có DOCX chuẩn do Admin tải | Chữ, bảng, hình phổ biến hiển thị trong cột trái và tab chi tiết; tệp DOCX gốc tải được |
| S8 | Mở trên iPhone hoặc trình duyệt rộng 390px | Hai cột xếp dọc, không có chữ/nút tràn ra ngoài |
| S9 | Môn đã xác nhận chương | Cột phải hiển thị chương có thật, số tài liệu được duyệt và liên kết đọc chương |
| S10 | Chương chưa được Admin duyệt tài liệu | Ghi rõ chưa có, không tạo file giả hoặc dùng tài liệu chương khác |
| S11 | Môn chưa xác nhận đề cương | Mời phân tích/chốt chương, không bịa danh sách chương |
| S12 | Mở Cài đặt học tập | Form mở rộng; lưu giờ học, thời lượng, mục tiêu, ghi chú; dữ liệu vẫn còn sau tải lại |
| S13 | Môn có đề cương chuẩn | Không làm phiền bằng ô đề cương cá nhân dự phòng |
| S14 | Môn chưa có đề cương chung | Có thể chọn đề cương cá nhân dự phòng, không đưa dữ liệu cá nhân vào kho chung |
| S15 | Dưới trang | Chỉ hiện tối đa 2 buổi gần nhất, có link thời khóa biểu |
| S16 | Dùng tài khoản khác môn / chưa đăng nhập mở file chung hoặc cá nhân | 403/404 hoặc chuyển đăng nhập; không lộ file |
| S17 | Dùng Quiz, lộ trình, Chat và Adaptive như cũ | Không phát sinh lỗi hồi quy |

## 3. Phạm vi hỗ trợ file

- **PDF**: trình xem PDF gốc của trình duyệt, có thể mở trong tab riêng và tải file.
- **Word DOCX**: Web chuyển nội dung DOCX thành bản xem HTML an toàn ngay trên máy chủ, gồm đoạn văn, tiêu đề, bảng và ảnh raster nhỏ. Đây **không phải** ảnh chụp nguyên dạng từng trang Word; font, sơ đồ SmartArt, biểu đồ, hình nổi, ngắt trang có thể khác. Nút tải file gốc luôn giữ nguyên DOCX.
- **Word DOC cũ**: chưa hỗ trợ upload/xem; cần chuyển sang DOCX hoặc PDF trước.
- Các tài liệu PDF/DOCX có văn bản được trích xuất vẫn được Study Agent sử dụng ở backend; không xóa hoặc đổi logic Chat/Quiz/roadmap.
- CI sử dụng dữ liệu DOCX tự tạo (có bảng, ảnh) và PDF mẫu; kiểm tra thị giác trên trình duyệt/thiết bị và độ chính xác AI trên file thực tế cần nghiệm thu thủ công.

**Ghi chú/ảnh lỗi:** ______________________________________
