"""Regression for AI Chat source-verification retry without real API calls."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chat_ai_recovery import generate_verified
from chapter_tutor import parse_tutor_answer

DOC = "Chương 2 - Thấu Cảm (Empathize) & Xác Định Vấn Đề (Define) (1).pdf"
EXCERPT = (
    "Đổi mới sáng tạo tối ưu đạt được khi kết hợp Desirability, "
    "Feasibility và Viability để cân bằng nhu cầu, kỹ thuật và kinh tế."
)


def check():
    # A chapter Chat can recover from malformed or paraphrased citations.
    sources = [{"key": "T1", "id": 11, "name": DOC, "excerpt": EXCERPT}]
    invalid = json.dumps({"explanation": "Đáp án C", "citations": [
        {"source_key": "T1", "quote": "Đây là câu hoàn toàn không có trong nguồn."}
    ]}, ensure_ascii=False)
    good = json.dumps({"explanation": "Đáp án C", "citations": [
        {"source_key": "T1", "quote": EXCERPT}
    ]}, ensure_ascii=False)
    sent = []
    def first_bad_then_good(prompt):
        sent.append(prompt)
        return (invalid if len(sent) == 1 else good), None

    checked, error = generate_verified(
        "Câu hỏi theo chương", first_bad_then_good,
        lambda raw: parse_tutor_answer(raw, sources), label="Test tutor"
    )
    assert checked and checked["explanation"] == "Đáp án C"
    assert checked["citations"][0]["quote"] == EXCERPT
    assert error is None and len(sent) == 2
    assert "LẦN TRẢ LỜI TRƯỚC" in sent[1]

    # Two forged citations are discarded: never return unsupported claims.
    count = [0]
    def always_bad(prompt):
        count[0] += 1
        return invalid, None

    checked, error = generate_verified(
        "Câu hỏi", always_bad, lambda raw: parse_tutor_answer(raw, sources)
    )
    assert checked is None and error and count[0] == 2

    # API unavailability doesn't trigger a second slow call.
    count[0] = 0
    def offline(prompt):
        count[0] += 1
        return None, "offline"
    checked, error = generate_verified("Câu hỏi", offline, lambda raw: raw)
    assert checked is None and error == "offline" and count[0] == 1

    # Free Chat retries a wrongly quoted response and retains real source.
    context = f"KIẾN THỨC CHUNG - {DOC} (shared_document):\n{EXCERPT}"
    bad_json = json.dumps({
        "mode": "shared", "sources": [DOC], "answer": "C",
        "citations": [{"source": DOC, "quote": "Không nằm trong học liệu."}]
    }, ensure_ascii=False)
    good_json = json.dumps({
        "mode": "shared", "sources": [DOC], "answer": "C",
        "citations": [{"source": DOC, "quote": EXCERPT}]
    }, ensure_ascii=False)
    with patch.object(project, "gemini_generate", side_effect=[
        (bad_json, None), (good_json, None)
    ]) as mock:
        answer, names, mode = project.gemini_subject_answer(
            "Design Thinking", "3 yếu tố tối ưu?", "", "",
            shared_context=context, shared_source_names=[DOC]
        )
    assert mock.call_count == 2
    assert mode == "shared" and names == [DOC] and EXCERPT in answer

    # When both citations fail, the user must NOT see raw PDF excerpts.
    with patch.object(project, "gemini_generate", return_value=(bad_json, None)):
        answer, names, mode = project.gemini_subject_answer(
            "Design Thinking", "3 yếu tố tối ưu?", "", [],
            shared_context=context, shared_source_names=[DOC]
        )
    assert "chưa tạo được câu trả lời" in answer
    assert EXCERPT not in answer and names == [] and mode == "general"
    print("Chat AI recovery PASS: retry, genuine sources, no PDF dump, safe fail")


if __name__ == "__main__":
    check()
