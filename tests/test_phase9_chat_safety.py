"""F3/F4: offline latency budget, JSON validation and source provenance QA.

All Gemini calls are mocked; never use a user's API key or spend tokens.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chat_response_validation import parse_free_chat_response


def run():
    good = json.dumps({"mode": "document", "sources": ["bai1.pdf"],
                       "answer": "Kiến thức đúng theo tài liệu."},
                      ensure_ascii=False)
    assert parse_free_chat_response(good,["bai1.pdf"],[]) == (
        "Kiến thức đúng theo tài liệu.",["bai1.pdf"],"document")
    fenced = chr(96) * 3 + "json\n" + good + "\n" + chr(96) * 3
    assert parse_free_chat_response(fenced,["bai1.pdf"],[])[2]=="document"
    for invalid in (
        '{"mode": "general", "sources": [], "answer": }',
        '{"mode":"document","sources":["file-gia.pdf"],"answer":"Sai nguồn"}',
        '{"mode":"document","sources":[],"answer":"Không có nguồn"}',
        '{"mode":"general","sources":["bai1.pdf"],"answer":"Nguồn giả"}',
        '{"mode":"other","sources":[],"answer":"Sai chế độ"}',
        "{" + '"mode":"general","sources":[],"answer":"ok"}' + " extra text",
    ):
        try:
            parse_free_chat_response(invalid,["bai1.pdf"],[])
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid JSON/provenance was accepted")

    # Malformed JSON cannot be displayed raw or attributed to a forged source.
    orig=project.gemini_generate
    try:
        project.gemini_generate=lambda prompt: (
            '{"mode":"document","answer":"MỘT NỘI DUNG GIẢ MẠO",'
            '"sources":["nguon-bia.pdf"]}',None)
        answer, sources, mode=project.gemini_subject_answer(
            "Lịch sử", "Tóm tắt Đại hội VI",
            "FILE: bai1.pdf\nĐổi mới được khởi xướng tại Đại hội VI năm 1986.",
            ["bai1.pdf"])
        assert "MỘT NỘI DUNG GIẢ MẠO" not in answer
        assert "nguon-bia.pdf" not in answer
        assert "Trích đoạn tham khảo" in answer
        assert "Đổi mới" in answer

        project.gemini_generate=lambda prompt: (
            '{"mode":"general","sources":[],"answer":"| Nội dung | Giải thích |\\n| --- | --- |\\n| A | B |"}',None)
        answer,sources,mode=project.gemini_subject_answer("Lịch sử","bảng", "",[])
        assert mode=="general" and sources==[] and "| --- | --- |" in answer

        project.gemini_generate=lambda prompt: (None,"offline")
        answer,sources,mode=project.gemini_subject_answer("Lịch sử","Tóm tắt","",[])
        assert "AI" in answer and "GEMINI" not in answer.upper()
    finally:
        project.gemini_generate=orig

    # A slow real API cannot consume a sequence of full timeout windows.
    clock = [100.0]
    calls = []
    def fake_post(url,headers,json,timeout):
        calls.append(timeout)
        clock[0] += timeout
        raise project.requests.Timeout("simulated network stall")
    with patch.dict(os.environ, {
        "GEMINI_API_KEY":"fixture-not-a-key",
        "GEMINI_MODEL":"fake-primary",
        "GEMINI_FALLBACK_MODELS":"fake-backup",
        "GEMINI_TOTAL_TIMEOUT":"35",
        "GEMINI_PRIMARY_RETRIES":"2",
        "GEMINI_REQUEST_TIMEOUT":"25",
    }), patch.object(project.time,"monotonic",side_effect=lambda:clock[0]), \
         patch.object(project.requests,"post",side_effect=fake_post):
        output, error = project.gemini_generate("test budget")
        assert output is None and error
        assert len(calls) <= 2, calls
        assert sum(calls) <= 36, calls
        assert clock[0]-100 <= 36,clock[0]

    print("F3/F4 PASS: bounded Gemini latency, JSON validation, no forged provenance")


if __name__=="__main__":
    run()
