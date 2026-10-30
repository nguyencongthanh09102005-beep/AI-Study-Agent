"""Answer-key checking: independent call without the generated answer key.

A mismatched independent answer, fabricated citation or malformed reply must
NEVER be saved/scored. The builder may retry for more verified questions.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from quiz_answer_verification import (
    accepted_indices, verification_prompt, verify_quiz_batch,
)

SOURCE = ("Node của danh sách liên kết đơn lưu dữ liệu và tham chiếu đến node "
          "kế tiếp bằng con trỏ next. "*20)
QUOTE = "Node của danh sách liên kết đơn lưu dữ liệu và tham chiếu đến node kế tiếp bằng con trỏ next."
QUESTIONS = [
    {"question":"Node trong danh sách liên kết đơn chứa gì? "+str(i),
     "topic":"Node", "chapter":"Chương 1",
     "options":["Dữ liệu và con trỏ next","Chỉ dữ liệu ảnh",
                "Chỉ biến toàn cục","Chỉ con trỏ tail"],"answer":0}
    for i in range(3)
]
def reply(answers=(0,0,0), quote=QUOTE):
    return json.dumps({"checks":[
        {"id":i,"answer":answer,"quote":quote}
        for i,answer in enumerate(answers)
    ]},ensure_ascii=False)

prompt=verification_prompt(QUESTIONS,SOURCE)
assert '"answer": 0' not in prompt, "Reviewer must not see generator key"
assert '"question"' in prompt and '"options"' in prompt
assert accepted_indices(reply(),QUESTIONS,SOURCE)=={0,1,2}
assert accepted_indices(reply((0,1,0)),QUESTIONS,SOURCE)=={0,2}
assert accepted_indices(reply(quote="Không có trích dẫn có thật ở trong tài liệu này."),QUESTIONS,SOURCE)==set()
assert accepted_indices('invalid json',QUESTIONS,SOURCE)==set()
assert accepted_indices(json.dumps({"checks":[{"id":0,"answer":0,"quote":QUOTE}]}),
                        QUESTIONS,SOURCE)==set(), "Incomplete review should fail closed"
assert accepted_indices(json.dumps({"checks":[
    {"id":0,"answer":0,"quote":QUOTE},
    {"id":0,"answer":0,"quote":QUOTE},
    {"id":2,"answer":0,"quote":QUOTE}]}),
    QUESTIONS,SOURCE)==set(), "Duplicate reviewer ID should fail closed"
assert len(verify_quiz_batch(QUESTIONS,SOURCE,
                lambda _: (reply((0,1,0)),None)))==2

calls={"generate":0,"review":0}
def fake_model(prompt):
    if "người kiểm định độc lập" in prompt:
        calls["review"]+=1
        pending=json.loads(prompt.split(
            "CÂU HỎI CẦN KIỂM ĐỊNH (KHÔNG CÓ ĐÁP ÁN TỪ NGƯỜI RA ĐỀ):\n")[-1])
        # Intentionally disagree with the first question on the first batch,
        # forcing a retry; the rejected question must not be stored.
        checks=[]
        for index,item in enumerate(pending):
            value=1 if calls["review"]==1 and index==0 else 0
            checks.append({"id":index,"answer":value,"quote":QUOTE})
        return json.dumps({"checks":checks},ensure_ascii=False),None
    calls["generate"]+=1
    size=__import__("re").search(r"Tạo đúng (\d+) câu",prompt)
    assert size, "Expected Quiz generator prompt"
    total=int(size.group(1))
    items=[
        {"question":f"Node có nội dung nào đúng? Bước {calls['generate']}, câu {i}",
         "topic":"Node", "chapter":"Chương 1",
         "options":["Dữ liệu và con trỏ next","Chỉ âm thanh",
                    "Chỉ hình ảnh","Không có dữ liệu"], "answer":0}
        for i in range(total)
    ]
    return json.dumps(items,ensure_ascii=False),None

with patch.object(project,"gemini_generate",fake_model):
    result=project.build_quiz(SOURCE,10,session_mode=True)
assert len(result)==10,(len(result),calls)
assert calls["review"]>=2 and calls["generate"]>=2,calls
assert not any("Bước 1, câu 0" in q["question"] for q in result)
assert all(q["options"][q["answer"]]=="Dữ liệu và con trỏ next" for q in result)

with patch.object(project,"gemini_generate",
                  side_effect=lambda prompt: (json.dumps(
                      [{"question":f"Node ? {i}","options":["A","B","C","D"],
                        "answer":0,"topic":"Node","chapter":"Chương 1"} for i in range(10)]
                  ) if "Tạo đúng" in prompt else "{}",None)):
    assert project.build_quiz(SOURCE,10,session_mode=True)==[]
print("Quiz answer verification PASS: second-pass evidence, wrong keys excluded, retries and fail closed")
