# Nghiệm thu Đợt 10–15 theo góp ý GVHD

Nhánh: `feature/phase9-fixes`. Chưa merge main.

| Mã | Nội dung | Code và test | Nghiệm thu thực tế |
|---|---|---|---|
| C1 | Bài tập theo chương, nộp/sửa, AI có dẫn chứng | Đã triển khai | Chưa thử Gemini thật |
| C2 | Xác nhận liên kết CLO–chương và thống kê Quiz/bài tập | Đã triển khai | Chưa nghiệm thu trình duyệt |
| C3 | Agent theo Quiz, bài tập, mục tiêu và thói quen | Đã triển khai | Chưa demo 2 người dùng thật |
| C4 | Cache phân tích đề cương chung theo phiên bản | Đã triển khai | Chưa đo trên dữ liệu thực |
| C5 | Bộ đánh giá so sánh với Gemini trực tiếp | Có script và rubric | Chưa chạy Gemini thật, chưa chấm độc lập |
| C6 | Giao diện Web nhất quán | Đã nối từ buổi học đến bài tập/CLO | Chưa nghiệm thu bằng ảnh |
| C7 | Kiểm thử tổng hợp bằng học liệu thật | Có CI tự động | Chưa nghiệm thu thủ công |
| C8 | Mobile đồng bộ toàn bộ chức năng mới | Chưa cập nhật | Chưa đạt |
| Đợt 15 | Báo cáo và slide có kết quả thật | Chưa cập nhật | Chưa đạt |

## Đường đi demo thực tế

1. Admin thêm đề cương môn Cấu trúc dữ liệu và giải thuật; tải slide và duyệt gắn đúng chương.
2. Sinh viên A xác nhận đề cương, lập lộ trình, đưa vào lịch, mở Bắt đầu học và hỏi Chat AI có dẫn chứng.
3. Mở Bài tập theo chương: nộp, nhận nhận xét Gemini, nộp bản sửa, xem lịch sử không ghi đè.
4. Chuẩn bị và làm Quiz; kiểm tra điểm yếu, làm bài ôn và giải thích đề xuất của Agent.
5. Xác nhận mã CLO thuộc chương; đối chiếu số câu Quiz, bài tập và thông báo thiếu minh chứng.
6. Đăng nhập sinh viên B cùng môn: học liệu chung tái sử dụng nhưng không thấy dữ liệu riêng của A.
7. Thêm buổi thủ công dùng tài liệu cá nhân và Quiz tùy chọn; thử sai môn và không có quyền.
8. Admin kiểm tra số cache hit ở /admin/shared-cache-metrics; đổi đề cương để chắc không tái dùng dữ liệu cũ.
9. Chạy benchmark `python evaluation/benchmark_agent_vs_gemini.py --live` **chỉ khi đã cấu hình API và đồng ý sử dụng quota**. Chấm thủ công theo `docs/evaluation-protocol-c5.md`.
10. Chụp ảnh Admin, Web, Mobile và kết quả đối chứng cho báo cáo/slide.

## Quy tắc đạt

Mỗi mục phải có PASS/FAIL/CHƯA TEST kèm ảnh/log. CI PASS không đồng nghĩa chất lượng câu hỏi Gemini đúng. Không kết luận đạt CLO chính thức, không nêu hiệu quả vượt Gemini nếu chưa có dữ liệu chấm thật. C8/Đợt 15 thực hiện sau khi Web được nghiệm thu.

## Cập nhật máy

```bash
git switch feature/phase9-fixes
git pull --ff-only
python app.py
```
