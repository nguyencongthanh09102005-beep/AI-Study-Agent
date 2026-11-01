"""C3: same shared subject, individualized evidence and explainable next actions."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_decision_phase8 import decide_next_learning_step
from chapter_exercise_routes import ensure_exercise_schema
from syllabus_learning import syllabus_hash


def check():
    old_db,old_upload=project.DB_PATH,project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH=Path(folder)/"personalized.sqlite"
            project.UPLOAD_DIR=Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_exercise_schema(conn)
            now=project.now()
            profiles=[]
            for name,style,minutes in (("C3StudentA","visual",30),
                                       ("C3StudentB","balanced",90)):
                uid=conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,'student',?)
                """,(name,name+"@test.local","hash",now)).lastrowid
                sid=conn.execute("""
                    INSERT INTO subjects(user_id,name,code,credits,created_at)
                    VALUES(?,'Thuật toán','SAME301',3,?)
                """,(uid,now)).lastrowid
                conn.execute("""
                    INSERT INTO learning_profiles(
                        user_id,learning_style,preferred_study_time,
                        daily_minutes,goals,created_at,updated_at)
                    VALUES(?,?,?,?,'Đạt 8.0',?,?)
                """,(uid,style,"20:00",minutes,now,now))
                profiles.append((uid,sid))
            (uid_a,sid_a),(uid_b,sid_b)=profiles
            for uid,sid,correct in ((uid_a,sid_a,2),(uid_b,sid_b,9)):
                quiz=conn.execute("""
                    INSERT INTO quizzes(user_id,subject_id,title,payload,created_at)
                    VALUES(?,?,'Quiz giống nhau','[]',?)
                """,(uid,sid,now)).lastrowid
                conn.execute("""
                    INSERT INTO quiz_attempts(
                       user_id,quiz_id,score,correct_count,total_questions,created_at)
                    VALUES(?,?,?,?,10,?)
                """,(uid,quiz,10*correct,correct,now))
            conn.execute("""
                INSERT INTO learning_weaknesses(
                    user_id,subject_id,topic_key,topic,chapter,miss_count,
                    correct_count,last_seen_at)
                VALUES(?,?,?,'Độ phức tạp','Chương 1',3,0,?)
            """,(uid_a,sid_a,"complexity",now))
            conn.execute("""
                INSERT INTO chapter_exercise_attempts(
                    user_id,subject_id,chapter_number,syllabus_hash,
                    exercise_index,exercise_hash,exercise_text,
                    answer_text,feedback_status,created_at)
                VALUES(?,?,1,?,0,?,'BT01','Trình bày độ phức tạp','reviewed',?)
            """,(uid_a,sid_a,syllabus_hash("Đề cương"),syllabus_hash("BT01"),now))
            conn.commit()
            a=decide_next_learning_step(conn,uid_a,sid_a)
            b=decide_next_learning_step(conn,uid_b,sid_b)
            assert a["kind"]=="review",a
            assert b["kind"]=="continue",b
            assert a["practice_count"]==1 and a["practice_reviewed"]==1
            assert b["practice_count"]==0 and b["practice_reviewed"]==0
            assert a["practice_chapter"]==1
            assert any("30 phút/buổi" in x for x in a["evidence"])
            assert any("90 phút/buổi" in x for x in b["evidence"])
            assert any("3 lần" not in x or "Bài tập" not in x for x in b["evidence"])
            assert all("Bài tập tự luận riêng: 1" not in e for e in b["evidence"])
            assert any("Bài tập tự luận riêng: 1" in e for e in a["evidence"])
            assert "Đạt 8.0" in " ".join(b["evidence"])
            assert a["latest_score"]==20
            assert b["latest_score"]==90
            assert decide_next_learning_step(conn,uid_a,sid_b) is None
            # Rendering personalized Agent displays evidence without altering Quiz.
            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid_a
            page=client.get(f"/subjects/{sid_a}")
            assert page.status_code==200,page.get_data(as_text=True)[:400]
            html=page.get_data(as_text=True)
            assert "Bài tập tự luận riêng: 1" in html
            assert "Luyện bài tập Chương 1" in html
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("C3 personalized Agent PASS: different learner progress, goals, preferences and private exercise evidence")


if __name__=="__main__":
    check()
