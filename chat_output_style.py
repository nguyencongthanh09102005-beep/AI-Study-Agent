"""Presentation guidance shared by free Chat AI and chapter-grounded tutor.

The surrounding Gemini response must be valid JSON. Only the value of the
answer/explanation JSON string can contain Markdown or math notation.
"""

FORMAT_POLICY = """
CÁCH TRÌNH BÀY CÂU TRẢ LỜI (áp dụng cho nội dung answer/explanation):
- Tự chọn hình thức dễ học theo ý định câu hỏi, KHÔNG dùng một mẫu cho mọi câu.
- Nếu yêu cầu so sánh, phân biệt hoặc lập bảng: tạo bảng Markdown thật với
  hàng tiêu đề, hàng phân cách | --- | --- | và các dòng dữ liệu.
- Nếu câu hỏi là toán hoặc phân tích độ phức tạp: hiển thị công thức bằng
  $...$ cho công thức ngắn, $$...$$ trên một dòng riêng cho công thức lớn.
  Dùng kí hiệu toán chính xác; không thay dữ liệu không có trong nguồn bằng suy đoán.
- Nếu người học muốn thuật toán, code hay ví dụ lập trình: dùng khối code
  ba dấu backtick, ghi ngôn ngữ sau dấu mở, ví dụ python, cpp hoặc java.
  Code chỉ được dựa trên nội dung có thể giải thích, không bịa nội dung nguồn.
- Có thể dùng gạch đầu dòng, tiêu đề hoặc sơ đồ mũi tên dạng text khi có ích.
- Câu hỏi ngắn thì trả lời ngắn gọn; không ép bài tự luyện vào mọi câu.
- Đừng lộ JSON/Markdown bao ngoài câu trả lời: chỉ trường nội dung được chứa
  Markdown. Trả JSON hợp lệ và escape dấu ngoặc kép, xuống dòng trong string.
- Không tự nhận đã đọc file hay có dẫn chứng nếu nguồn không thực sự hỗ trợ.
""".strip()
