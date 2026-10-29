# AI Study Agent — Phiếu nghiệm thu bản sửa F1/F2/F3/F4/F6/F8

**Nhánh:** feature/phase9-fixes (không sửa/merge main)  
**Người kiểm tra:** __________ **Ngày:** __________  
**Phạm vi:** Tính năng Web, nhánh Đợt 8 + các sửa đổi được duyệt.

## Chuẩn bị

Kiểm tra git status trước khi đổi nhánh; lưu thay đổi chưa commit (đặc biệt mobile/.env.example và mobile/package-lock.json). Từ thư mục gốc:

    git fetch origin
    git switch --track origin/feature/phase9-fixes
    python tests/test_phase9_schedule_safety.py
    python tests/test_phase9_chat_safety.py
    python tests/test_phase9_integration.py
    python tests/test_adaptive_phase8.py
    python tests/test_final_qa.py
    python app.py

Nếu nhánh đã tồn tại ở local, dùng git switch feature/phase9-fixes và git pull --ff-only. Mở http://127.0.0.1:5000.

## Checklist để tick PASS/FAIL/CHƯA TEST

| ID | Thao tác | Kết quả kỳ vọng | Kết quả |
|---|---|---|---|
| F1-01 | Tự sửa giờ buổi **roadmap** từ Kế hoạch học, sau đó mở trang môn | Agent không đề xuất tự dời giờ đó | ☐ PASS ☐ FAIL ☐ Chưa test |
| F1-02 | Làm Quiz sai thêm sau khi đã tự đổi giờ roadmap | Giờ roadmap đã sửa không bị ghi đè | ☐ PASS ☐ FAIL ☐ Chưa test |
| F2-01 | Buổi roadmap tiếp theo nằm ngay sau buổi ôn Adaptive | Agent không dời buổi hiện tại đè lên buổi tiếp theo hoặc đảo thứ tự | ☐ PASS ☐ FAIL ☐ Chưa test |
| F2-02 | Có deadline môn trước thời gian mà Agent muốn chuyển buổi | Agent không đề xuất dời vượt deadline | ☐ PASS ☐ FAIL ☐ Chưa test |
| F2-03 | Lịch đủ chỗ, đúng thứ tự và không vượt deadline | Được xem trước rồi chọn Đồng ý/Giữ lịch; không tự đổi | ☐ PASS ☐ FAIL ☐ Chưa test |
| F3-01 | Gửi câu hỏi Chat khi Gemini bình thường | Câu trả lời hiện đầy đủ, thời gian đo được | ☐ PASS ☐ FAIL ☐ Chưa test |
| F3-02 | Mô phỏng mạng/API chậm bằng bài test riêng | Tổng retry/fallback có giới hạn, không chờ nối tiếp vô hạn | ☐ PASS ☐ FAIL ☐ Chưa test |
| F3-03 | Gemini không khả dụng | Có thông báo/trích đoạn dự phòng; không treo giao diện | ☐ PASS ☐ FAIL ☐ Chưa test |
| F4-01 | Gemini trả lời JSON hợp lệ và có nguồn đúng tài khoản | Trả về câu trả lời, nguồn là file thực đã đưa vào context | ☐ PASS ☐ FAIL ☐ Chưa test |
| F4-02 | Gemini trả JSON sai hoặc viện dẫn file bịa | Không hiện nội dung raw/nguồn bịa như câu trả lời tin cậy | ☐ PASS ☐ FAIL ☐ Chưa test |
| F4-03 | Câu trả lời dự phòng trích đoạn | Có ghi chú rõ chưa được AI xác minh | ☐ PASS ☐ FAIL ☐ Chưa test |
| F6-01 | Xem Dashboard, chi tiết môn, kế hoạch, lộ trình, Quiz | Chữ rõ hơn, không lệch layout/đè nút | ☐ PASS ☐ FAIL ☐ Chưa test |
| F6-02 | Thu nhỏ trình duyệt đến 390px và 768px, kiểm tra Web | Không xuất hiện tràn ngang không cần thiết; bảng dài vẫn cuộn được | ☐ PASS ☐ FAIL ☐ Chưa test |
| F6-03 | Xem login/đăng ký/admin trên màn hình nhỏ | Form và nút dễ đọc, không vỡ layout | ☐ PASS ☐ FAIL ☐ Chưa test |
| F8-01 | Chạy 3 bài test phase9 và test_adaptive_phase8.py | Tất cả PASS | ☐ PASS ☐ FAIL ☐ Chưa test |
| F8-02 | Tài khoản A/B cùng môn nhưng tài liệu cá nhân khác | Chat không lộ nội dung tài liệu riêng của người khác | ☐ PASS ☐ FAIL ☐ Chưa test |
| F8-03 | Dùng một PDF học liệu **thật** của bạn, hỏi AI 5 câu về nội dung đó | Kiểm tra câu trả lời, mức đúng, nguồn dẫn và thời gian; lưu ảnh minh chứng | ☐ PASS ☐ FAIL ☐ Chưa test |
| F8-04 | Quiz sai → ôn → Quiz đúng → đề xuất mới → xem lịch | Không trùng buổi, không ghi đè lịch tự chỉnh, UI hoạt động | ☐ PASS ☐ FAIL ☐ Chưa test |

## Phạm vi đã kiểm thử tự động vs thực tế

- CI: dùng học liệu mẫu chương 2 **có nội dung giống tài liệu môn thật**, đang lưu trong examples/SL02_DanhSachLienKet_TEST.txt; Gemini được **mock** để không dùng quota API.
- **Chưa được chứng minh tự động:** tốc độ và độ chính xác Gemini trên API thật, giao diện trực quan trên iPhone, nội dung PDF cá nhân của người dùng. Các trường hợp này cần nghiệm thu bằng trình duyệt/thiết bị và chụp ảnh.

## Kết quả

F1: ___ F2: ___ F3: ___ F4: ___ F6: ___ F8: ___

Lỗi (màn hình, bước, ảnh): ______________________

Chỉ xem xét merge sau khi người dùng đồng ý nghiệm thu.
