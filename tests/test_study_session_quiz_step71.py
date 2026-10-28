"""Phase 7.1 integration tests: verified per-session Quiz context and optional
provenance links. No Gemini calls; tests run against an isolated SQLite DB."""
import json
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chapter_chat_context import LessonContextError
from course_path_learning import (
    build_course_roadmap, parse_chapter_details, unit_fingerprint,
)
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import import_roadmap_lessons, ensure_session_schedule_schema
from chapter_material_routes import ensure_chapter_material_schema
from syllabus_routes import ensure_syllabus_schema
from syllabus_learning import syllabus_hash
from study_session_quiz import (
    ensure_session_quiz_schema, get_session_quiz_context, link_generated_quiz,
)


def login(client, user):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = user
        sess["user_name"] = "Student"


def verify():
    with TemporaryDirectory() as temp:
        old_db, old_uploads = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(temp) / "quiz71.sqlite"
            project.UPLOAD_DIR = Path(temp) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            ensure_chapter_material_schema(conn)
            ensure_session_quiz_schema(conn)
            created = project.now()

            def user(role, email):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """, ("Quiz test", email, "hash", role, created)).lastrowid

            student = user("student", "quiz71-a@example.test")
            other = user("student", "quiz71-b@example.test")
            admin = user("admin", "quiz71-admin@example.test")
            subject = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Giải thuật", "ALG71", created)).lastrowid
            other_subject = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (other, "Khác", "OTHER71", created)).lastrowid
            syllabus = ("Chương 1. Danh sách liên kết\n"
                        "1.1. Node và con trỏ head\n"
                        "1.2. Duyệt danh sách đơn\n"
                        "Mục tiêu: Hiểu cấu trúc node\n"
                        "Bài tập: Viết thuật toán duyệt")
            units = [{"title": "Chương 1. Danh sách liên kết",
                      "evidence": "Chương 1. Danh sách liên kết"}]
            fingerprint = syllabus_hash(syllabus)
            syllabus_doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, "Đề cương cá nhân", "syllabus71.txt",
                  syllabus, created)).lastrowid
            conn.execute("UPDATE subjects SET personal_syllabus_document_id=? "
                         "WHERE id=?", (syllabus_doc, subject))
            private_doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, "Tài liệu cá nhân riêng", "private71.pdf",
                  "Private secret only", created)).lastrowid
            conn.execute("""
                INSERT INTO syllabus_reviews(user_id,subject_id,source_hash,
                source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, subject, fingerprint, "personal",
                  json.dumps(units, ensure_ascii=False), created))
            roadmap = build_course_roadmap(
                parse_chapter_details(syllabus, units),
                [{"id": private_doc, "name": "Tài liệu cá nhân riêng",
                  "text": "Private secret only", "kind": "personal"}],
                {"goal": "Hiểu bài", "preferred_time": "19:00",
                 "daily_minutes": 45}, start_date=date(2026, 11, 2)
            )
            assert roadmap
            conn.execute("""
                INSERT INTO course_roadmaps(user_id,subject_id,source_hash,
                  units_hash,sessions_json,updated_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, fingerprint, unit_fingerprint(units),
                  json.dumps(roadmap, ensure_ascii=False), created))
            summary = import_roadmap_lessons(conn, student, subject, roadmap, created)
            assert summary["created"] >= 1
            task = conn.execute("""
                SELECT id FROM study_tasks
                WHERE user_id=? AND subject_id=? AND source='roadmap'
                ORDER BY roadmap_session_id LIMIT 1
            """, (student, subject)).fetchone()["id"]
            old_quiz = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Quiz cũ','[]',?)
            """, (student, subject, created)).lastrowid
            other_quiz = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Quiz tài khoản khác','[]',?)
            """, (other, other_subject, created)).lastrowid
            conn.execute("""
                INSERT INTO quiz_attempts(user_id,quiz_id,score,correct_count,
                total_questions,answers_json,created_at) VALUES(?,?,100,1,1,'[0]',?)
            """, (student, old_quiz, created))
            conn.commit()
            conn.close()

            api = f"/api/study-plan/tasks/{task}/quiz-context"
            page = f"/quiz?task_id={task}"
            client = project.app.test_client()
            assert client.get(api).status_code == 401
            login(client, other)
            assert client.get(api).status_code == 404
            assert client.get(page).status_code == 404
            login(client, admin)
            assert client.get(api).status_code == 403
            assert client.get(page).status_code == 403
            login(client, student)
            assert client.get("/quiz?task_id=not-a-number").status_code == 400
            unready = client.get(api)
            assert unready.status_code == 200, unready.get_data(as_text=True)
            before = unready.get_json()
            assert before["ready"] is False
            assert before["source_names"] == []
            assert "Private secret only" not in unready.get_data(as_text=True)
            page_before = client.get(page).get_data(as_text=True)
            assert "QUIZ THEO BUỔI HỌC" in page_before
            assert "Chưa đủ nguồn được duyệt" in page_before
            assert "Quiz cũ" in page_before

            # Admin-approved official syllabus + readable, chapter-mapped file.
            conn = project.db()
            shared = project.ensure_shared_subject_for_user_subject(conn, student, subject)
            shared_id = shared["id"]
            conn.execute("UPDATE shared_subjects SET admin_managed=1 WHERE id=?",
                         (shared_id,))
            conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,
                stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,1,?,?)
            """, (shared_id, "Đề cương chính thức", "official71.txt",
                  syllabus, admin, created))
            doc_id = conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,
                stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,0,?,?)
            """, (shared_id, "Slide chương 1 đã duyệt", "approved71.pdf",
                  "Node gồm vùng dữ liệu và con trỏ next. Duyệt node từ head.", admin, created)).lastrowid
            unapproved_id = conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,
                stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,0,?,?)
            """, (shared_id, "Tài liệu chưa duyệt", "unapproved71.pdf",
                  "Tài liệu không được phép dùng", admin, created)).lastrowid
            conn.execute("""
                INSERT INTO shared_document_chapters(document_id,shared_subject_id,
                chapter_key,syllabus_hash,confirmed_by,confirmed_at)
                VALUES(?,?,?, ?,?,?)
            """, (doc_id, shared_id, "1", fingerprint, admin, created))
            conn.commit()
            conn.close()
            response = client.get(api)
            assert response.status_code == 200, response.get_data(as_text=True)
            ready = response.get_json()
            assert ready["ready"] is True, ready
            assert ready["task_id"] == task
            assert ready["subject_id"] == subject
            assert ready["chapter_number"] == 1
            assert ready["source_names"] == ["Slide chương 1 đã duyệt"]
            assert "source_signature" not in ready
            assert "source_ids" not in ready
            assert "extracted_text" not in response.get_data(as_text=True)
            assert "Tài liệu cá nhân riêng" not in response.get_data(as_text=True)
            assert "Tài liệu chưa duyệt" not in response.get_data(as_text=True)
            ready_page = client.get(page)
            assert ready_page.status_code == 200
            html = ready_page.get_data(as_text=True)
            assert "Nguồn đã xác thực" in html
            assert "Slide chương 1 đã duyệt" in html
            assert "Quiz theo buổi được chuẩn bị ở trang Lộ trình theo chương" in html
            assert "Lộ trình theo chương" in html
            assert "Quiz cũ" in html
            room = client.get(f"/study-plan/tasks/{task}/learn")
            assert room.status_code == 200
            assert f"/quiz?task_id={task}" in room.get_data(as_text=True)

            # A link is made only by a verified internal path in future 7.2.
            conn = project.db()
            ensure_session_quiz_schema(conn)
            verified = get_session_quiz_context(project, conn, student, task)
            assert verified["ready"] is True
            candidate = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Quiz theo buổi thử liên kết','[]',?)
            """, (student, subject, created)).lastrowid
            try:
                link_generated_quiz(conn, student, other_quiz, verified, created)
                assert False, "Cross-user Quiz must be rejected"
            except LessonContextError as exc:
                assert exc.status == 404
            link_generated_quiz(conn, student, candidate, verified, created)
            try:
                link_generated_quiz(conn, student, candidate, verified, created)
                assert False, "Never relink or overwrite existing Quiz provenance"
            except LessonContextError as exc:
                assert exc.status == 409
            conn.commit()
            assert conn.execute("SELECT COUNT(*) FROM quiz_session_links").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE quiz_id=?",
                                (old_quiz,)).fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM quiz_session_links WHERE quiz_id=?",
                                (old_quiz,)).fetchone()[0] == 0
            conn.close()
            linked_page = client.get("/quiz").get_data(as_text=True)
            # 7.3: prepared session Quiz remains hidden until server unlock.
            assert "Quiz theo buổi thử liên kết" not in linked_page
            assert "Quiz cũ" in linked_page

            # Revoked approval disables prospective session Quiz, never removes
            # the historic quiz or recorded scores.
            conn = project.db()
            conn.execute("DELETE FROM shared_document_chapters WHERE document_id=?",
                         (doc_id,))
            conn.commit()
            conn.close()
            revoked = client.get(api)
            assert revoked.status_code == 200
            assert revoked.get_json()["ready"] is False
            assert revoked.get_json()["source_names"] == []
            conn = project.db()
            assert conn.execute("SELECT COUNT(*) FROM quizzes WHERE user_id=?",
                                (student,)).fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM quiz_attempts WHERE quiz_id=?",
                                (old_quiz,)).fetchone()[0] == 1
            conn.close()

            conn = project.db()
            modified = json.loads(json.dumps(roadmap))
            modified[0]["topics"] = ["Mục tiêu khác"]
            conn.execute("""
                UPDATE course_roadmaps SET sessions_json=?
                WHERE user_id=? AND subject_id=?
            """, (json.dumps(modified, ensure_ascii=False), student, subject))
            conn.commit()
            conn.close()
            assert client.get(api).status_code == 409
            assert client.get(page).status_code == 409
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_db, old_uploads


if __name__ == "__main__":
    verify()
    print("7.1 session Quiz context / verified sources / legacy safety OK")
