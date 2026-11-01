"""UI copy acceptance: development-phase/debug copy must not leak to students.

This is a static regression in addition to Flask integration/UI tests.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAGES=(
    "templates/syllabus_review.html",
    "templates/subject_detail.html",
    "templates/course_learning_path.html",
    "templates/study_plan.html",
    "templates/quiz.html",
    "templates/study_session.html",
)
TECHNICAL=(
    "Đợt 6.1", "ĐỢT 6.4", "ĐỢT 7.1", "ĐỢT 8",
    "Đợt 8.3", "không gọi Gemini lại",
    "Đã dùng lại phân tích đề cương chung đúng phiên bản",
    "Giờ học nằm trên từng thẻ",
    "Xem chuẩn đầu ra CLO và minh chứng tiến bộ",
)
for rel in PAGES:
    text=(ROOT/rel).read_text(encoding="utf-8")
    for phrase in TECHNICAL:
        assert phrase not in text, (rel, phrase)

source=(ROOT/"syllabus_routes.py").read_text(encoding="utf-8")
assert "không gọi Gemini lại" not in source
assert "Đã tìm thấy danh sách chương đã phân tích." in source

subject=(ROOT/"templates/subject_detail.html").read_text(encoding="utf-8")
assert "Xem mục tiêu môn học và tiến độ" in subject
assert "{% if chapter_items %}" in subject
assert "Chưa xác nhận{% endif %}" in subject
assert "chuẩn đầu ra CLO" not in subject
assert "TRỢ LÝ HỌC TẬP" in subject

roadmap=(ROOT/"templates/course_learning_path.html").read_text(encoding="utf-8")
assert "Sắp xếp lịch học từ lộ trình" in roadmap
assert 'name="action" value="schedule"' in roadmap
assert 'name="action" value="reflow"' in roadmap

planner=(ROOT/"templates/study_plan.html").read_text(encoding="utf-8")
assert "Thời khóa biểu tuần" in planner
assert 'id="plannerTimetableGrid"' in planner
assert "Sáng · Trưa · Chiều · Tối" not in planner

print("Student UI copy PASS: no development-phase labels, actions and CLO navigation retained")
