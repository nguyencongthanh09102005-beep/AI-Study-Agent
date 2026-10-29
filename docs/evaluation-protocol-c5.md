# Đợt 12 (C5) — Quy trình đối chứng AI Study Agent và Gemini trực tiếp

**Mục đích:** Chứng minh giá trị của kiến trúc đề cương → học liệu → Quiz → đề xuất cá nhân, không khẳng định mô hình Gemini được Agent nâng cấp trí tuệ.

## Kiểm thử máy (có thể tái lập)

Chạy thử dữ liệu và cấu trúc prompt (không gọi API):

```bash
python evaluation/benchmark_agent_vs_gemini.py
```

Sau khi cấu hình `GEMINI_API_KEY` và đã đồng ý sử dụng quota, chạy so sánh thật (2 lần gọi Gemini cho mỗi trường hợp):

```bash
python evaluation/benchmark_agent_vs_gemini.py --live --max-cases 4 --output evaluation/results/real_run.json
```

Đầu vào `evaluation/cases_example.json` là **dữ liệu mô phỏng**. Để báo cáo nghiêm túc, thay bằng 10–20 câu hỏi trong tài liệu môn chuyên ngành có nguồn được xác nhận và ít nhất 2 học viên có kết quả Quiz khác nhau. Không tải dữ liệu riêng của sinh viên khác vào bản công khai.

## Thiết kế đối chứng

- Cùng một mô hình Gemini, cùng câu hỏi và cùng đoạn học liệu cho hai nhánh.
- Nhánh `direct` nhận tài liệu và câu hỏi trong một yêu cầu trực tiếp.
- Nhánh `agent` nhận chính nguồn đó, cộng tên môn, chương, mục tiêu và chủ đề yếu của học viên.
- Thứ tự gọi luân phiên để giảm lệch nhỏ do thời điểm; ghi độ trễ thật của từng lần gọi.
- Kiểm tra máy chỉ xác minh **có trích nguyên văn hợp lệ**, thời gian và tình trạng phản hồi; không tự đánh giá đáp án đúng.

## Mẫu chấm thủ công hai người chấm

Với mỗi câu hỏi và mỗi nhánh, hai người chấm độc lập cho điểm 0–2:

| Tiêu chí | 0 | 1 | 2 |
|---|---|---|---|
| Độ đúng nội dung | Sai hoặc bịa | Đúng một phần | Đúng đầy đủ theo nguồn |
| Bám học liệu | Không có căn cứ | Có một phần | Từng kết luận quan trọng có căn cứ |
| Dễ hiểu và hữu ích | Khó dùng | Có ích một phần | Rõ ràng, giúp giải quyết bài học |
| Phù hợp nhu cầu người học | Không phù hợp | Phù hợp một phần | Nhắm đúng mục tiêu/điểm yếu được cung cấp |

Ghi riêng **độ trễ**, **số lần gọi Gemini**, **số câu thiếu nguồn hợp lệ**, **lượt cache shared** lấy từ `/admin/shared-cache-metrics`. Không cộng tốc độ vào điểm độ đúng. Nếu bất đồng chấm trên 1 điểm, cần thảo luận và ghi chú.

## Báo cáo sau khi chạy

| Chỉ số | Gemini trực tiếp | AI Study Agent |
|---|---|---|
| Số ca kiểm thử | Chưa đo | Chưa đo |
| Điểm đúng trung bình (người chấm) | Chưa đo | Chưa đo |
| Tỷ lệ trích dẫn có thật | Chưa đo | Chưa đo |
| Trung vị độ trễ | Chưa đo | Chưa đo |
| Trả lời phù hợp điểm yếu cá nhân | Chưa đo | Chưa đo |

**Không được thay 'Chưa đo' bằng số ước lượng.** Các chỉ số cache, phân quyền, lộ trình và cá nhân hóa đã có test code là minh chứng **chức năng**, chưa đủ để kết luận **hiệu quả giáo dục** vượt hệ thống khác.