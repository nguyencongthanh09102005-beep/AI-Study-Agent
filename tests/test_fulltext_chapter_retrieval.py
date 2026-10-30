"""Regression: a 100k-character textbook must match chapters near its end.

No real model or database required. Source evidence is validated against
EXACTLY the excerpts sent to Gemini, and old prefix-only caches must expire.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bulk_chapter_mapping import batch_prompt, parse_batch
from chapter_fulltext_retrieval import select_chapter_excerpts, EXCERPT_VERSION
from course_path_learning import match_course_materials

chapters = {
    "1": {"title":"Khái quát về phương pháp thiết kế", "topics":["quan sát nhu cầu"]},
    "5": {"title":"Đổi mới sáng tạo", "topics":["thử nghiệm nguyên mẫu", "phân tích khả thi"]},
}
late = ("Đổi mới sáng tạo yêu cầu thử nghiệm nguyên mẫu và phân tích khả thi "
        "trên sản phẩm thực tế trước khi triển khai chính thức.")
text = ("Kiến thức nhập môn không nhắc đến các thuật ngữ chuyên môn tương ứng. " * 900)
text += "\n" + late
assert len(text)>50000
selected = select_chapter_excerpts(text,chapters)
assert late in selected and len(selected)<=5600,(len(selected), selected[-250:])
assert late not in text[:5600]
rows = [{"id":19,"extracted_text":text}]
prompt = batch_prompt(rows,chapters,"OOPTEST")
assert late in prompt and len(prompt)<12000
valid = {"documents":[{"document_id":19,
         "suggestions":[{"chapter_key":"5","evidence":late}]}]}
assert parse_batch(json.dumps(valid,ensure_ascii=False),rows,chapters)[19] == [
    {"key":"5","evidence":late}]
forged = {"documents":[{"document_id":19,
          "suggestions":[{"chapter_key":"5",
                          "evidence":"Đoạn giả có vẻ hợp lý nhưng không xuất hiện trong các trích đoạn đã gửi."}]}]}
assert parse_batch(json.dumps(forged,ensure_ascii=False),rows,chapters)[19] == []
section = {"chapter":"Chương 5: Đổi mới sáng tạo",
           "topics":["thử nghiệm nguyên mẫu","phân tích khả thi"]}
found = match_course_materials(section, [
    {"id":19,"name":"giao-trinh.txt","text":text,"kind":"personal"}
])
assert len(found)==1 and found[0]["id"]==19
assert EXCERPT_VERSION.startswith("chapter-fulltext")
print("Long chapter materials PASS: late-text classification, quoted evidence, roadmap materials")
