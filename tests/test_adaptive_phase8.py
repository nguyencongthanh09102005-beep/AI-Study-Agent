"""Phase 8.4 acceptance/regression: adaptive decisions, explanations and consent.

Runs offline: no Gemini calls, no shared DB mutation, no changes to main.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_review_schedule import local_now
from adaptive_decision_phase8 import decide_next_learning_step
from adaptive_plan_phase8 import proposal_for_subject, apply_student_choice


def run():
    with TemporaryDirectory() as d:
        old_db, old_uploads = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(d) / "phase8.sqlite"
            project.UPLOAD_DIR = Path(d) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            stamp = project.now()
            uid = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('P8 Student','phase8@test.local','hash','student',?)
            """, (stamp,)).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Other Student','phase8-other@test.local','hash','student',?)
            """, (stamp,)).lastrowid
            sid = conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử Đảng','LSD8',3,?)
            """, (uid,stamp)).lastrowid
            other_sid = conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Môn riêng','PRIVATE8',3,?)
            """, (other,stamp)).lastrowid
            assert decide_next_learning_step(conn,other,sid) is None
            assert decide_next_learning_step(conn,uid,sid)["kind"]=="collect"

            qid = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,title,payload,created_at)
                VALUES(?,?,'Quiz test','[]',?)
            """, (uid,sid,stamp)).lastrowid
            conn.execute("""
                INSERT INTO quiz_attempts(user_id,quiz_id,score,correct_count,
                                          total_questions,answers_json,created_at)
                VALUES(?,?,30,3,10,'[]',?)
            """, (uid,qid,stamp))
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",False)
            d1=decide_next_learning_step(conn,uid,sid)
            assert d1["kind"]=="verify",d1
            assert any("3/10" in x for x in d1["evidence"])
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",False)
            d2=decide_next_learning_step(conn,uid,sid)
            assert d2["kind"]=="review" and d2["weakness_count"]==1
            assert d2["material_chapter"]==1
            assert any("Tiến độ môn" in x for x in d2["evidence"])

            future=(local_now()+timedelta(days=2)).date()
            review_at=datetime.combine(future,datetime.min.time()).replace(hour=19)
            roadmap_at=review_at-timedelta(hours=1)
            manual_at=review_at+timedelta(minutes=75)
            iso=lambda date: date.isoformat(timespec="minutes")
            rid=conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                                        note,done,source,created_at)
                VALUES(?,?,'Ôn điểm yếu',?,45,'',0,'adaptive',?)
            """, (uid,sid,iso(review_at),stamp)).lastrowid
            task=conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                                        note,done,source,created_at)
                VALUES(?,?,'Học Chương 2',?,45,'',0,'roadmap',?)
            """, (uid,sid,iso(roadmap_at),stamp)).lastrowid
            manual=conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                                        note,done,source,created_at)
                VALUES(?,?,'Lịch cá nhân',?,45,'',0,'manual',?)
            """, (uid,sid,iso(manual_at),stamp)).lastrowid
            # Different student's data cannot affect this preview.
            conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,
                                        note,done,source,created_at)
                VALUES(?,?,'Other private',?,45,'',0,'manual',?)
            """, (other,other_sid,iso(review_at+timedelta(hours=2)),stamp))
            conn.commit()

            proposal=proposal_for_subject(conn,uid,sid)
            assert proposal and proposal["task_id"]==task,proposal
            assert datetime.fromisoformat(proposal["new_at"])>=review_at+timedelta(minutes=45)
            proposed=datetime.fromisoformat(proposal["new_at"])
            assert proposed>=manual_at+timedelta(minutes=45) or proposed+timedelta(minutes=45)<=manual_at

            # Preview must never write schedules.
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (task,)).fetchone()[0]==iso(roadmap_at)
            try:
                apply_student_choice(conn,uid,sid,"invalid-key","accept")
            except ValueError:
                pass
            else:
                raise AssertionError("Stale/tampered proposal was accepted")
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (task,)).fetchone()[0]==iso(roadmap_at)
            assert proposal_for_subject(conn,other,sid) is None

            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid
            page=client.get(f"/subjects/{sid}")
            assert page.status_code==200
            html=page.get_data(as_text=True)
            assert "Vì sao Study Agent" in html and "Đồng ý đổi giờ" in html
            with client.session_transaction() as sess:
                csrf=sess["adaptive_plan_csrf"]
            bad=client.post(f"/subjects/{sid}/adaptive-plan",data={
                "proposal_key":proposal["proposal_key"],"choice":"accept"
            })
            assert bad.status_code==403
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (task,)).fetchone()[0]==iso(roadmap_at)

            # Declining preserves all events and persists the user's refusal.
            refused=client.post(f"/subjects/{sid}/adaptive-plan",data={
                "csrf_token":csrf,"proposal_key":proposal["proposal_key"],
                "choice":"dismiss"
            })
            assert refused.status_code==303
            assert proposal_for_subject(conn,uid,sid)["dismissed"]
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (task,)).fetchone()[0]==iso(roadmap_at)
            repeated=client.post(f"/subjects/{sid}/adaptive-plan",data={
                "csrf_token":csrf,"proposal_key":proposal["proposal_key"],
                "choice":"accept"
            })
            assert repeated.status_code==303
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (task,)).fetchone()[0]==iso(roadmap_at)

            # Fresh review time creates a fresh, independently confirmable proposal.
            changed_review=review_at+timedelta(days=1)
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                         (iso(changed_review),rid))
            conn.commit()
            fresh=proposal_for_subject(conn,uid,sid)
            assert fresh and fresh["proposal_key"]!=proposal["proposal_key"]
            accepted=client.post(f"/subjects/{sid}/adaptive-plan",data={
                "csrf_token":csrf,"proposal_key":fresh["proposal_key"],
                "choice":"accept"
            })
            assert accepted.status_code==303
            final=conn.execute("SELECT study_at,duration FROM study_tasks WHERE id=?",
                               (task,)).fetchone()
            assert final["study_at"]==fresh["new_at"] and final["duration"]==45
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (manual,)).fetchone()[0]==iso(manual_at)
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (rid,)).fetchone()[0]==iso(changed_review)
            assert proposal_for_subject(conn,uid,sid) is None  # moved after review
            assert conn.execute("""
                SELECT COUNT(*) FROM adaptive_plan_decisions
                WHERE user_id=? AND subject_id=?
            """, (uid,sid)).fetchone()[0]==2

            # Once weak signals are solved, don't prescribe unnecessary review.
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",True)
            project.record_quiz_learning_signal(conn,uid,sid,"Cương lĩnh","Chương 1",True)
            conn.execute("""
                INSERT INTO quiz_attempts(user_id,quiz_id,score,correct_count,
                                          total_questions,answers_json,created_at)
                VALUES(?,?,90,9,10,'[]',?)
            """, (uid,qid,stamp))
            assert decide_next_learning_step(conn,uid,sid)["kind"]=="continue"
            assert proposal_for_subject(conn,uid,sid) is None
            conn.commit()
            conn.close()
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_uploads
    print("Phase 8.1-8.4 decision, evidence, consent, CSRF, ownership, collision PASS")


if __name__=="__main__":
    run()
