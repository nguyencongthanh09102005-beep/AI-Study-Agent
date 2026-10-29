"""7.5.3: avoid overlaps and preserve manually edited adaptive review times."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_review_schedule import next_review_slot, has_manual_time, local_now


def run():
    with TemporaryDirectory() as folder:
        db_path, uploads = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(folder) / "review.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            now = project.now()
            uid = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Review User','review75@test.local','hash','student',?)
            """, (now,)).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Other','reviewother75@test.local','hash','student',?)
            """, (now,)).lastrowid
            sub = conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử','HS7',3,?)
            """, (uid,now)).lastrowid
            another = conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Tin học','IT7',3,?)
            """, (uid,now)).lastrowid
            project.ensure_learning_profile(conn,uid)
            candidate = local_now()+timedelta(days=1)
            tomorrow = candidate.date()
            preferred = datetime.combine(tomorrow,datetime.min.time()).replace(hour=19)
            # Existing course lesson occupies 19:00-19:45 tomorrow.
            conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,note,done,source,created_at)
                VALUES(?,?, 'Buổi chính',?,45,'',0,'roadmap',?)
            """, (uid,another,preferred.isoformat(timespec="minutes"),now))
            conn.commit()
            # Free-slot chooser is deterministic with injected local time.
            slot = next_review_slot(conn,uid,45,"19:00",
                                     current=preferred-timedelta(hours=2))
            start = datetime.fromisoformat(slot)
            assert start!=preferred, "Review collides with a regular lesson"
            assert start + timedelta(minutes=45) <= preferred or start >= preferred+timedelta(minutes=45)
            project.record_quiz_learning_signal(conn,uid,sub,"Đổi mới","Chương 3",False)
            review = project.sync_adaptive_review_task(conn,uid,sub)
            assert review and review["source"]=="adaptive"
            review_id = review["id"]
            row = conn.execute("SELECT study_at,duration FROM study_tasks WHERE id=?",
                               (review_id,)).fetchone()
            start=datetime.fromisoformat(row["study_at"])
            assert start!=preferred
            assert start+timedelta(minutes=row["duration"])<=preferred or start>=preferred+timedelta(minutes=45)
            # Repeated sync cannot create two unfinished adaptive tasks.
            project.sync_adaptive_review_task(conn,uid,sub)
            assert conn.execute("""
                SELECT COUNT(*) FROM study_tasks
                WHERE user_id=? AND subject_id=? AND source='adaptive' AND done=0
            """,(uid,sub)).fetchone()[0]==1
            conn.commit()
            conn.close()

            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid
            chosen=(local_now()+timedelta(days=3)).date()
            user_time=datetime.combine(chosen,datetime.min.time()).replace(hour=17,minute=15)
            updated=client.post(f"/study-plan/tasks/{review_id}/update",data={
                "title":"Ôn điểm yếu theo ý tui",
                "study_at":user_time.isoformat(timespec="minutes"),
                "duration":"60", "subject_id":str(sub),
                "note":"Dành buổi chiều để ôn"
            })
            assert updated.status_code in (302,303)
            conn=project.db()
            assert has_manual_time(conn,review_id,uid)
            project.record_quiz_learning_signal(conn,uid,sub,"Đổi mới","Chương 3",False)
            again=project.sync_adaptive_review_task(conn,uid,sub)
            assert again["id"]==review_id
            row=conn.execute("SELECT study_at,duration FROM study_tasks WHERE id=?",
                             (review_id,)).fetchone()
            assert row["study_at"]==user_time.isoformat(timespec="minutes")
            assert row["duration"]==60
            # Other student's request never changes the pinned task.
            assert not has_manual_time(conn,review_id,other)
            # Solving the weakness clears the pending review, without
            # changing any of the regular roadmap lessons.
            project.record_quiz_learning_signal(conn,uid,sub,"Đổi mới","Chương 3",True)
            project.record_quiz_learning_signal(conn,uid,sub,"Đổi mới","Chương 3",True)
            assert project.sync_adaptive_review_task(conn,uid,sub) is None
            assert conn.execute("SELECT 1 FROM study_tasks WHERE id=?",
                                (review_id,)).fetchone() is None
            assert conn.execute("SELECT COUNT(*) FROM study_tasks WHERE source='roadmap'").fetchone()[0]==1
            conn.commit()
            conn.close()
        finally:
            project.DB_PATH,project.UPLOAD_DIR=db_path,uploads
    print("7.5.3 adaptive review slot, collision, user-edited time, cleanup PASS")


if __name__ == "__main__":
    run()
