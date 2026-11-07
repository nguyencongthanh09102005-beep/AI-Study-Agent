"""Mobile personal study room regression: isolation, consent, timer, source and file.

Uses disposable database/files and mocked AI; never uses real student records.
"""
import base64
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from manual_lesson_routes import attach_document, ensure_schema


def run():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    old_gemini, old_quiz = project.gemini_generate, project.build_quiz
    prompts = []
    try:
        with TemporaryDirectory() as tmp:
            project.DB_PATH = Path(tmp)/"mobile-manual.sqlite"
            project.UPLOAD_DIR = Path(tmp)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_schema(conn)
            when=project.now()
            def user(name):
                return conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,'student',?)",
                    (name,name+"@manual.test","hash",when),
                ).lastrowid
            uid, other=user("mobile-manual-a"),user("mobile-manual-b")
            def subject(owner,name):
                return conn.execute(
                    "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                    (owner,name,name[:3],when),
                ).lastrowid
            sid,other_sid=subject(uid,"Tự học Figma"),subject(other,"Đề cương khác")
            body="Tài liệu UI UX buổi tự học. " * 120
            stored="private_manual_study.txt"
            (project.UPLOAD_DIR/stored).write_text(body,encoding="utf-8")
            document=conn.execute(
                "INSERT INTO documents(user_id,subject_id,original_name,"
                "stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                (uid,sid,"figma-ui.txt",stored,body,when),
            ).lastrowid
            other_doc=conn.execute(
                "INSERT INTO documents(user_id,subject_id,original_name,"
                "stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                (other,other_sid,"other.txt","other.txt","not my file",when),
            ).lastrowid
            day=(datetime.now()+timedelta(days=1)).strftime("%Y-%m-%dT19:00")
            task=conn.execute(
                "INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,"
                "note,done,source,created_at) VALUES(?,?,?,?,?,'Luyện thiết kế',0,'manual',?)",
                (uid,sid,"Buổi tự học Figma",day,45,when),
            ).lastrowid
            attach_document(conn,uid,task,sid,document,when)
            conn.commit()
            conn.close()

            client=project.app.test_client()
            outsider=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid
                sess["user_name"]="Figma student"
            with outsider.session_transaction() as sess:
                sess["user_id"]=other
                sess["user_name"]="Other student"

            url=f"/api/mobile/manual-study/{task}"
            assert project.app.test_client().get(url).status_code==401
            assert outsider.get(url).status_code==404
            assert outsider.get(url+"/file").status_code==404
            assert outsider.post(url+"/ask",json={"question":"Trả lời đi"}).status_code==403
            result=client.get(url)
            assert result.status_code==200,result.get_json()
            state=result.get_json()
            assert state["document"]["name"]=="figma-ui.txt"
            assert state["document"]["text"].startswith("Tài liệu UI UX")
            assert state["document"]["extracted_chars"]==len(body)
            assert state["task"]["id"]==task and state["subject"]["id"]==sid
            token=state["csrf"]
            headers={"X-Manual-CSRF":token}
            assert token
            assert client.post(url+"/timer",json={"action":"start"}).status_code==403
            assert client.post(url+"/timer",json={"action":"start"},
                               headers={"X-Manual-CSRF":"wrong"}).status_code==403
            assert client.post(url+"/timer",json={"action":"invalid"},
                               headers=headers).status_code==400
            started=client.post(url+"/timer",json={"action":"start"},headers=headers)
            assert started.status_code==200,started.get_json()
            assert started.get_json()["status"]=="running"
            paused=client.post(url+"/timer",json={"action":"pause"},headers=headers)
            assert paused.status_code==200,paused.get_json()
            assert paused.get_json()["status"]=="paused"
            resumed=client.post(url+"/timer",json={"action":"resume"},headers=headers)
            assert resumed.status_code==200,resumed.get_json()
            assert resumed.get_json()["status"]=="running"

            raw=client.get(url+"/file")
            assert raw.status_code==200,raw.get_json()
            assert base64.b64decode(raw.get_json()["base64"])==body.encode("utf-8")
            assert raw.headers["Cache-Control"]=="private, no-store"
            assert client.post(url+"/prepare-quiz",headers=headers,json={}).status_code==400

            def generate(prompt):
                prompts.append(prompt)
                return "Theo file cá nhân: thành phần UI.", ""
            project.gemini_generate=generate
            asked=client.post(url+"/ask",headers=headers,
                              json={"question":"Giải thích thành phần UI?"})
            assert asked.status_code==200,asked.get_json()
            assert asked.get_json()["source"]=="figma-ui.txt"
            assert asked.get_json()["response"].startswith("Theo file cá nhân")
            assert body[:100] in prompts[-1]
            assert "không tự chế kiến thức" in prompts[-1]
            assert not client.get("/api/mobile/chat/"+str(sid)).get_json().get("messages")

            project.build_quiz=lambda _text,_count: [
                {"question":f"Câu {n} về UI?", "options":["A","B","C","D"],
                 "answer":"A"} for n in range(10)
            ]
            quiz=client.post(url+"/prepare-quiz",headers=headers,
                             json={"confirm":True})
            assert quiz.status_code==200,quiz.get_json()
            assert quiz.get_json()["quiz_id"]
            assert client.get(url).get_json()["quiz"]["id"]==quiz.get_json()["quiz_id"]
            assert outsider.get(url).status_code==404
            finished=client.post(url+"/timer",headers=headers,json={"action":"finish"})
            assert finished.status_code==200,finished.get_json()
            assert finished.get_json()["status"]=="completed"
            assert client.get(url).get_json()["task"]["done"] is True
            assert client.post(url+"/timer",headers=headers,json={"action":"resume"}).status_code==409
            conn=project.db()
            assert conn.execute(
                "SELECT done FROM study_tasks WHERE id=?",(task,)
            ).fetchone()["done"]==1
            assert conn.execute(
                "SELECT id FROM quizzes WHERE user_id=? AND document_id=?",
                (uid,other_doc),
            ).fetchone() is None
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
        project.gemini_generate,project.build_quiz=old_gemini,old_quiz
    print("Mobile manual study room PASS: ACL, document, file, source QA, timer, Quiz")


if __name__=="__main__":
    run()
