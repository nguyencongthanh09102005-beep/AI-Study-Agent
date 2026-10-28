"""7.2-7.4: offline regeneration, 15/60 scoring integration, live schedule lock.

All tests use a temporary database and mock Gemini. Never touch real data.
"""
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import build_course_roadmap, parse_chapter_details, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import import_roadmap_lessons, ensure_session_schedule_schema
from chapter_material_routes import ensure_chapter_material_schema
from syllabus_routes import ensure_syllabus_schema
from syllabus_learning import syllabus_hash
from study_session_quiz_runtime import (
    ensure_quiz_runtime_schema, ordered_tasks, context_for_task, saved_quiz,
    prepare_step, preparation_status, quiz_access, start_quiz,
)
from chapter_chat_context import LessonContextError


def login(client, uid):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = uid


def run():
    with TemporaryDirectory() as folder:
        prev_db, prev_upload, prev_builder = (
            project.DB_PATH, project.UPLOAD_DIR, project.build_quiz)
        try:
            project.DB_PATH = Path(folder) / "quiz7234.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            ensure_chapter_material_schema(conn)
            ensure_quiz_runtime_schema(conn)
            now = project.now()
            def make_user(role, email):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """, ("Quiz test", email, "h", role, now)).lastrowid
            student = make_user("student", "study7234a@example.test")
            other = make_user("student", "study7234b@example.test")
            admin = make_user("admin", "study7234admin@example.test")
            subject = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Giải thuật", "ALGO7234", now)).lastrowid
            syllabus = (
                "Chương 1. Danh sách liên kết\n"
                "1.1. Cấu trúc node và liên kết\n"
                "1.2. Duyệt danh sách đơn\n"
                "1.3. Xóa node đầu\n"
                "Mục tiêu: Hiểu cách hoạt động của danh sách liên kết\n"
                "Bài tập: Viết hàm duyệt danh sách"
            )
            units = [{"title": "Chương 1. Danh sách liên kết",
                      "evidence": "Chương 1. Danh sách liên kết"}]
            fp = syllabus_hash(syllabus)
            doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,
                stored_name,extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (student, subject, "Đề cương", "syllabus.txt", syllabus, now)).lastrowid
            conn.execute("UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                         (doc, subject))
            conn.execute("""
                INSERT INTO syllabus_reviews(user_id,subject_id,source_hash,
                source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, subject, fp, "personal",
                  json.dumps(units, ensure_ascii=False), now))
            sessions = build_course_roadmap(
                parse_chapter_details(syllabus, units), [],
                {"goal": "Thuần thục node", "preferred_time": "19:00",
                 "daily_minutes": 45}, start_date=date(2026, 11, 2))
            assert len(sessions) >= 2, "Need a final comprehensive lesson"
            conn.execute("""
                INSERT INTO course_roadmaps(user_id,subject_id,source_hash,
                units_hash,sessions_json,updated_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, fp, unit_fingerprint(units),
                  json.dumps(sessions, ensure_ascii=False), now))
            import_roadmap_lessons(conn, student, subject, sessions, now)
            task_rows = ordered_tasks(conn, student, subject)
            shared = project.ensure_shared_subject_for_user_subject(conn, student, subject)
            assert shared
            conn.execute("UPDATE shared_subjects SET admin_managed=1 WHERE id=?",
                         (shared["id"],))
            conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,
                stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,1,?,?)
            """, (shared["id"], "Đề cương chuẩn", "official.pdf",
                  syllabus, admin, now))
            approved_id = conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,
                stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,0,?,?)
            """, (shared["id"], "Slide đã duyệt", "source.pdf",
                  "Một node có dữ liệu và con trỏ. Con trỏ next liên kết node kế. "
                  "Duyệt danh sách bắt đầu từ head và chuyển sang node tiếp theo. "
                  "Dừng khi con trỏ tiếp theo bằng NULL. Dùng con trỏ để xóa node đầu.",
                  admin, now)).lastrowid
            conn.execute("""
                INSERT INTO shared_document_chapters(document_id,shared_subject_id,
                chapter_key,syllabus_hash,confirmed_by,confirmed_at)
                VALUES(?,?,?, ?,?,?)
            """, (approved_id, shared["id"], "1", fp, admin, now))
            conn.commit()
            conn.close()

            calls = []
            def mock_build(text, count, focus_topics=None, session_mode=False):
                assert session_mode
                assert "Giảng viên môn" not in text
                calls.append(count)
                return [
                    {"question": f"Node và con trỏ trong lần {len(calls)}, câu {i} hoạt động thế nào?",
                     "topic": "Cấu trúc node", "chapter": "Chương 1",
                     "options": ["Theo head", "Theo tail", "Theo root", "Theo leaf"],
                     "answer": i % 4}
                    for i in range(count)
                ]
            project.build_quiz = mock_build
            client = project.app.test_client()
            endpoint = f"/api/subjects/{subject}/quiz-preparation"
            assert client.get(endpoint).status_code == 401
            login(client, other)
            assert client.get(endpoint).status_code == 404
            login(client, admin)
            assert client.get(endpoint).status_code == 403
            login(client, student)
            route = f"/subjects/{subject}/learning-path"
            assert client.get(route).status_code == 200
            with client.session_transaction() as sess:
                csrf = sess["session_quiz_csrf"]
            assert client.post(endpoint + "/next", json={}).status_code == 403
            assert client.post(endpoint + "/next", json={},
                               headers={"X-Quiz-CSRF": "wrong"}).status_code == 403
            headers = {"X-Quiz-CSRF": csrf}
            max_steps = len(task_rows) * 3 + 20
            for _ in range(max_steps):
                step = client.post(endpoint + "/next", json={}, headers=headers)
                assert step.status_code == 200, step.get_data(as_text=True)
                if step.get_json()["done"]:
                    break
            else:
                raise AssertionError("Quiz preparation did not finish")
            status = client.get(endpoint).get_json()
            assert status["done"] is True
            assert status["ready"] == len(task_rows)
            conn = project.db()
            for i, task in enumerate(task_rows):
                context, prior, count = context_for_task(project, conn, student, task["id"])
                quiz = saved_quiz(conn, student, task["id"], context["source_signature"])
                assert quiz, (task, count)
                questions = json.loads(quiz["payload"])
                assert len(questions) == (60 if i == len(task_rows)-1 else 15)
                assert len({q["question"] for q in questions}) == len(questions)
            first_context, _, _ = context_for_task(project, conn, student, task_rows[0]["id"])
            first_quiz = saved_quiz(conn, student, task_rows[0]["id"],
                                    first_context["source_signature"])["id"]
            final_context, _, _ = context_for_task(project, conn, student, task_rows[-1]["id"])
            final_quiz = saved_quiz(conn, student, task_rows[-1]["id"],
                                    final_context["source_signature"])["id"]
            assert len(calls) == len(task_rows)-1 + len(task_rows)-1, calls
            assert client.get("/quiz").status_code == 200
            locked_html = client.get("/quiz").get_data(as_text=True)
            assert f'data-quiz-id="{first_quiz}"' not in locked_html
            assert f'data-quiz-id="{final_quiz}"' not in locked_html
            assert client.get(f"/api/mobile/quizzes/{first_quiz}").status_code == 409
            blocked = client.post("/api/quiz/submit", json={
                "quiz_id": first_quiz, "answers": [0]*15
            })
            assert blocked.status_code == 409
            planned = datetime.fromisoformat(task_rows[0]["study_at"])
            assert not quiz_access(conn, project, student, first_quiz,
                                   planned-timedelta(minutes=1))["can_start"]
            try:
                start_quiz(conn, project, student, first_quiz,
                           planned-timedelta(minutes=1))
                raise AssertionError("Should not unlock early")
            except LessonContextError as exc:
                assert exc.status == 409

            # Reschedule before starting; the lock follows current study_tasks,
            # and questions remain unchanged (no new Gemini calls).
            new_start = planned+timedelta(hours=2)
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                         (new_start.isoformat(timespec="minutes"),
                          task_rows[0]["id"]))
            assert not quiz_access(conn, project, student, first_quiz,
                                   planned+timedelta(minutes=1))["can_start"]
            assert quiz_access(conn, project, student, first_quiz,
                               new_start+timedelta(minutes=1))["can_start"]
            assert start_quiz(conn, project, student, first_quiz,
                              new_start+timedelta(minutes=1))["allowed"]
            # The previously granted in-progress attempt survives further
            # schedule changes until its originally granted window ends.
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                         ((new_start+timedelta(hours=2)).isoformat(timespec="minutes"),
                          task_rows[0]["id"]))
            assert quiz_access(conn, project, student, first_quiz,
                               new_start+timedelta(minutes=3))["allowed"]
            assert not quiz_access(conn, project, student, first_quiz,
                                   new_start+timedelta(hours=1))["allowed"]
            conn.commit()
            conn.close()

            assert client.get("/quiz").status_code == 200
            # Still locked in the real current wall clock, because the test's
            # future planned window has not actually started.
            assert client.post("/api/quiz/submit", json={
                "quiz_id": first_quiz, "answers": [0]*15
            }).status_code == 409

            # Approval revoked => neither quiz nor answer keys leak, even with
            # the previous grant; historical quiz and answers are preserved.
            conn = project.db()
            conn.execute("DELETE FROM shared_document_chapters WHERE document_id=?",
                         (approved_id,))
            conn.commit()
            conn.close()
            assert client.get(f"/api/mobile/quizzes/{first_quiz}").status_code == 409
            assert client.post("/api/quiz/submit", json={
                "quiz_id": first_quiz, "answers": [0]*15
            }).status_code == 409
            conn = project.db()
            assert conn.execute("SELECT COUNT(*) FROM quizzes WHERE user_id=?",
                                (student,)).fetchone()[0] == len(task_rows)
            conn.close()
        finally:
            project.DB_PATH, project.UPLOAD_DIR = prev_db, prev_upload
            project.build_quiz = prev_builder


if __name__ == "__main__":
    run()
    print("7.2-7.4 pre-generation / 15-60 / schedule unlock / server gate PASS")
