"""Four-note acceptance: private vs official and safe Support confirmations."""
import io
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_review_schedule import local_now
from support_schedule_chat import _date_time, _self_study_topic
from learning_streams import academic_quiz, ensure_private_weakness_schema


def check():
    assert _date_time("Đổi Lịch sử Đảng ngày 31/10/2099 đến 9h tối")[0].hour == 21
    assert _date_time("Cho buổi tự học môn Figma vào 7h tối ngày 1/11/2099")[0].hour == 19
    assert _self_study_topic("Cho buổi tự học môn Figma vào 7h tối ngày 1/11") == "Figma"
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as path:
        project.DB_PATH=Path(path)/"support.db"
        project.UPLOAD_DIR=Path(path)/"uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn=project.db()
            uid=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student','support@test.local','hash','student',?)
            """,(project.now(),)).lastrowid
            outsider=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Other','other-support@test.local','hash','student',?)
            """,(project.now(),)).lastrowid
            subject=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử Đảng Cộng sản Việt Nam','LS_DANG',3,?)
            """,(uid,project.now())).lastrowid
            qid=conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Quiz tự luyện','[]',?)
            """,(uid,subject,project.now())).lastrowid
            conn.commit()
            assert academic_quiz(conn,uid,qid) is False
            project.record_quiz_learning_signal(
                conn,uid,subject,"Bài luyện cá nhân","",False,
                stream="self_study"
            )
            ensure_private_weakness_schema(conn)
            assert conn.execute("""
                SELECT COUNT(*) FROM self_study_weaknesses WHERE user_id=?
            """,(uid,)).fetchone()[0] == 1
            assert conn.execute("""
                SELECT COUNT(*) FROM learning_weaknesses WHERE user_id=?
            """,(uid,)).fetchone()[0] == 0
            conn.commit();conn.close()
            client=project.app.test_client()
            with client.session_transaction() as sess:sess["user_id"]=uid
            response=client.get("/api/chat/support")
            assert response.status_code==200,response.get_data(as_text=True)
            token=response.get_json()["csrf_token"]
            headers={"X-CSRF-Token":token}
            future=local_now()+timedelta(days=2)
            date=future.strftime("%d/%m/%Y")
            iso=future.strftime("%Y-%m-%d")+"T19:00"
            msg=client.post("/api/chat/support/message",json={
                "message":f"Cho buổi tự học môn Figma vào 7h tối ngày {date}"
            },headers=headers)
            assert msg.status_code==200,msg.get_data(as_text=True)
            info=msg.get_json()
            assert info["intent"]=="create",info
            assert info["topic"]=="Figma" and info["study_at"]==iso
            recommended=client.post("/api/chat/support/message",json={
                "message":"Cho tui tự học môn Figma"
            },headers=headers)
            assert recommended.status_code==200,recommended.get_data(as_text=True)
            hint=recommended.get_json()
            assert hint["intent"]=="create" and hint["topic"]=="Figma",hint
            hinted_time=__import__("datetime").datetime.fromisoformat(hint["study_at"])
            assert hinted_time.weekday()!=6 and 19<=hinted_time.hour<22
            upload=client.post("/api/chat/support/upload",
                data={"file":(io.BytesIO(b"Figma frames and component exercises"),"figma.txt")},
                headers=headers, content_type="multipart/form-data")
            assert upload.status_code==201,upload.get_data(as_text=True)
            doc=upload.get_json()["document"]["id"]
            pre=client.post("/api/chat/support/create/preview",json={
                "topic":"Figma","subject_id":None,"study_at":iso,
                "duration":60,"document_id":doc
            },headers=headers)
            assert pre.status_code==200,pre.get_data(as_text=True)
            proposal=pre.get_json()["proposal_id"]
            conn=project.db()
            assert conn.execute("SELECT COUNT(*) FROM study_tasks WHERE user_id=?",
                                (uid,)).fetchone()[0]==0
            conn.close()
            outsider_client=project.app.test_client()
            with outsider_client.session_transaction() as sess:sess["user_id"]=outsider
            assert outsider_client.get("/api/chat/support/documents").get_json()["documents"]==[]
            assert outsider_client.post("/api/chat/support/create/confirm",
                json={"proposal_id":proposal},headers=headers).status_code in (403,409)
            ok=client.post("/api/chat/support/create/confirm",
                           json={"proposal_id":proposal},headers=headers)
            assert ok.status_code==200,ok.get_data(as_text=True)
            result=ok.get_json()
            assert result["document_id"]==doc
            assert client.post("/api/chat/support/create/confirm",
                json={"proposal_id":proposal},headers=headers).status_code==409
            conn=project.db()
            task=conn.execute("SELECT * FROM study_tasks WHERE id=?",
                              (result["task_id"],)).fetchone()
            assert task["source"]=="manual" and task["study_at"]==iso
            assert conn.execute(
                "SELECT document_id FROM manual_lesson_documents WHERE task_id=?",
                (task["id"],)
            ).fetchone()[0]==doc
            assert conn.execute("SELECT subject_id FROM documents WHERE id=?",
                                (doc,)).fetchone()[0]==task["subject_id"]
            assert conn.execute(
                "SELECT COUNT(*) FROM subjects WHERE user_id=? AND name='Figma'",
                (uid,)
            ).fetchone()[0]==1
            conn.close()
            print("Support acceptance PASS: NL date, reviewable add, inline upload,"
                  " subject creation on confirm, exact single write, owner isolation,"
                  " personal quiz evidence isolated")
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload


if __name__=="__main__":
    check()
