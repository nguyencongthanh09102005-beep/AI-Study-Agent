"""Offline regression for full-text retrieval and source-only citations.

The same gemini_subject_answer() backend serves bubble, full Web Chat and Mobile.
No real Gemini API calls, no persistent data touched.
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chat_retrieval import passages, retrieve, evidence_from_context
from chat_response_validation import verify_source_citations

EVIDENCE = "Giải thích duyvat: cơ sở vật chất quyết định đời sống tinh thần trong đoạn kiểm thử này."
LONG_TEXT = ("Đoạn phụ không chứa khái niệm cần tìm. " * 450) + "\n" + EVIDENCE


def check():
    assert "".join(passages("A" * 10000))  # Long passages exist
    assert EVIDENCE in "".join(passages(LONG_TEXT))
    found = retrieve([{"name":"triethoc.txt","text":LONG_TEXT}],
                     "Hãy giải thích duyvat", max_chars=8000)
    assert found and EVIDENCE in " ".join(p for _,p in found), found

    context = "\n\n".join(f"FILE: {name}\n{part}" for name,part in found)
    evidence = evidence_from_context(context, ["triethoc.txt"], "document")
    assert evidence and EVIDENCE in " ".join(evidence["triethoc.txt"])
    good = json.dumps({"mode":"document","sources":["triethoc.txt"],
                       "citations":[{"source":"triethoc.txt","quote":EVIDENCE}],
                       "answer":"Trong học liệu kiểm thử có giải thích duyvat."},
                       ensure_ascii=False)
    verified = verify_source_citations(good,"document",["triethoc.txt"],evidence)
    assert len(verified) == 1
    forged = json.dumps({"mode":"document","sources":["triethoc.txt"],
                         "citations":[{"source":"triethoc.txt",
                                       "quote":"Một câu rất dài nhưng hoàn toàn không nằm trong tài liệu gốc."}],
                         "answer":"Không được hiển thị với nguồn."},ensure_ascii=False)
    try:
        verify_source_citations(forged,"document",["triethoc.txt"],evidence)
        raise AssertionError("Forged quote accepted")
    except ValueError:
        pass

    with patch.object(project,"gemini_generate",return_value=(good,None)):
        answer, names, mode = project.gemini_subject_answer(
            "Triết học","Giải thích duyvat",context,["triethoc.txt"])
    assert mode=="document" and names==["triethoc.txt"]
    assert EVIDENCE in answer

    with patch.object(project,"gemini_generate",return_value=(forged,None)):
        answer,names,mode=project.gemini_subject_answer(
            "Triết học","Giải thích duyvat",context,["triethoc.txt"])
    assert "Không được hiển thị với nguồn" not in answer
    assert "Trích đoạn tham khảo" in answer

    prev_db,prev_upload=project.DB_PATH,project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as tmp:
        project.DB_PATH=Path(tmp)/"chat_long_docs.sqlite"
        project.UPLOAD_DIR=Path(tmp)/"uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn=project.db()
            now=project.now()
            uid=conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES(?,?,?,?,?)",("A","long@chat.test","hash","student",now)
            ).lastrowid
            subject=conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (uid,"Triết học","TRIETTEST",now)
            ).lastrowid
            for i in range(10):
                body=(LONG_TEXT if i==0 else "Tài liệu khác không có nội dung cần tìm.")
                conn.execute(
                    "INSERT INTO documents(user_id,subject_id,original_name,"
                    "stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                    (uid,subject,f"file{i}.txt",f"file{i}.txt",body,now)
                )
            conn.commit()
            conn.close()
            doc_context,names=project.get_subject_context(uid,subject,"giải thích duyvat")
            assert "file0.txt" in names and EVIDENCE in doc_context
            assert "file9.txt" not in names or EVIDENCE in doc_context

            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid
            chats=client.get("/api/chats").get_json()
            assert chats
            convo=next(x["id"] for x in chats if x["subject_id"]==subject)
            with patch.object(project,"gemini_generate",return_value=(json.dumps({
                "mode":"document","sources":["file0.txt"],
                "citations":[{"source":"file0.txt","quote":EVIDENCE}],
                "answer":"Giải thích có căn cứ từ phần cuối tài liệu."
            },ensure_ascii=False),None)):
                response=client.post("/api/chat",json={
                    "conversation_id":convo,"question":"Giải thích duyvat"
                })
            assert response.status_code==200, response.get_data(as_text=True)[:500]
            data=response.get_json()
            assert data["source_mode"]=="document" and EVIDENCE in data["answer"]
        finally:
            project.DB_PATH,project.UPLOAD_DIR=prev_db,prev_upload
    print("Free Chat retrieval and citation PASS: final paragraphs, old documents,"
          " grounded citations, bad quotes rejected, shared backend endpoint")


if __name__=="__main__":
    check()
