"""Phase 6.3.1: real Flask read-only course lesson room, auth and material ACL."""
import json
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as project
from course_path_learning import (
    build_course_roadmap, parse_chapter_details, unit_fingerprint,
)
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, import_roadmap_lessons
from chapter_material_routes import ensure_chapter_material_schema
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema


def login(client, user_id):
    with client.session_transaction() as user_session:
        user_session["user_id"] = user_id
        user_session["user_name"] = "Study session test"


def verify():
    with TemporaryDirectory() as tmp:
        old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(tmp) / "session.db"
            project.UPLOAD_DIR = Path(tmp) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            ensure_chapter_material_schema(conn)
            student = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Student','s1@lesson.test','hash','student',?)",
                (project.now(),),
            ).lastrowid
            outsider = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Other','s2@lesson.test','hash','student',?)",
                (project.now(),),
            ).lastrowid
            admin = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Admin','admin@lesson.test','hash','admin',?)",
                (project.now(),),
            ).lastrowid
            subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) "
                "VALUES(?,?,?,?)", (student, "Cấu trúc dữ liệu", "DATA631", project.now()),
            ).lastrowid
            other_course = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) "
                "VALUES(?,?,?,?)", (student, "Hệ điều hành", "OS631", project.now()),
            ).lastrowid
            outsider_course = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) "
                "VALUES(?,?,?,?)", (outsider, "Ngoài quyền", "OTHER631", project.now()),
            ).lastrowid
            syllabus = ("Chương 1. Danh sách liên kết\n"
                        "1.1. Cấu trúc node\n"
                        "1.2. Con trỏ head\n"
                        "Mục tiêu: Nắm cách liên kết node\n"
                        "Bài tập: Viết chương trình duyệt node")
            units = [{"title": "Chương 1. Danh sách liên kết",
                      "evidence": "Chương 1. Danh sách liên kết"}]
            source = syllabus_hash(syllabus)
            syllabus_doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,
                stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, "Đề cương",
                  "syllabus631.txt", syllabus, project.now())).lastrowid
            conn.execute(
                "UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                (syllabus_doc, subject))
            doc_id = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,
                stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, "Slide Node cá nhân.pdf",
                  "private631.pdf", "Cấu trúc node, con trỏ head, liên kết node",
                  project.now())).lastrowid
            wrong_subject_doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,
                stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, other_course, "Mật của môn khác",
                  "other_course631.pdf", "Cấu trúc node", project.now())).lastrowid
            wrong_user_doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,
                stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (outsider, outsider_course, "Mật của sinh viên khác",
                  "other_user631.pdf", "Cấu trúc node", project.now())).lastrowid
            conn.execute("""
                INSERT INTO syllabus_reviews
                (user_id,subject_id,source_hash,source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, subject, source, "personal",
                  json.dumps(units, ensure_ascii=False), project.now()))
            sessions = build_course_roadmap(
                parse_chapter_details(syllabus, units),
                [{"id": doc_id, "name": "Slide Node cá nhân.pdf",
                  "text": "Cấu trúc node con trỏ head, liên kết node",
                  "kind": "personal"}],
                {"goal": "Hiểu node", "preferred_time": "19:00", "daily_minutes": 45},
                start_date=date(2026, 11, 2)
            )
            assert sessions and sessions[0]["objectives"]
            # Deliberately inject forbidden material hints into the saved JSON.
            # Viewing the room must check current DB ownership, not trust JSON.
            sessions[0]["materials"] = [
                {"id": doc_id, "kind": "personal", "name": "Gợi ý hợp lệ"},
                {"id": wrong_subject_doc, "kind": "personal", "name": "Rò rỉ môn khác"},
                {"id": wrong_user_doc, "kind": "personal", "name": "Rò rỉ sinh viên khác"},
                {"id": 999999, "kind": "shared", "name": "Chưa duyệt"},
            ]
            conn.execute("""
                INSERT INTO course_roadmaps
                (user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)
                VALUES(?,?,?,?,?,?)
            """, (student, subject, source, unit_fingerprint(units),
                  json.dumps(sessions, ensure_ascii=False), project.now()))
            summary = import_roadmap_lessons(
                conn, student, subject, sessions, project.now())
            assert summary["created"] == len(sessions)
            task_id = conn.execute("""
                SELECT id FROM study_tasks WHERE user_id=? AND subject_id=?
                AND source='roadmap' ORDER BY roadmap_session_id LIMIT 1
            """, (student, subject)).fetchone()["id"]
            manual = conn.execute("""
                INSERT INTO study_tasks(user_id,subject_id,title,study_at,
                duration,note,done,source,created_at)
                VALUES(?,?,?,'2026-11-02T20:00',45,'',0,'manual',?)
            """, (student, subject, "Việc thủ công", project.now())).lastrowid
            conn.commit()
            conn.close()
            url = f"/study-plan/tasks/{task_id}/learn"
            client = project.app.test_client()
            anonymous = client.get(url)
            assert anonymous.status_code in (302, 303)
            login(client, student)
            calendar = client.get("/study-plan").get_data(as_text=True)
            assert f"/study-plan/tasks/{task_id}/learn" in calendar
            assert "▶ Bắt đầu học" in calendar
            assert f"/study-plan/tasks/{manual}/learn" not in calendar
            # No hidden writes: opening the lesson cannot mark completion.
            db = project.db()
            before = dict(db.execute("SELECT * FROM study_tasks WHERE id=?", (task_id,)).fetchone())
            db.close()
            page = client.get(url)
            assert page.status_code == 200
            body = page.get_data(as_text=True)
            assert "KHÔNG GIAN HỌC TẬP" in body
            assert "Cấu trúc dữ liệu" in body
            assert "Cấu trúc node" in body
            assert "Mục tiêu buổi học" in body
            assert "Hoạt động học tập" in body
            assert "19:00" in body
            assert "Slide Node cá nhân.pdf" in body
            assert f"/uploads/private631.pdf" in body
            assert 'data-chat-enabled="0"' in body
            assert "Mở Chat AI thông thường của môn" in body
            assert client.get(f"/api/study-plan/tasks/{task_id}/chat-history").status_code == 409
            assert "Mật của môn khác" not in body
            assert "Mật của sinh viên khác" not in body
            assert "Chưa duyệt" not in body
            db = project.db()
            after = dict(db.execute("SELECT * FROM study_tasks WHERE id=?", (task_id,)).fetchone())
            assert before == after
            assert db.execute("SELECT COUNT(*) FROM quizzes WHERE user_id=?", (student,)).fetchone()[0] == 0
            db.close()
            assert client.get(f"/study-plan/tasks/{manual}/learn").status_code == 404
            assert client.post(url).status_code == 405

            # A student cannot access another student's room, even knowing the ID.
            login(client, outsider)
            other = client.get(url)
            assert other.status_code == 404
            assert "Slide Node" not in other.get_data(as_text=True)
            login(client, admin)
            assert client.get(url).status_code == 403
            login(client, student)

            # Admin-approved shared materials show live; rogue saved shared IDs
            # do not. The official syllabus matches the confirmed review.
            db = project.db()
            shared = project.ensure_shared_subject_for_user_subject(db, student, subject)
            shared_id = shared["id"]
            # The test inserted official files directly; model the real
            # Admin-managed course state required by the chapter tutor.
            db.execute("UPDATE shared_subjects SET admin_managed=1 WHERE id=?",
                       (shared_id,))
            db.execute("""
                INSERT INTO shared_documents
                (shared_subject_id,original_name,stored_name,extracted_text,
                is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,1,?,?)
            """, (shared_id, "Đề cương chuẩn", "official631.txt", syllabus, admin, project.now()))
            approved_id = db.execute("""
                INSERT INTO shared_documents
                (shared_subject_id,original_name,stored_name,extracted_text,
                is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,0,?,?)
            """, (shared_id, "Slide chương 1 được duyệt", "shared631.pdf",
                  "Cấu trúc node liên kết", admin, project.now())).lastrowid
            unapproved_id = db.execute("""
                INSERT INTO shared_documents
                (shared_subject_id,original_name,stored_name,extracted_text,
                is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?, ?,0,?,?)
            """, (shared_id, "Tài liệu chưa duyệt", "not_approved631.pdf",
                  "Cấu trúc node liên kết", admin, project.now())).lastrowid
            db.execute("""
                INSERT INTO shared_document_chapters
                (document_id,shared_subject_id,chapter_key,syllabus_hash,confirmed_by,confirmed_at)
                VALUES(?,?,?, ?,?,?)
            """, (approved_id, shared_id, "1", source, admin, project.now()))
            db.commit()
            db.close()
            shared_room = client.get(url).get_data(as_text=True)
            assert "Slide chương 1 được duyệt" in shared_room
            assert f"/shared-documents/{approved_id}/file" in shared_room
            assert "Tài liệu chưa duyệt" not in shared_room
            assert f"/shared-documents/{unapproved_id}/file" not in shared_room
            assert 'data-chat-enabled="1"' in shared_room
            assert "study_session_chat.js" in shared_room

            # The room shares the existing subject conversation, but keeps
            # the prompt and history scoped to the verified roadmap session.
            chat_url = f"/api/study-plan/tasks/{task_id}/chat-history"
            initial = client.get(chat_url)
            assert initial.status_code == 200, initial.get_data(as_text=True)[:500]
            initial_data = initial.get_json()
            assert initial_data["messages"] == []
            assert initial_data["source_names"] == ["Slide chương 1 được duyệt"]
            conversation = initial_data["conversation_id"]
            asked = []
            original_generate = project.gemini_generate
            def mock_tutor(prompt):
                asked.append(prompt)
                return (json.dumps({
                    "explanation": "Một node là một thành phần trong danh sách liên kết.",
                    "citations": [{"source_key": "T1",
                                   "quote": "Cấu trúc node liên kết"}],
                    "practice": "Bạn hãy nêu nhiệm vụ của con trỏ head."
                }, ensure_ascii=False), None)
            try:
                project.gemini_generate = mock_tutor
                payload = {
                    "conversation_id": conversation,
                    "question": "Giải thích node trong buổi này.",
                    "lesson": {"chapter_number": 1, "task_id": task_id},
                }
                response = client.post("/api/chat", json=payload)
                assert response.status_code == 200, response.get_data(as_text=True)[:500]
                data = response.get_json()
                assert data["source_mode"] == "chapter"
                assert data["lesson"]["session_task_id"] == task_id
                assert "Cấu trúc node liên kết" in data["answer"]
                assert "NGỮ CẢNH BUỔI HỌC" in asked[-1]
                assert "Mật của môn khác" not in asked[-1]
                assert "Tài liệu chưa duyệt" not in asked[-1]
                scoped_history = client.get(chat_url).get_json()["messages"]
                assert [item["role"] for item in scoped_history] == ["user", "assistant"]
                # Existing chapter mode remains distinct from the room's history.
                full_chapter = client.post("/api/chat", json={
                    "conversation_id": conversation, "question": "Hỏi cả chương.",
                    "lesson": {"chapter_number": 1}
                })
                assert full_chapter.status_code == 200
                assert "Hỏi cả chương." not in asked[-1].split("ĐỐI THOẠI GẦN ĐÂY")[1].split("YÊU CẦU CỦA SINH VIÊN")[0]
                assert len(client.get(chat_url).get_json()["messages"]) == 2
                # The task number cannot be used to forge a different chapter.
                bad = client.post("/api/chat", json={
                    **payload, "lesson": {"chapter_number": 2, "task_id": task_id}
                })
                assert bad.status_code in (400, 404)
                assert client.post("/api/chat", json={
                    **payload, "lesson": {"chapter_number": 1,
                                          "task_id": manual}
                }).status_code == 404
                assert client.post("/api/chat", json={
                    **payload, "lesson": {"chapter_number": 1,
                                          "task_id": task_id, "topic_index": 0}
                }).status_code == 400
                login(client, outsider)
                assert client.get(chat_url).status_code == 404
                assert client.post("/api/chat", json=payload).status_code == 404
                login(client, student)
            finally:
                project.gemini_generate = original_generate

            # Revoke mapping; no stale approved file must survive.
            db = project.db()
            db.execute("DELETE FROM shared_document_chapters WHERE document_id=?",
                       (approved_id,))
            db.commit()
            db.close()
            assert "Slide chương 1 được duyệt" not in client.get(url).get_data(as_text=True)
            assert 'data-chat-enabled="0"' in client.get(url).get_data(as_text=True)
            assert client.get(chat_url).status_code == 409
            # Approval revoked -> no AI answer or history leak.
            assert client.post("/api/chat", json=payload).status_code == 409

            # Regenerating a lesson changes its signature; never mix old
            # schedule with new objective/topic under the same ID.
            db = project.db()
            changed = json.loads(json.dumps(sessions))
            changed[0]["topics"] = ["Nội dung mới sau khi tạo lại"]
            db.execute("""UPDATE course_roadmaps SET sessions_json=?
                       WHERE user_id=? AND subject_id=?""",
                       (json.dumps(changed, ensure_ascii=False), student, subject))
            db.commit()
            db.close()
            stale_room = client.get(url)
            assert stale_room.status_code == 409
            assert "cần được rà soát" in stale_room.get_data(as_text=True)
            assert "Nội dung mới sau khi tạo lại" not in stale_room.get_data(as_text=True)

            # Restoring roadmaps then replacing syllabus invalidates the room.
            db = project.db()
            db.execute("UPDATE course_roadmaps SET sessions_json=? "
                       "WHERE user_id=? AND subject_id=?",
                       (json.dumps(sessions, ensure_ascii=False), student, subject))
            db.execute("UPDATE shared_documents SET extracted_text=? WHERE stored_name=?",
                       (syllabus+" thêm chương mới", "official631.txt"))
            db.commit()
            db.close()
            assert client.get(url).status_code == 409
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload


if __name__ == "__main__":
    verify()
    print("Phase 6.3.1 study-room, access control, and materials OK")
