"""F1/F2: protect edited roadmap times, lesson order and subject deadlines."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_review_schedule import local_now
from adaptive_plan_phase8 import proposal_for_subject, is_manual_roadmap_time


def run():
    with TemporaryDirectory() as temp:
        old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(temp) / "f12.sqlite"
            project.UPLOAD_DIR = Path(temp) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            stamp = project.now()
            uid = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student F12','f12@test.local','hash','student',?)
            """, (stamp,)).lastrowid
            sid = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,'History F12','F12',?)
            """, (uid, stamp)).lastrowid
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",False)
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",False)
            target = datetime.combine((local_now()+timedelta(days=4)).date(),
                                       datetime.min.time()).replace(hour=19)
            iso=lambda dt: dt.isoformat(timespec="minutes")
            road_at=target-timedelta(hours=1)
            road=conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                note,done,source,created_at,roadmap_session_id)
                VALUES(?,?,'Buoi 1',?,45,'',0,'roadmap',?,1)
            """,(uid,sid,iso(road_at),stamp)).lastrowid
            conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                note,done,source,created_at)
                VALUES(?,?,'Adaptive review',?,45,'',0,'adaptive',?)
            """,(uid,sid,iso(target),stamp))
            conn.commit()
            assert proposal_for_subject(conn,uid,sid), "Initial suggestion should exist"
            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid

            moved=iso(road_at+timedelta(minutes=10))
            response=client.post(f"/study-plan/tasks/{road}/update",data={
                "subject_id":str(sid),"title":"Buoi 1",
                "study_at":moved,"duration":"45","note":"my time"
            })
            assert response.status_code==302
            assert is_manual_roadmap_time(conn,uid,road)
            assert proposal_for_subject(conn,uid,sid) is None, "Manually edited roadmap must not move"
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (road,)).fetchone()[0]==moved
            # For the remaining F2 tests, remove only the test fixture lock.
            conn.execute("DELETE FROM roadmap_manual_time_locks WHERE task_id=?", (road,))
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?", (iso(road_at),road))
            conn.commit()
            valid=proposal_for_subject(conn,uid,sid)
            assert valid

            # The next roadmap session has an ID and cannot be overtaken.
            nxt=conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                note,done,source,created_at,roadmap_session_id)
                VALUES(?,?,'Buoi 2',?,45,'',0,'roadmap',?,2)
            """,(uid,sid,iso(target+timedelta(hours=1,minutes=30)),stamp)).lastrowid
            conn.commit()
            assert proposal_for_subject(conn,uid,sid) is None, "Must preserve roadmap order"
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                         (iso(target+timedelta(days=1)),nxt))
            conn.commit()
            assert proposal_for_subject(conn,uid,sid) is not None

            # Deadline of this subject limits auto-proposed time even if no collisions.
            reminder=conn.execute("""
                INSERT INTO reminders(user_id,subject_id,title,due_at,done,source,created_at)
                VALUES(?,?,'deadline',?,0,'manual',?)
            """,(uid,sid,iso(target+timedelta(hours=1)),stamp)).lastrowid
            conn.commit()
            assert proposal_for_subject(conn,uid,sid) is None, "Must never shift beyond deadline"
            conn.execute("UPDATE reminders SET due_at=? WHERE id=?",
                         (iso(target+timedelta(days=2)),reminder))
            conn.commit()
            assert proposal_for_subject(conn,uid,sid) is not None
            conn.close()
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("F1/F2 PASS: manual roadmap lock, session order, deadline, safe proposal")


if __name__=="__main__":
    run()
