"""Same backend for bubble/full Chat: greetings and citation prompting.

No live Gemini calls; all source names and quotes are locally scoped and must
still pass existing provenance validation.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chat_grounding import (
    brief_greeting, citation_hints, is_unverified_fallback
)

CHAPTER = "Chương 1 - Tổng Quan Về Tư Duy Thiết Kế & Đổi Mới Sáng Tạo.pdf"
QUOTE = "Desirability (Tính Yêu thích/Mong muốn): Con người có thực sự cần và khao khát giải pháp này không?"
QUESTION = (
    "Đổi mới sáng tạo tối ưu đạt được ở giao điểm ba yếu tố nào? "
    "A Discover, Develop, Deliver; B Empathize, Define, Ideate; "
    "C Desirability, Feasibility, Viability; D Critical, Systems, Growth."
)


def check():
    assert brief_greeting("alo") and brief_greeting("ALO!!!")
    assert brief_greeting("chào bạn") and brief_greeting("hi!")
    assert not brief_greeting(QUESTION)
    assert not brief_greeting("alo giúp mình giải đáp về Design Thinking")

    # Never make a provider call just to respond to a plain greeting.
    with patch.object(project, "gemini_generate",
                      side_effect=AssertionError("AI call for greeting")):
        answer, sources, mode = project.gemini_subject_answer(
            "Tư duy Thiết kế", "alo",
            "", [], shared_context="KIẾN THỨC CHUNG - " + CHAPTER +
            " (shared_document):\\n" + QUOTE,
            shared_source_names=[CHAPTER]
        )
    assert "Tui đây!" in answer and sources == [] and mode == "general"

    ctx = f"KIẾN THỨC CHUNG - {CHAPTER} (shared_document):\\n{QUOTE}"
    ctx = ctx.replace("\\\\n", "\\n")
    hints = citation_hints(QUESTION, "", [], ctx, [CHAPTER])
    assert CHAPTER in hints and QUOTE in hints, hints
    assert citation_hints("alo", "", [], ctx, [CHAPTER]) == ""

    good = json.dumps({
        "mode": "shared", "sources": [CHAPTER],
        "citations": [{"source": CHAPTER, "quote": QUOTE}],
        "answer": "Đáp án C. Desirability, Feasibility, Viability."
    }, ensure_ascii=False)
    with patch.object(project, "gemini_generate", return_value=(good, None)) as ai:
        answer, sources, mode = project.gemini_subject_answer(
            "Tư duy Thiết kế", QUESTION, "", [],
            shared_context=ctx, shared_source_names=[CHAPTER]
        )
    assert ai.call_count == 1
    prompt = ai.call_args.args[0]
    assert "GỢI Ý TRÍCH DẪN NGUYÊN VĂN" in prompt and QUOTE in prompt
    assert "Đáp án C" in answer and sources == [CHAPTER] and mode == "shared"
    # Invalid quotation must never be treated as verified.
    forged = json.dumps({
        "mode": "shared", "sources": [CHAPTER],
        "citations": [{"source": CHAPTER, "quote": "Một câu trích dẫn giả hoàn toàn không nằm trong học liệu."}],
        "answer": "Bịa nội dung."
    }, ensure_ascii=False)
    with patch.object(project, "gemini_generate", return_value=(forged, None)):
        answer, sources, mode = project.gemini_subject_answer(
            "Tư duy Thiết kế", QUESTION, "", [],
            shared_context=ctx, shared_source_names=[CHAPTER]
        )
    assert "Bịa nội dung." not in answer and sources == []
    assert is_unverified_fallback(answer)
    assert not is_unverified_fallback("Đáp án C. Có nguồn thật.")
    print("Shared Chat grounding PASS: greetings, verbatim hints, forged-source rejection")


if __name__ == "__main__":
    check()
