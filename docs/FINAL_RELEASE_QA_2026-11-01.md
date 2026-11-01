# AI Study Agent — Kiểm thử tổng thể và bàn giao (01/11/2026)

## 1. Phạm vi và nguyên tắc công bố

- **Nhánh phát hành thử:** `feature/phase9-fixes`. Không tự hợp nhất vào `main` khi chưa kiểm thử thiết bị và xác nhận của sinh viên.
- **Kiểm thử tự động:** GitHub Actions chạy Flask/SQLite trong dữ liệu kiểm thử cách ly, hợp đồng Web/Mobile, Quiz, lộ trình, phân quyền, CLO, Chat, xác thực nguồn, hàng đợi AI, xuất iOS SDK 58.
- **Không được nhầm:** CI PASS **không phải** là kiểm thử AI với API thật, đo hiệu quả học tập, hoặc nghiệm thu cảm ứng Expo Go trên iPhone. Không được dùng ảnh UI mô phỏng làm minh chứng ứng dụng thực tế.
- Các file báo cáo và slide từng mô tả nhánh `main` commit tháng 10 là **tài liệu phiên bản cũ**, phải sửa commit/ảnh/trạng thái trước khi bảo vệ.
- Không chạy benchmark `--live` và không tiêu thụ quota API nếu chưa chủ động cấu hình.

## 2. Ma trận nghiệm thu theo nghiệp vụ

| Mã | Luồng cần đảm bảo | Kiểm chứng tự động | Kiểm tra trên thiết bị thật |
|---|---|---|---|
| A01 | Admin duyệt đề cương và tài liệu đúng mã môn/chương | `test_admin_shared.py`, `test_chapter_materials_step3.py` | Đăng nhập Admin, duyệt file thật |
| A02 | Sinh viên xác nhận đề cương, lộ trình, CLO, lên lịch | `test_syllabus_step1.py`, `test_course_path_step2.py`, `test_clo_evidence_c2.py`, `test_course_schedule_sync.py` | Xem nội dung có đúng đề cương thật |
| A03 | Mở buổi học Web/Mobile, đồng hồ máy chủ, Chat có nguồn | `test_mobile_study_room.py`, `test_study_session_tracking.py`, `test_chat_grounding.py` | Tạm dừng, mở lại, mất mạng, kiểm tra nguồn |
| A04 | Quiz 15 câu/buổi và 60 câu tổng hợp; khóa theo lịch | `test_study_session_quiz_step7234.py`, `test_mobile_session_quiz_ui.js` | Chạy 15/60 trên iPhone, chuyển app và quay lại |
| A05 | Chấm, đáp án sau nộp, chống gửi trùng, ôn điểm yếu | `test_quiz_answer_verification.py`, `test_quiz_review_progress_step754.py`, `test_study_session_quiz_step7234.py` | Nộp Quiz, so với Web, thử mất Wi-Fi |
| A06 | Adaptive không ghi đè lịch đã sửa và không trùng giờ | `test_adaptive_phase8.py`, `test_phase9_schedule_safety.py`, `test_schedule_conflicts.py` | Sửa giờ trên Web và mở lại Mobile |
| A07 | Tài khoản A/B, Admin, bảo vệ dữ liệu & nguồn riêng | `test_final_integrity_audit.py`, `test_admin_shared.py`, `test_final_qa.py` | Đăng xuất/đổi tài khoản và xem tài liệu riêng |
| A08 | Giao diện 4 tab, AI bong bóng, đổi môn, lịch tuần | `test_mobile_minimal_ui.js`, `test_mobile_learning_ui.js`, `test_mobile_chat_parity.js` | Nhấn/scroll/keyboard/đổi môn trên iPhone |
| A09 | Bài tập theo chương, CLO, cá nhân hóa và shared cache | `test_chapter_exercises_c1.py`, `test_clo_evidence_c2.py`, `test_agent_personalization_c3.py`, `test_shared_cache_c4.py` | Chủ yếu trên Web; chưa tuyên bố Mobile đủ mọi trang |
| A10 | So sánh với gọi AI trực tiếp | `test_evaluation_harness_c5.py` (offline) | Chưa có điểm chấm người thật / benchmark live |
| A11 | Báo cáo/slide phản ánh UI và commit thực tế | Kiểm tra thủ công nội dung và ảnh | Cần duyệt bìa, học vị GVHD, chụp minh chứng cuối |

