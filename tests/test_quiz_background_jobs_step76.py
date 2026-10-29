"""Phase 7.6: durable background job, pause/resume, no Gemini HTTP call."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from course_schedule_sync import ensure_session_schedule_schema
from quiz_preparation_jobs import enqueue, pause, status, tick


def login(client,uid):
    with client.session_transaction() as session:
        session.clear()
        session["user_id"]=uid
        session["session_quiz_csrf"]="abc456securetoken"


def run():
    with TemporaryDirectory() as folder:
        old_db,old_up=project.DB_PATH,project.UPLOAD_DIR
        try:
            project.DB_PATH=Path(folder)/"jobs.sqlite"
            project.UPLOAD_DIR=Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_session_schedule_schema(conn)
            now=project.now()
            uid=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Worker','worker76@study.local','hash','student',?)
            """,(now,)).lastrowid
            outsider=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Outside','outside76@study.local','hash','student',?)
            """,(now,)).lastrowid
            sid=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử','HIST76',3,?)
            """,(uid,now)).lastrowid
            conn.execute("""
                INSERT INTO study_tasks(
                    user_id,subject_id,title,study_at,duration,note,done,
                    source,roadmap_session_id,created_at)
                VALUES(?,?,'Buổi 1','2026-11-01T19:00',45,'',0,'roadmap',1,?)
            """,(uid,sid,now))
            conn.commit();conn.close()
            client=project.app.test_client()
            with patch("quiz_preparation_jobs.preparation_status",
                       return_value=[{"status":"pending"}]),\
                 patch("quiz_preparation_jobs.start_local_worker") as starter:
                login(client,outsider)
                wrong=client.post(
                    f"/api/subjects/{sid}/quiz-preparation/background",
                    headers={"X-Quiz-CSRF":"abc456securetoken"},json={})
                assert wrong.status_code==404
                login(client,uid)
                no_csrf=client.post(
                    f"/api/subjects/{sid}/quiz-preparation/background",json={})
                assert no_csrf.status_code==403
                queued=client.post(
                    f"/api/subjects/{sid}/quiz-preparation/background",
                    headers={"X-Quiz-CSRF":"abc456securetoken"},json={})
                assert queued.status_code==200,queued.get_data(as_text=True)
                assert queued.get_json()["state"]=="queued"
                starter.assert_called_once()
                conn=project.db()
                assert status(conn,uid,sid)["state"]=="queued"
                conn.close()
                stopped=client.post(
                    f"/api/subjects/{sid}/quiz-preparation/background/pause",
                    headers={"X-Quiz-CSRF":"abc456securetoken"},json={})
                assert stopped.get_json()["state"]=="paused"
                with patch("quiz_preparation_jobs.prepare_step",
                           side_effect=AssertionError("Paused job called Gemini")):
                    assert tick(project) is False
                conn=project.db()
                assert status(conn,uid,sid)["state"]=="paused"
                assert enqueue(conn,project,uid,sid)=="queued"
                conn.close()

            calls=[]
            def mock_step(p,conn,u,s):
                calls.append((u,s))
                return {"done":len(calls)>1}
            with patch("quiz_preparation_jobs.prepare_step",mock_step):
                assert tick(project) is True
                conn=project.db()
                assert status(conn,uid,sid)["state"]=="queued"
                conn.close()
                assert tick(project) is True
                conn=project.db()
                assert status(conn,uid,sid)["state"]=="completed"
                conn.close()
                assert tick(project) is False
            assert calls==[(uid,sid),(uid,sid)]
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_up
    print("7.6 server queue/auth/CSRF/pause/resume/worker steps PASS")


if __name__=="__main__":
    run()
