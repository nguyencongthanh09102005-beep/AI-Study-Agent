# Phiếu chấm độc lập — đối chứng AI Study Agent và Gemini trực tiếp

**Trạng thái:** MẪU TRỐNG. Chưa có số liệu/chấm điểm. Không được dùng làm kết quả thực nghiệm.

## Thông tin lần đo

- Ngày/giờ:
- Commit GitHub:
- Mã môn và phiên bản giáo trình (nguồn được phép công bố):
- Số trường hợp: ____ (khuyến nghị 10–20 trường hợp dùng học liệu thật)
- Mô hình và cấu hình (hai nhánh cùng mô hình):
- Số người chấm độc lập: 2
- Đường dẫn kết quả từ `evaluation/benchmark_agent_vs_gemini.py --live`:
- Điều kiện đặc biệt / quota / timeout:

## Chấm theo rubric đã có

Mỗi lượt trả lời, **hai người chấm độc lập** cho 0–2 điểm trên mỗi tiêu chí:

1. **Độ đúng nội dung:** 0 = sai/bịa; 1 = đúng một phần; 2 = đầy đủ theo nguồn.
2. **Bám học liệu:** 0 = thiếu căn cứ; 1 = có một phần; 2 = kết luận trọng yếu có nguồn.
3. **Dễ hiểu/hữu ích:** 0 = khó dùng; 1 = có ích phần nào; 2 = rõ ràng.
4. **Cá nhân hóa:** 0 = không phù hợp; 1 = một phần; 2 = khớp mục tiêu/điểm yếu.

Chấm các tiêu chí **riêng cho hai nhánh** `direct` và `agent`. So sánh cùng câu hỏi, cùng đoạn tài liệu; nhánh Agent được cung cấp thêm ngữ cảnh cá nhân. Không xem nhánh nào khi chấm nếu có thể ẩn nhãn. Với bất đồng trên 1 điểm, cần thảo luận và ghi rõ.

## Bảng ghi điểm (lặp lại một dòng cho mỗi câu hỏi và mỗi nhánh)

| Mã ca | Nhánh | Người chấm | Đúng (0–2) | Bám nguồn (0–2) | Dễ hiểu (0–2) | Cá nhân hóa (0–2) | Trích dẫn hợp lệ? | Thời gian ms | Ghi chú / trang nguồn |
|---|---|---|---|---|---|---|---|---|---|
| C01 | direct | A | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA ĐO | CHƯA ĐO | |
| C01 | direct | B | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA ĐO | CHƯA ĐO | |
| C01 | agent | A | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA ĐO | CHƯA ĐO | |
| C01 | agent | B | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA CHẤM | CHƯA ĐO | CHƯA ĐO | |

Nhân bảng trên thành C02…C10/C20 trước khi chấm. **Trích dẫn nguyên văn tồn tại không bảo đảm câu trả lời đúng về mặt ngữ nghĩa.**

## Tổng hợp cho Chương 5 (chỉ điền sau khi chấm)

| Thước đo | Gemini trực tiếp | AI Study Agent |
|---|---|---|
| Số trường hợp hợp lệ | CHƯA ĐO | CHƯA ĐO |
| Điểm đúng trung bình (hai người chấm) | CHƯA ĐO | CHƯA ĐO |
| Điểm bám học liệu trung bình | CHƯA ĐO | CHƯA ĐO |
| Điểm cá nhân hóa trung bình | CHƯA ĐO | CHƯA ĐO |
| Tỷ lệ trích dẫn được xác minh | CHƯA ĐO | CHƯA ĐO |
| Trung vị tổng thời gian phản hồi (ms) | CHƯA ĐO | CHƯA ĐO |
| Lỗi/timeout | CHƯA ĐO | CHƯA ĐO |

**Không được kết luận Agent có mô hình AI mạnh hơn** chỉ từ kết quả: kiến trúc Agent cung cấp thêm dữ liệu học tập, trong khi hai nhánh dùng cùng nhà cung cấp mô hình. Xem giao thức đầy đủ: `docs/evaluation-protocol-c5.md`.
