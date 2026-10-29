# Nghiệm thu: Buổi học thủ công và tài liệu cá nhân

Nhánh feature/phase9-fixes. Không merge vào main trước khi nghiệm thu.

**Luồng:** Kế hoạch học → Thêm buổi học → chọn môn và file cá nhân → tùy chọn chuẩn bị Quiz 10 câu → lưu buổi → Không gian học cá nhân.

| ID | Thao tác | Kết quả mong đợi |
|---|---|---|
| M1 | Thêm buổi không chọn file | Tạo lịch thủ công như trước, không gọi Gemini |
| M2 | Chọn môn Lịch sử Đảng | Chỉ hiện các file cá nhân thuộc đúng môn này |
| M3 | Chọn PDF hoặc DOCX rồi lưu | Mở Không gian học cá nhân, xem đúng file |
| M4 | Mở file tab mới và tải file | Chỉ tài khoản chủ sở hữu được truy cập |
| M5 | Xem thời khóa biểu Tuần / Ngày | Buổi gắn tài liệu có Bắt đầu học; buổi thường vẫn hiện |
| M6 | Không chọn Chuẩn bị Quiz | Không tạo Quiz hoặc gọi Gemini |
| M7 | Chọn Chuẩn bị Quiz khi lưu | Tạo 10 câu từ file; nếu Gemini lỗi lịch vẫn có và được báo lỗi |
| M8 | Nhấn Chuẩn bị Quiz nhiều lần | Tái sử dụng Quiz đã tạo, không tạo trùng |
| M9 | Mở Quiz đã lưu | Mở đúng Quiz trong trang Quiz và làm bài như cũ |
| M10 | Hỏi AI trong buổi thủ công | Phản hồi dựa trên đúng tài liệu, có ghi tên nguồn |
| M11 | File trích xuất không đủ nội dung | Cảnh báo thay vì sinh câu hỏi không căn cứ |
| M12 | Sửa giờ, đánh dấu hoàn thành | Giữ liên kết tài liệu và Quiz |
| M13 | Chuyển buổi gắn file sang môn khác | Bị ngăn để tránh sai nguồn riêng |
| M14 | Tài khoản khác truy cập URL buổi, file, Quiz | Không đọc được nội dung riêng |
| M15 | Buổi học chính từ lộ trình | Không gian học và Quiz theo chương vẫn hoạt động |
| M16 | Mobile và Admin | Giữ API Mobile, dữ liệu cũ và phân quyền Shared Knowledge |

**Lưu ý:** Bấm chọn Chuẩn bị Quiz lúc lưu sẽ gọi Gemini đồng bộ và có thể chậm. Không tạo Quiz khi upload tài liệu. Không tự gửi tài liệu tới Gemini trừ khi bạn chủ động Hỏi AI hoặc yêu cầu chuẩn bị Quiz. Mỗi buổi gắn tối đa một tài liệu cá nhân, mặc định 10 câu.

**Kết quả:** PASS / CÓ LỖI / CHƯA TEST. Ghi ID và gửi ảnh để chỉnh.