"""Both Chat AI modes request adaptive formatting while preserving JSON."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chapter_tutor import make_tutor_prompt, parse_tutor_answer

quote = "Mảng truy cập phần tử theo chỉ số với chi phí O(1)."
sources = [{
    "key": "T1", "id": 19, "name": "chuong2.txt",
    "excerpt": quote + " Danh sách liên kết truy cập O(n)."
}]
lesson_prompt = make_tutor_prompt(
    "Cấu trúc dữ liệu", "Chương 2", "Mảng; Danh sách liên kết",
    "Hãy lập bảng so sánh.", sources
)
assert "bảng Markdown thật" in lesson_prompt
assert "công thức" in lesson_prompt
assert "khối code" in lesson_prompt
assert "Chỉ xuất JSON" in lesson_prompt
table = "| Cấu trúc | Truy cập |\\n| --- | --- |\\n| Mảng | O(1) |"
valid = {
    "explanation": table,
    "citations": [{"source_key": "T1", "quote": quote}],
    "practice": ""
}
answer = parse_tutor_answer(json.dumps(valid, ensure_ascii=False), sources)
assert answer and "| --- | --- |" in answer["explanation"]
assert answer["citations"][0]["source_name"] == "chuong2.txt"

old_model = project.gemini_generate
prompts = []
def fake_model(prompt):
    prompts.append(prompt)
    return (json.dumps({
        "mode": "general", "sources": [], "answer": table
    }, ensure_ascii=False), None)
try:
    project.gemini_generate = fake_model
    free_answer, used, mode = project.gemini_subject_answer(
        "Cấu trúc dữ liệu", "So sánh bằng bảng", "", []
    )
finally:
    project.gemini_generate = old_model
assert mode == "general" and used == []
assert "| --- | --- |" in free_answer
assert "bảng Markdown thật" in prompts[-1]
assert 'Trường "answer" ĐƯỢC dùng Markdown' in prompts[-1]
print("Chat AI format policy: both free and chapter modes support structured output")
