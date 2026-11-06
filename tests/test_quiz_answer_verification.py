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
# Strict callers still fail closed, while the scheduler may preserve ONLY
# corroborated questions in its unexposed, source-scoped draft store.
partial_calls = {"generate": 0, "review": 0}
def partial_model(prompt):
    if "người kiểm định độc lập" in prompt:
        partial_calls["review"] += 1
        pending = json.loads(prompt.split(
            "CÂU HỎI CẦN KIỂM ĐỊNH (KHÔNG CÓ ĐÁP ÁN TỪ NGƯỜI RA ĐỀ):\n")[-1])
        checks = [
            {"id": item["id"], "answer": 0 if i == 0 else None,
             "quote": QUOTE if i == 0 else ""}
            for i, item in enumerate(pending)
        ]
        return json.dumps({"checks": checks}, ensure_ascii=False), None
    partial_calls["generate"] += 1
    count = int(__import__("re").search(r"Tạo đúng (\d+) câu", prompt).group(1))
    questions = [
        {"question": f"Node nối tiếp thế nào? Nhóm {partial_calls['generate']}, câu {i}",
         "topic": "Node", "chapter": "Chương 1",
         "options": ["Dữ liệu và con trỏ next", "Chỉ âm thanh", "Chỉ hình ảnh",
                     "Không có dữ liệu"], "answer": 0}
        for i in range(count)
    ]
    return json.dumps(questions, ensure_ascii=False), None

with patch.object(project, "gemini_generate", partial_model):
    incomplete = project.build_quiz(SOURCE, 10, session_mode=True)
    accepted_draft = project.build_quiz(
        SOURCE, 10, session_mode=True, allow_partial=True)
assert incomplete == [], "Normal Quiz output must still reject incomplete items"
assert 0 < len(accepted_draft) < 10
assert all(q["options"][q["answer"]] == "Dữ liệu và con trỏ next" for q in accepted_draft)

# Quota failures must be distinguished from invalid answers in Quiz drafts.
from quiz_provider_limits import QuizRateLimitError
with patch.object(project, "gemini_generate",
                  return_value=(None, "Gemini đã chạm giới hạn API (HTTP 429).")):
    try:
        project.build_quiz(SOURCE, 15, session_mode=True, allow_partial=True)
        raise AssertionError("Quota error must be visible to the background queue")
    except QuizRateLimitError:
        pass
    assert project.build_quiz(SOURCE, 15, session_mode=True) == []

# A verified subset from the first batch survives a rate limit later in the
# same call; future steps can persist that subset before entering cooldown.
mixed_calls={"generation":0}
def mid_batch_rate_limit(prompt):
    if "người kiểm định độc lập" in prompt:
        candidate=json.loads(prompt.split(
            "CÂU HỎI CẦN KIỂM ĐỊNH (KHÔNG CÓ ĐÁP ÁN TỪ NGƯỜI RA ĐỀ):\n")[-1])
        return json.dumps({"checks":[
            {"id": x["id"], "answer": 0, "quote": QUOTE}
            for x in candidate
        ]}, ensure_ascii=False), None
    mixed_calls["generation"]+=1
    if mixed_calls["generation"] > 1:
        return None, "Gemini đã chạm giới hạn API (HTTP 429)."
    items=[{"question":f"Node trong lần gọi đầu: {i}",
            "topic":"Node", "chapter":"Chương 1",
            "options":["Dữ liệu và con trỏ next","Chỉ âm thanh",
                       "Chỉ hình ảnh","Không có dữ liệu"], "answer":0}
           for i in range(10)]
    return json.dumps(items, ensure_ascii=False), None

with patch.object(project, "gemini_generate", mid_batch_rate_limit):
    partial_429=project.build_quiz(
        SOURCE, 15, session_mode=True, allow_partial=True)
assert len(partial_429)==10, len(partial_429)

print("Quiz answer verification PASS: second-pass evidence, wrong keys excluded, retries and fail closed")
