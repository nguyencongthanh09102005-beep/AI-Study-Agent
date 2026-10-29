"""Integration QA: manual lesson -> private document -> optional Quiz -> study room.

No Gemini calls or real student records. A disposable DB is used.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from manual_lesson_routes import ensure_schema


def run():
    old_db,old_upload=project.DB_PATH,project.UPLOAD_DIR
    old_build,old_gemini=project.build_quiz,project.gemini_generate
    generated=[]
    content="Chương 1. Khái niệm. "+("Nội dung lịch sử lấy từ giáo trình chính thức. "*30)
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH=Path(folder)/"manual.sqlite"
            project.UPLOAD_DIR=Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_schema(conn)
            timestamp=project.now()
            def make_user(name):
                return conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,'student',?)",
                    (name,name+"@unit.local","hash",timestamp)
                ).lastrowid
            user,other=make_user("personal-test"),make_user("other-personal")
            def make_subject(uid,code):
                return conn.execute(
                    "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                    (uid,"Môn "+code,code,timestamp)
                ).lastrowid
            subject=make_subject(user,"HIS")
            other_subject=make_subject(user,"MATH")
            stranger_subject=make_subject(other,"PRIVATE")
            def make_doc(uid,sid,name):
                return conn.execute("""
                    INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                          extracted_text,created_at)
                    VALUES(?,?,?,?,?,?)
                """,(uid,sid,name,name,content,timestamp)).lastrowid
            doc=make_doc(user,subject,"mine.pdf")
            wrong_course=make_doc(user,other_subject,"wrong-course.pdf")
            private_other=make_doc(other,stranger_subject,"other-student.pdf")
            conn.commit()

            client=project.app.test_client()
            outsider=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=user
                sess["user_name"]="Student"
            with outsider.session_transaction() as sess:
                sess["user_id"]=other
                sess["user_name"]="Other"

            day=(datetime.now()+timedelta(days=2)).strftime("%Y-%m-%dT19:00")
            base={"title":"Học bổ sung chương 1","subject_id":str(subject),
                  "study_at":day,"duration":"45","note":"Ôn chủ đề 1"}
            listing=client.get("/study-plan")
            assert listing.status_code==200
            page=listing.get_data(as_text=True)
            assert 'id="taskPersonalDocument"' in page
            assert "Chuẩn bị Quiz 10 câu" in page
            assert 'data-subject-id="'+str(subject)+'"' in page
            assert "mine.pdf" in page
            assert "other-student.pdf" not in page
            assert "manual_task_document.js" in page

            for invalid_doc in (wrong_course,private_other,99999):
                res=client.post("/study-plan/tasks/create",data={
                    **base,"document_id":str(invalid_doc),"prepare_quiz":"1"
                })
                assert res.status_code==400
            assert conn.execute("SELECT count(*) FROM study_tasks WHERE user_id=?",
                                (user,)).fetchone()[0]==0

            # Legacy manual reminder/task remains valid without a personal document.
            no_file=client.post("/study-plan/tasks/create",data=base)
            assert no_file.status_code in (302,303)
            assert no_file.headers["Location"].endswith("/study-plan")

            # Add a linked manual session with no AI expense by default.
            linked=client.post("/study-plan/tasks/create",data={
                **base,"document_id":str(doc)
            })
            assert linked.status_code==303, linked.status_code
            manual_id=int(linked.headers["Location"].split("/")[-1])
            lesson=client.get(linked.headers["Location"])
            assert lesson.status_code==200
            room_html=lesson.get_data(as_text=True)
            assert "mine.pdf" in room_html
            assert "Ôn chủ đề 1" in room_html
            assert "Hỏi AI về tài liệu này" in room_html
            assert "Chuẩn bị Quiz 10 câu" in room_html
            assert f"/documents/{doc}/file?preview=1" in room_html
            assert "Không gian học cá nhân" in room_html
            assert outsider.get(f"/manual-study/{manual_id}").status_code==404
            assert outsider.post(f"/manual-study/{manual_id}/prepare-quiz",
                                data={}).status_code==403
            assert client.post(f"/manual-study/{manual_id}/prepare-quiz",
                               data={"csrf_token":"spoof"}).status_code==403
            assert conn.execute("SELECT count(*) FROM quizzes WHERE user_id=?",
                                (user,)).fetchone()[0]==0

            with client.session_transaction() as sess:
                token=sess["manual_lesson_csrf"]
            def fake_build(text,n):
                generated.append((text,n))
                return [{
                    "question":f"Câu {i} về chương 1?",
                    "options":["1","2","3","4"],
                    "answer":0,"topic":"Chương 1"
                } for i in range(n)]
            project.build_quiz=fake_build
            prepared=client.post(f"/manual-study/{manual_id}/prepare-quiz",
                                 data={"csrf_token":token})
            assert prepared.status_code==303
            assert generated and generated[-1][1]==10
            record=conn.execute("""
                SELECT quiz_id,quiz_fingerprint FROM manual_lesson_documents
                WHERE task_id=? AND user_id=?
            """,(manual_id,user)).fetchone()
            assert record["quiz_id"] and record["quiz_fingerprint"]
            quiz_id=record["quiz_id"]
            assert conn.execute("SELECT document_id FROM quizzes WHERE id=?",
                                (quiz_id,)).fetchone()[0]==doc
            assert "Mở Quiz đã chuẩn bị" in client.get(f"/manual-study/{manual_id}").get_data(as_text=True)
            # Repeated requests do not charge Gemini a second time or duplicate Quiz.
            before=len(generated)
            prepared_again=client.post(f"/manual-study/{manual_id}/prepare-quiz",
                                       data={"csrf_token":token})
            assert prepared_again.status_code==303
            assert len(generated)==before
            assert conn.execute("SELECT count(*) FROM quizzes WHERE user_id=?",
                                (user,)).fetchone()[0]==1
            linked_quiz=client.get(f"/quiz?quiz_id={quiz_id}")
            assert linked_quiz.status_code==200
            html=linked_quiz.get_data(as_text=True)
            assert f'id="quiz-work-{quiz_id}"' in html
            assert f'id="quiz-work-{quiz_id}" data-quiz-id="{quiz_id}"' in html

            project.gemini_generate=lambda p: (
                "Tài liệu ghi khái niệm cơ bản, theo mine.pdf.",None
            )
            q=client.post(f"/manual-study/{manual_id}/ask",data={
                "csrf_token":token, "question":"Giải thích chương 1"
            })
            assert q.status_code==303
            answered=client.get(f"/manual-study/{manual_id}").get_data(as_text=True)
            assert "Tài liệu ghi khái niệm cơ bản" in answered
            assert "mine.pdf" in answered

            # Edited manual tasks cannot silently switch to a mismatched subject.
            moved=client.post(f"/study-plan/tasks/{manual_id}/update",data={
                **base,"subject_id":str(other_subject)
            })
            assert moved.status_code==400
            unchanged=conn.execute(
                "SELECT subject_id FROM study_tasks WHERE id=?",(manual_id,)
            ).fetchone()[0]
            assert unchanged==subject

            # Opt-in at creation generates exactly once; Gemini failures are
            # non-destructive and retry can be triggered from the private room.
            project.build_quiz=lambda text,n: []
            failed=client.post("/study-plan/tasks/create",data={
                **base,"title":"Quiz lỗi nhưng vẫn có lịch",
                "document_id":str(doc),"prepare_quiz":"1"
            })
            assert failed.status_code==303
            err_page=client.get(failed.headers["Location"]).get_data(as_text=True)
            assert "Gemini chưa tạo đủ" in err_page
            assert "Quiz lỗi nhưng vẫn có lịch" in err_page
            assert conn.execute("SELECT count(*) FROM study_tasks WHERE user_id=?",
                                (user,)).fetchone()[0]==3
            assert conn.execute("SELECT count(*) FROM quizzes WHERE user_id=?",
                                (user,)).fetchone()[0]==1

            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
        project.build_quiz,project.gemini_generate=old_build,old_gemini
    print("Manual lesson PASS: owner/subject ACL, opt-in Quiz, scoped AI, safe failure, legacy tasks")


if __name__=="__main__":
    run()
