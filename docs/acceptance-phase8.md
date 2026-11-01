# Phiếu nghiệm thu AI Study Agent — Đợt 8.1–8.4

Nhánh: feature/adaptive-phase8 — KHÔNG sửa hoặc kiểm thử trực tiếp trên main.
Người kiểm thử: __________ Ngày: __________ Môi trường: Web local

## Chuẩn bị
1. Tài khoản sinh viên thử nghiệm; môn đã có đề cương, học liệu, lộ trình và Quiz.
2. Mở chi tiết môn học để xem gợi ý và dữ liệu chứng minh.
3. Để kiểm thử 8.3, dùng một môn thử có lịch ôn Adaptive tương lai và buổi roadmap tương lai xếp TRƯỚC lịch ôn. Nếu lịch hiện có không cần đổi, việc không có gợi ý đổi lịch là bình thường.
4. Không sử dụng tài khoản/dữ liệu học chính để thử thay đổi giờ nếu không muốn ảnh hưởng lịch.

## Checklist PASS / FAIL

| ID | Hành động | Kết quả kỳ vọng | Kết quả |
|---|---|---|---|
| 8.1-01 | Chi tiết môn chưa có Quiz | Agent yêu cầu làm Quiz thu thập dữ liệu, không đoán năng lực | ☐ |
| 8.1-02 | Làm sai 1 lần ở một chủ đề mới | Agent đề xuất kiểm tra thêm, không khẳng định yếu lâu dài | ☐ |
| 8.1-03 | Làm sai lần thứ hai ở chủ đề đó | Ưu tiên ôn đúng chủ đề, không nhân đôi nhiệm vụ ôn | ☐ |
| 8.1-04 | Giải quyết toàn bộ điểm yếu và làm Quiz >=5 câu với >=75% đúng | Có thể đề xuất học tiếp, không tuyên bố thành thạo tuyệt đối | ☐ |
| 8.2-01 | Mở Vì sao Study Agent đề xuất bước này? | Thấy số câu đúng/tổng, chủ đề yếu, lịch ôn và buổi kế nếu có | ☐ |
| 8.2-02 | Có điểm yếu ở Chương 1 | Bằng chứng khớp đúng môn/chương, không rò dữ liệu môn khác | ☐ |
| 8.2-03 | Tải lại trang khi dữ liệu không đổi | Gợi ý nhất quán và không cần gọi Gemini lại | ☐ |
| 8.3-01 | Đặt buổi roadmap tương lai sớm hơn lịch ôn Adaptive tương lai | Hiện giờ cũ, giờ gợi ý và giờ ôn, giờ mới không trùng lịch | ☐ |
| 8.3-02 | Chỉ xem đề xuất, không bấm nút | Không có thay đổi lịch học | ☐ |
| 8.3-03 | Chọn Giữ lịch hiện tại | Giờ cũ không đổi, đề xuất được ghi nhận đã bỏ qua | ☐ |
| 8.3-04 | Tạo đề xuất mới rồi chọn Đồng ý đổi giờ buổi này | Chỉ thay đổi một buổi roadmap đã chọn, không sửa task thủ công, giờ ôn hay deadline | ☐ |
| 8.3-05 | Gửi lại đề xuất cũ sau khi lịch thay đổi | Hệ thống từ chối đề xuất hết hiệu lực, không ghi đè | ☐ |
| 8.4-01 | Chạy file test_adaptive_phase8.py | PASS: đánh giá, CSRF, xác nhận, chống trùng giờ, phân quyền | ☐ |
| 8.4-02 | Chạy test 7.5.3 / 7.5.4 / 7.6 | Tất cả PASS | ☐ |
| 8.4-03 | Đăng nhập tài khoản khác | Không thấy dữ liệu học tập cá nhân của tài khoản đầu | ☐ |
| 8.4-04 | Quiz sai → Ôn → Quiz đúng → Xem đề xuất | Gợi ý cập nhật từ kết quả thật, Dashboard/Quiz/Kế hoạch học vẫn bình thường | ☐ |

## Lệnh để chạy

    git status
    git fetch origin
    git switch --track origin/feature/adaptive-phase8
    python tests/test_adaptive_phase8.py
    python tests/test_adaptive_review_step753.py
    python tests/test_quiz_review_progress_step754.py
    python tests/test_quiz_background_jobs_step76.py
    python tests/test_final_qa.py
    python app.py

Nếu nhánh đã có trên máy, dùng git switch feature/adaptive-phase8 thay cho git switch --track.
Nhớ xem git status và bảo toàn các thay đổi cục bộ trước khi chuyển nhánh.

## Chốt nghiệm thu

- 8.1: ☐ PASS ☐ FAIL
- 8.2: ☐ PASS ☐ FAIL
- 8.3: ☐ PASS ☐ FAIL
- 8.4: ☐ PASS ☐ FAIL
- Lỗi / ảnh minh chứng: __________________________

Chỉ merge vào main sau khi nghiệm thu thực tế xong.
