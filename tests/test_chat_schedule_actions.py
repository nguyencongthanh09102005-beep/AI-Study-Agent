"""Chat bubble schedule changes: isolation, proposals, conflicts, stale safety.

Disposable SQLite DB; every model call would be an error. This verifies the
routes used by the floating Chat and protects student tasks from silent edits.
"""
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_review_schedule import local_now
from adaptive_plan_phase8 import is_manual_roadmap_time
from adaptive_review_schedule import has_manual_time
from course_schedule_sync import ensure_session_schedule_schema


def check():
    prev_db,prev_upload=project.DB_PATH,project.UPLOAD_DIR
    with TemporaryDirectory() as root:
        project.DB_PATH=Path(root)/"chat-schedule.sqlite"
        project.UPLOAD_DIR=Path(root)/"uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn=project.db()
            ensure_session_schedule_schema(conn)
            stamp=project.now()
            def user(name):
                return conn.execute("""
                  INSERT INTO users(name,email,password_hash,role,created_at)
                  VALUES(?,?,?,'student',?)
                """,(name,name+"@test.local","hash",stamp)).lastrowid
            uid,outsider=user("owner"),user("outsider")
            def subject(user_id,name,code):
                sid=conn.execute("""
                    INSERT INTO subjects(user_id,name,code,created_at)
                    VALUES(?,?,?,?)
                """,(user_id,name,code,stamp)).lastrowid
                cid=conn.execute("""
                    INSERT INTO chat_conversations(user_id,subject_id,title,created_at,updated_at)
                    VALUES(?,?,?,?,?)
                """,(user_id,sid,name,stamp,stamp)).lastrowid
                return sid,cid
            sid,convo=subject(uid,"Triết học","TRIET-CHAT")
            other_sid,other_convo=subject(uid,"Lịch sử Đảng","HISTORY")
            foreign_sid,foreign_convo=subject(outsider,"Khoa học","FOREIGN")
            date=(local_now()+timedelta(days=3)).date()
            at=lambda h,m=0:f"{date.isoformat()}T{h:02d}:{m:02d}"
            def task(owner,course,title,when,src="manual",order=None):
                return conn.execute("""
                    INSERT INTO study_tasks(user_id,subject_id,title,study_at,
                      duration,note,done,source,created_at,roadmap_session_id)
                    VALUES(?,?,?,?,45,'Do not change',0,?,?,?)
                """,(owner,course,title,when,src,stamp,order)).lastrowid
            roadmap=task(uid,sid,"Bài 1",at(19),"roadmap",1)
            other=task(uid,other_sid,"Bài sử",at(19))
            next_road=task(uid,sid,"Bài 2",at(22),"roadmap",2)
            adaptive=task(uid,sid,"Ôn tập",at(17),"adaptive")
            foreign=task(outsider,foreign_sid,"Private",at(20))
            conn.commit();conn.close()
            web=project.app.test_client()
            with web.session_transaction() as cookie:cookie["user_id"]=uid
            stranger=project.app.test_client()
            with stranger.session_transaction() as cookie:cookie["user_id"]=outsider
            headers=lambda token:{"X-CSRF-Token":token}
            with patch.object(project,"gemini_generate",
                side_effect=AssertionError("Schedule must never invoke AI")):
                no_login=project.app.test_client()
                assert no_login.get(f"/api/chat/schedule?conversation_id={convo}").status_code==401
                assert stranger.get(f"/api/chat/schedule?conversation_id={convo}").status_code==404
                listing=web.get(f"/api/chat/schedule?conversation_id={convo}")
                assert listing.status_code==200,listing.get_data(as_text=True)
                data=listing.get_json()
                assert data["conflict_count"]==1,data
                assert data["subject_id"]==sid
                by_id={row["id"]:row for row in data["tasks"]}
                assert foreign not in by_id and other not in by_id
                assert by_id[roadmap]["suggested_at"]==at(20),by_id[roadmap]
                assert by_id[roadmap]["conflict_titles"]==["Bài sử"]
                token=data["csrf_token"]
                body={"conversation_id":convo,"task_id":roadmap,"study_at":at(20)}
                assert web.post("/api/chat/schedule/preview",json=body).status_code==403
                assert web.post("/api/chat/schedule/preview",json={
                    **body,"task_id":other
                },headers=headers(token)).status_code==404
                assert web.post("/api/chat/schedule/preview",json={
                    **body,"study_at":at(19,30)
                },headers=headers(token)).status_code==409
                assert web.post("/api/chat/schedule/preview",json={
                    **body,"study_at":at(21,30)
                },headers=headers(token)).status_code==409
                preview=web.post("/api/chat/schedule/preview",json=body,
                                 headers=headers(token))
                assert preview.status_code==200,preview.get_data(as_text=True)
                proposal_id=preview.get_json()["proposal_id"]
                conn=project.db()
                assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                    (roadmap,)).fetchone()[0]==at(19)
                conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                             (at(19,15),other))
                conn.commit();conn.close()
                stale=web.post("/api/chat/schedule/confirm",json={
                    "conversation_id":convo,"proposal_id":proposal_id
                },headers=headers(token))
                assert stale.status_code==409,stale.get_data(as_text=True)
                conn=project.db()
                assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                    (roadmap,)).fetchone()[0]==at(19)
                conn.close()
                preview=web.post("/api/chat/schedule/preview",json=body,
                                 headers=headers(token))
                assert preview.status_code==200,preview.get_data(as_text=True)
                proposal_id=preview.get_json()["proposal_id"]
                saved=web.post("/api/chat/schedule/confirm",json={
                    "conversation_id":convo,"proposal_id":proposal_id
                },headers=headers(token))
                assert saved.status_code==200,saved.get_data(as_text=True)
                assert saved.get_json()["study_at"]==at(20)
                assert web.post("/api/chat/schedule/confirm",json={
                    "conversation_id":convo,"proposal_id":proposal_id
                },headers=headers(token)).status_code==409
                conn=project.db()
                moved=conn.execute("SELECT * FROM study_tasks WHERE id=?",
                                   (roadmap,)).fetchone()
                assert moved["study_at"]==at(20)
                assert moved["note"]=="Do not change"
                assert moved["duration"]==45 and moved["done"]==0
                assert is_manual_roadmap_time(conn,uid,roadmap)
                assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                    (other,)).fetchone()[0]==at(19,15)
                assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                    (foreign,)).fetchone()[0]==at(20)
                conn.close()

                # An adaptive review also receives a manual-time protection lock.
                new_slot=at(16)
                proposed=web.post("/api/chat/schedule/preview",json={
                    "conversation_id":convo,"task_id":adaptive,"study_at":new_slot
                },headers=headers(token))
                assert proposed.status_code==200,proposed.get_data(as_text=True)
                confirmed=web.post("/api/chat/schedule/confirm",json={
                    "conversation_id":convo,
                    "proposal_id":proposed.get_json()["proposal_id"]
                },headers=headers(token))
                assert confirmed.status_code==200,confirmed.get_data(as_text=True)
                conn=project.db()
                assert has_manual_time(conn,adaptive,uid)
                assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                    (adaptive,)).fetchone()[0]==new_slot
                conn.close()
            print("Chat schedule PASS: conflict across courses, free slot, preview,"
                  " explicit confirmation, CSRF, ownership, stale rejection,"
                  " no Gemini, roadmap & adaptive locks, repeat-submit safety")
        finally:
            project.DB_PATH,project.UPLOAD_DIR=prev_db,prev_upload

if __name__=="__main__":
    check()
