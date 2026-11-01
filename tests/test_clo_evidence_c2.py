"""C2: CLO mapping confirmation, source integrity and personal Quiz/exercise evidence."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from chapter_exercise_routes import ensure_exercise_schema
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema


def check():
    syllabus="""ĐỀ CƯƠNG MÔN
Chương 1. Đại cương thuật toán
Thời lượng: 6 tiết | Liên kết chuẩn đầu ra: CLO1
Mục tiêu sau chương
Nắm được độ phức tạp thuật toán.
Nội dung kiến thức
• 1.1. Big O
Bài tập
BT01: Giải thích Big O.
Chương 2. Danh sách liên kết
Thời lượng: 6 tiết | Liên kết chuẩn đầu ra: CLO2
Mục tiêu sau chương
Hiểu node.
Nội dung kiến thức
• 2.1. Duyệt danh sách liên kết
Bài tập
BT02: Vẽ node.
""".strip()
    old_db,old_upload=project.DB_PATH,project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as path:
            project.DB_PATH=Path(path)/"clo.sqlite"
            project.UPLOAD_DIR=Path(path)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_syllabus_schema(conn)
            ensure_exercise_schema(conn)
            now=project.now()
            def user(name):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,'student',?)
                """,(name,name+"@test.local","hash",now)).lastrowid
            a,b=user("CLOA"),user("CLOB")
            def make_subject(uid):
                return conn.execute("""
                    INSERT INTO subjects(user_id,name,code,created_at)
                    VALUES(?,'Thuật toán','CLOTEST',?)
                """,(uid,now)).lastrowid
            sid_a,sid_b=make_subject(a),make_subject(b)
            shared=conn.execute("""
                INSERT INTO shared_subjects(
                    subject_key,code,name,syllabus_text,admin_managed,
                    created_at,updated_at)
                VALUES(?,?,?, ?,1,?,?)
            """,(project._normalize_subject_key("CLOTEST","Thuật toán"),
                 "CLOTEST","Thuật toán",syllabus,now,now)).lastrowid
            conn.execute("UPDATE subjects SET shared_subject_id=? WHERE id IN (?,?)",
                         (shared,sid_a,sid_b))
            hash_=syllabus_hash(syllabus)
            units=json.dumps([
                {"title":"Chương 1. Đại cương thuật toán",
                 "evidence":"Chương 1. Đại cương thuật toán"},
                {"title":"Chương 2. Danh sách liên kết",
                 "evidence":"Chương 2. Danh sách liên kết"}],ensure_ascii=False)
            for uid,sid in ((a,sid_a),(b,sid_b)):
                conn.execute("""
                    INSERT INTO syllabus_reviews(
                        user_id,subject_id,source_hash,source_kind,
                        units_json,status,updated_at)
                    VALUES(?,?,?,'shared',?,'confirmed',?)
                """,(uid,sid,hash_,units,now))
            quiz_questions=[{
                "question":f"Câu {i} Big O?","chapter":"Chương 1",
                "topic":"Big O","answer":0,"options":["A","B","C","D"]
            } for i in range(6)]
            from study_session_quiz import ensure_session_quiz_schema
            ensure_session_quiz_schema(conn)
            def make_attempt(uid,sid,answers):
                quiz=conn.execute("""
                    INSERT INTO quizzes(user_id,subject_id,title,payload,created_at)
                    VALUES(?,?,?,?,?)
                """,(uid,sid,"Quiz Chương 1",json.dumps(quiz_questions),now)).lastrowid
                conn.execute("""
                    INSERT INTO quiz_session_links(
                        quiz_id,task_id,user_id,subject_id,chapter_number,
                        session_title,session_signature,source_signature,source_ids_json,created_at)
                    VALUES(?,NULL,?,?,1,'Bài chính khóa 1','test-session','test-source','[]',?)
                """,(quiz,uid,sid,now))
                conn.execute("""
                    INSERT INTO quiz_attempts(
                        user_id,quiz_id,score,correct_count,total_questions,
                        answers_json,created_at)
                    VALUES(?,?,?,?,?,?,?)
                """,(uid,quiz,100*answers.count(0)/len(answers),
                     answers.count(0),6,json.dumps(answers),now))
            make_attempt(a,sid_a,[0,0,0,0,1,1])
            make_attempt(b,sid_b,[0,0,0,0,0,0])
            conn.execute("""
                INSERT INTO chapter_exercise_attempts(
                  user_id,subject_id,chapter_number,syllabus_hash,exercise_index,
                  exercise_hash,exercise_text,answer_text,feedback_status,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """,(a,sid_a,1,hash_,0,syllabus_hash("BT01: Giải thích Big O."),
                 "BT01: Giải thích Big O.","Lời giải riêng A","reviewed",now))
            conn.commit()
            def client(uid):
                c=project.app.test_client()
                with c.session_transaction() as sess:
                    sess["user_id"]=uid
                return c
            ca,cb=client(a),client(b)
            path_a=f"/subjects/{sid_a}/clo"
            path_b=f"/subjects/{sid_b}/clo"
            assert cb.get(path_a).status_code==404
            assert ca.get(path_a).status_code==200
            preview=ca.get(path_a).get_data(as_text=True)
            assert "Chưa xác nhận liên kết" in preview
            assert "CLO1" in preview and "CLO2" in preview
            with ca.session_transaction() as sess:
                token=sess["clo_mapping_csrf"]
            assert ca.post(path_a,data={"csrf_token":"invalid","clo_1":"CLO1"}).status_code==403
            assert ca.post(path_a,data={"csrf_token":token,"clo_1":"CLO99"}).status_code==400
            assert ca.post(path_a,data={
                "csrf_token":token,"clo_1":"CLO1","clo_2":"CLO2"
            }).status_code==303
            evaluated=ca.get(path_a).get_data(as_text=True)
            assert "Đã lưu liên kết CLO" in evaluated
            assert "Nên ôn lại" in evaluated
            assert "Quiz đúng 4/6 câu" in evaluated
            assert "Bài tập đã nộp 1 lượt" in evaluated
            assert "Nhận xét AI có dẫn chứng 1 lượt" in evaluated
            # Student B sees distinct evidence; no automatic CLO mastery.
            cb.get(path_b)
            with cb.session_transaction() as sess:
                bt=sess["clo_mapping_csrf"]
            assert cb.post(path_b,data={
                "csrf_token":bt,"clo_1":"CLO1","clo_2":"CLO2"
            }).status_code==303
            other=cb.get(path_b).get_data(as_text=True)
            assert "Có tín hiệu tích cực" in other
            assert "Quiz đúng 6/6 câu" in other
            assert "Bài tập đã nộp 0 lượt" in other
            assert "điểm chính thức" in other or "chấm CLO chính thức" in other
            # Changing the verified source invalidates confirmed CLO mapping.
            conn.execute("UPDATE shared_subjects SET syllabus_text=? WHERE id=?",
                         (syllabus.replace("CLO1","CLO3"),shared))
            conn.commit()
            assert ca.post(path_a,data={
                "csrf_token":token,"clo_1":"CLO1"
            }).status_code==409
            assert ca.get(path_a).status_code==303
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("C2 CLO PASS: confirmed mappings, source versioning, per-user quiz & exercise evidence")


if __name__=="__main__":
    check()
