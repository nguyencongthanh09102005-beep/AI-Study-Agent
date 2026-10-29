"""F8 integration QA with repository's realistic subject material.

This tests an extracted course document, real Flask routes, two user sessions,
sourced/unsourced handling and adaptive recommendations. Gemini is stubbed,
so factual quality of live model answers is NOT claimed by this test.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_decision_phase8 import decide_next_learning_step


def run():
    sample=(Path(__file__).resolve().parents[1] /
            "examples" / "SL02_DanhSachLienKet_TEST.txt").read_text(encoding="utf-8")
    assert "DANH SÁCH LIÊN KẾT" in sample and len(sample)>1500
    old_db,old_upload=project.DB_PATH,project.UPLOAD_DIR
    with TemporaryDirectory() as temp:
        try:
            project.DB_PATH=Path(temp)/"integration.sqlite"
            project.UPLOAD_DIR=Path(temp)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            stamp=project.now()
            people=[]
            for code in ("user1","user2"):
                uid=conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,'student',?)
                """,(code,code+"@local.test","hash",stamp)).lastrowid
                sid=conn.execute("""
                    INSERT INTO subjects(user_id,name,code,created_at)
                    VALUES(?,'Cấu trúc dữ liệu','CTDL_TEST',?)
                """,(uid,stamp)).lastrowid
                people.append((uid,sid))
            first,other=people
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,extracted_text,created_at)
                VALUES(?,?,'chuong2.txt','sample-chuong2.txt',?,?)
            """,(first[0],first[1],sample,stamp))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,extracted_text,created_at)
                VALUES(?,?,'secret-private.txt','sample-other.txt',?,?)
            """,(other[0],other[1],"PRIVATE_USER2_DO_NOT_LEAK. Môn riêng.",stamp))
            convo=conn.execute("""
                INSERT INTO chat_conversations(user_id,subject_id,title,created_at,updated_at)
                VALUES(?,?,'Study',?,?)
            """,(first[0],first[1],stamp,stamp)).lastrowid
            conn.commit()

            own,own_sources=project.get_subject_context(
                first[0],first[1],"Giải thích danh sách liên kết đơn và con trỏ next")
            assert "Danh sách liên kết đơn" in own
            assert own_sources==["chuong2.txt"]
            assert "PRIVATE_USER2_DO_NOT_LEAK" not in own
            foreign,foreign_sources=project.get_subject_context(
                other[0],other[1],"Giải thích danh sách liên kết đơn")
            assert "PRIVATE_USER2_DO_NOT_LEAK" in foreign
            assert "chuong2.txt" not in foreign_sources

            anonymous=project.app.test_client()
            auth=anonymous.get("/login")
            assert auth.status_code==200
            assert "phase9_accessibility.css" in auth.get_data(as_text=True)
            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=first[0]
                sess["user_name"]="Test Student"
            page=client.get(f"/subjects/{first[1]}")
            assert page.status_code==200
            html=page.get_data(as_text=True)
            assert "phase9_accessibility.css" in html
            assert "Vì sao Study Agent" in html
            assert client.get(f"/subjects/{other[1]}").status_code in (302,404)

            orig=project.gemini_generate
            prompts=[]
            def fake_model(prompt):
                prompts.append(prompt)
                return json.dumps({
                    "mode":"document","sources":["chuong2.txt"],
                    "answer":"Danh sách liên kết đơn có các node chứa liên kết next."
                },ensure_ascii=False),None
            try:
                project.gemini_generate=fake_model
                response=client.post("/api/chat",json={
                    "conversation_id":convo,
                    "question":"Giải thích danh sách liên kết đơn và next?"
                })
                assert response.status_code==200,response.get_data(as_text=True)[:500]
                data=response.get_json()
                assert data["source_mode"]=="document"
                assert "chuong2.txt" in data["sources"]
                assert "PRIVATE_USER2_DO_NOT_LEAK" not in prompts[0]
                assert "PRIVATE_USER2_DO_NOT_LEAK" not in data["answer"]

                # Deliberate forged provenance: the interface must never echo it.
                project.gemini_generate=lambda prompt: (
                    '{"mode":"document","sources":["fictional.pdf"],'
                    '"answer":"FABRICATED_DATA_42"}',None)
                bad=client.post("/api/chat",json={
                    "conversation_id":convo,
                    "question":"Nội dung tài liệu nói gì?"
                })
                assert bad.status_code==200
                text=bad.get_json()["answer"]
                assert "FABRICATED_DATA_42" not in text
                assert "fictional.pdf" not in text
                assert "Trích đoạn tham khảo" in text
            finally:
                project.gemini_generate=orig

            project.record_quiz_learning_signal(
                conn,first[0],first[1],"Danh sách liên kết đơn","Chương 2",False)
            project.record_quiz_learning_signal(
                conn,first[0],first[1],"Danh sách liên kết đơn","Chương 2",False)
            agent=decide_next_learning_step(conn,first[0],first[1])
            assert agent["kind"]=="review"
            assert agent["material_chapter"]==2
            assert decide_next_learning_step(conn,other[0],first[1]) is None
            conn.close()
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("F8 PASS: representative real-length study text, Flask Chat, privacy, quiz signals and UI")


if __name__=="__main__":
    run()
