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
| C8 | Mobile: 4 tab, Chat nổi, lộ trình/buổi học, Quiz theo buổi 15/60, tài liệu & lịch | Đã triển khai + CI PASS; chưa khẳng định ngang chức năng Web | Cần nghiệm thu Expo Go từng luồng; C1/C2/C4 chuyên sâu vẫn ưu tiên Web |
| Đợt 15 | Báo cáo, slide và minh chứng bảo vệ | Bản 25/10 đã có; cần đồng bộ tính năng và commit mới | Chưa chốt đến khi cập nhật ảnh thực và duyệt thông tin bìa |

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

Mỗi mục phải có PASS/FAIL/CHƯA TEST kèm ảnh/log. CI PASS không đồng nghĩa chất lượng câu hỏi Gemini đúng. Không kết luận đạt CLO chính thức, không nêu hiệu quả vượt Gemini nếu chưa có dữ liệu chấm thật. C8 đã có triển khai nền tảng trên Mobile nhưng không đồng nghĩa tất cả chức năng Web đã có UI riêng trên Mobile. Báo cáo, slide và ảnh nghiệm thu cần cập nhật theo phiên bản mới. Xem `docs/FINAL_RELEASE_QA_2026-11-01.md` trước khi xác nhận hoàn tất.

## Cập nhật máy

```bash
git switch feature/phase9-fixes
git pull --ff-only
python app.py
```