**Cách ghi:** PASS tự động, PASS thủ công, FAIL, CHƯA TEST là các trạng thái khác nhau. Mỗi mục thao tác thật cần ảnh và ngày quan sát.

## 3. Kịch bản demo toàn tuyến (dữ liệu thật, không phỏng đoán)

1. Admin: tạo môn/đề cương chuẩn và duyệt học liệu đúng chương; không tải tài liệu khác chương làm nguồn.
2. Sinh viên A: xác nhận đề cương, xem lộ trình/CLO, đưa buổi vào lịch; kiểm tra không trùng lịch đã chỉnh.
3. Vào Không gian học: học liệu, mục tiêu, timer, hỏi Chat AI một câu từ chính chương, mở dẫn chứng.
4. Chuẩn bị Quiz nếu chưa có; kiểm tra trạng thái khóa **trước giờ học**.
5. Khi lịch đến giờ: mở Quiz buổi thường **15 câu**, nộp bài; sau đó thử buổi tổng hợp **60 câu** với bộ dữ liệu test phù hợp.
6. Mở kết quả/điểm yếu và lộ trình ôn trên cả Web và Mobile; xem lại đáp án chỉ khi đã nộp.
7. Sinh viên B: mở cùng nguồn dùng chung nhưng không thể xem file, lịch sử Chat, Quiz và lịch riêng của A.
8. Admin: xem cache/nguồn dùng chung; thay đổi phiên bản đề cương/tài liệu để đảm bảo nguồn cũ không được trích sai.
9. Chụp màn hình thật của Admin, Web, Mobile, trạng thái Quiz 15/60, tiến độ và workflow CI để đưa vào báo cáo.

## 4. Các giới hạn còn lại cần công khai

- **Thiết bị thật:** Expo iOS export không chứng minh cuộn màn hình, bàn phím, chuyển ứng dụng hoặc gửi Quiz khi Wi-Fi mất.
- **AI tạo sinh:** độ đúng của đáp án và trích dẫn trên file thật cần người kiểm tra; test mocking chỉ kiểm chứng logic và an toàn.
- **Tính năng Web ≠ Mobile:** một số thao tác nâng cao (bài tập/CLO/cache, chỉnh đề cương, quản trị) vẫn tập trung trên Web.
- **Học liệu:** PDF scan chưa OCR; DOC cũ không phải DOCX; khả năng trích xuất bảng/hình phức tạp có giới hạn.
- **Hạ tầng:** Expo Go và máy Flask LAN chỉ thích hợp demo; cấu hình HTTPS, bảo vệ phiên và worker bền vững cần thiết trước khi triển khai Internet.
- **Khoa học:** chưa có benchmark trực tiếp độc lập, thống kê cải thiện kết quả học hay kết luận vượt các chatbot tổng quát.
- **Hồ sơ:** hình ảnh cũ trong báo cáo/slide không đại diện cho UI ngày 01/11 nếu chưa thay.

## 5. Lệnh tự chạy một đợt kiểm thử trước buổi bảo vệ

```powershell
git status
git fetch origin
git switch feature/phase9-fixes
git pull --ff-only origin feature/phase9-fixes
python tests/test_final_release_contract.py
python tests/test_study_session_quiz_step7234.py
python tests/test_final_integrity_audit.py
python tests/test_final_qa.py
node tests/test_mobile_session_quiz_ui.js
cd mobile
npx expo export --platform ios --output-dir dist-ci
```

Lệnh trên là bước spot-check khi tải về máy; **GitHub Actions** chạy toàn bộ danh mục CI (rộng hơn) với mỗi commit.

## 6. Phiếu xác nhận bàn giao

- [ ] GitHub Actions của commit cuối PASS (lưu URL run và ảnh minh chứng)
- [ ] Đăng nhập iPhone và Web cùng dữ liệu: PASS/FAIL
- [ ] Quiz Mobile 15/60, nộp/đáp án/điểm yếu: PASS/FAIL
- [ ] Đổi môn Chat AI, kích thước khung, bàn phím: PASS/FAIL
- [ ] Admin và sinh viên B không lộ dữ liệu: PASS/FAIL
- [ ] Độ đúng của ít nhất 5 câu hỏi trên học liệu thật: đã chấm/chưa chấm
- [ ] Báo cáo/slide: bìa **Bộ Xây dựng**, tên đề tài tiếng Việt, GVHD có học vị được xác minh
- [ ] Sao lưu SQLite và ảnh chứng minh; nghiệm thu trước khi merge `main`

Không đánh dấu những ô này tự động thay cho người dùng.
