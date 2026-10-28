"""Phase 6.4: real Flask session timing, authorization, state transitions,
CSRF, replay protection, actual seconds and planner progress integrity."""
import json
import sys
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as project
from course_path_learning import build_course_roadmap, parse_chapter_details, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, import_roadmap_lessons
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema
from study_session_tracking import (
    StudyTrackingError, apply_action, ensure_tracking_schema, read_state,
)


def login(client, uid):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = uid
        sess["user_name"] = "Tester"


def test():
    with TemporaryDirectory() as temp:
        old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(temp) / "study64.sqlite"
            project.UPLOAD_DIR = Path(temp) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            ensure_tracking_schema(conn)
            t0 = project.now()
            student = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('A','study64a@example.test','x','student',?)
            """, (t0,)).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('B','study64b@example.test','x','student',?)
            """, (t0,)).lastrowid
            admin = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('C','study64c@example.test','x','admin',?)
            """, (t0,)).lastrowid
            subject = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Dữ liệu và giải thuật", "TEST64", t0)).lastrowid
            syllabus = (
                "Chương 1. Danh sách liên kết\n"
                "1.1. Node\n1.2. Con trỏ next\n"
                "Mục tiêu: Nắm được cách duyệt node\n"
                "Bài tập: Viết hàm tìm node"
            )
            units = [{"title": "Chương 1. Danh sách liên kết",
                      "evidence": "Chương 1. Danh sách liên kết"}]
            doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                extracted_text,created_at) VALUES(?,?,?,?,?,?)
            """, (student, subject, "Đề cương", "syllabus64.txt", syllabus, t0)).lastrowid
            conn.execute(
                "UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                (doc, subject)
            )
            fingerprint = syllabus_hash(syllabus)
            conn.execute("""
                INSERT INTO syllabus_reviews
                (user_id,subject_id,source_hash,source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, subject, fingerprint, "personal",
                  json.dumps(units, ensure_ascii=False), t0))
            lessons = build_course_roadmap(
                parse_chapter_details(syllabus, units), [],
                {"goal": "Hiểu node", "preferred_time": "19:00",
                 "daily_minutes": 45}, start_date=date(2026, 11, 2)
            )
            assert lessons
            conn.execute("""
                INSERT INTO course_roadmaps(
                  user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)
                VALUES(?,?,?,?,?,?)
            """, (student, subject, fingerprint, unit_fingerprint(units),
                  json.dumps(lessons, ensure_ascii=False), t0))
            imported = import_roadmap_lessons(conn, student, subject, lessons, t0)
            assert imported["created"] >= 1
            task_id = conn.execute("""
                SELECT id FROM study_tasks WHERE user_id=? AND subject_id=?
                ORDER BY roadmap_session_id LIMIT 1
            """, (student, subject)).fetchone()["id"]
            conn.commit()
            conn.close()

            client = project.app.test_client()
            room_url = "/study-plan/tasks/{}/learn".format(task_id)
            api_url = "/api/study-plan/tasks/{}/study-session".format(task_id)
            assert client.get(api_url).status_code == 401
            assert client.post(api_url, json={"action": "start"}).status_code == 401
            login(client, other)
            assert client.get(api_url).status_code == 404
            login(client, admin)
            assert client.get(api_url).status_code == 403

            login(client, student)
            assert client.post(api_url, json={"action": "start"}).status_code == 403
            room = client.get(room_url)
            assert room.status_code == 200
            content = room.get_data(as_text=True)
            assert 'id="studySessionTimer"' in content
            assert "study_session_timer.js" in content
            with client.session_transaction() as sess:
                csrf = sess["study_session_csrf"]
            headers = {"X-Study-CSRF": csrf}
            assert client.post(api_url, json={"action": "start"},
                               headers={"X-Study-CSRF": "wrong"}).status_code == 403
            assert client.post(api_url, data="action=start",
                               headers=headers).status_code == 415
            first = client.get(api_url).get_json()
            assert first["status"] == "idle"
            assert first["elapsed_seconds"] == 0
            conn = project.db()
            assert conn.execute("""
                SELECT COUNT(*) FROM study_session_tracking
            """).fetchone()[0] == 0
            assert conn.execute("SELECT done FROM study_tasks WHERE id=?",
                                (task_id,)).fetchone()["done"] == 0
            conn.close()
            def post(action):
                return client.post(api_url, json={"action": action}, headers=headers)
            start = post("start")
            assert start.status_code == 200, start.get_data(as_text=True)
            assert start.get_json()["status"] == "running"
            assert post("start").status_code == 409
            assert post("heartbeat").status_code == 200
            paused = post("pause")
            assert paused.status_code == 200
            assert paused.get_json()["status"] == "paused"
            assert post("pause").status_code == 409
            assert post("heartbeat").status_code == 409
            assert post("resume").get_json()["status"] == "running"
            result = post("finish")
            assert result.status_code == 200, result.get_data(as_text=True)
            assert result.get_json()["status"] == "completed"
            assert result.get_json()["done"] is True
            assert post("finish").status_code == 409
            assert client.get(api_url).get_json()["status"] == "completed"
            conn = project.db()
            assert conn.execute("""
                SELECT done FROM study_tasks WHERE id=?
            """, (task_id,)).fetchone()["done"] == 1
            assert conn.execute("""
                SELECT progress FROM subjects WHERE id=?
            """, (subject,)).fetchone()["progress"] > 0
            conn.close()

            # Server time is authoritative and can survive refresh/pauses.
            conn = project.db()
            conn.execute("DELETE FROM study_session_tracking WHERE task_id=?", (task_id,))
            conn.execute("""
                UPDATE study_tasks SET done=0,completed_at='' WHERE id=?
            """, (task_id,))
            conn.commit()
            task = conn.execute("SELECT * FROM study_tasks WHERE id=?",
                                (task_id,)).fetchone()
            t = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
            assert apply_action(project, conn, task, student, "start", t)["status"] == "running"
            assert apply_action(project, conn, task, student, "heartbeat",
                                t+timedelta(seconds=20))["elapsed_seconds"] == 20
            assert apply_action(project, conn, task, student, "pause",
                                t+timedelta(seconds=35))["elapsed_seconds"] == 35
            assert read_state(conn, task, student, t+timedelta(seconds=200))["elapsed_seconds"] == 35
            assert apply_action(project, conn, task, student, "resume",
                                t+timedelta(seconds=200))["status"] == "running"
            assert apply_action(project, conn, task, student, "finish",
                                t+timedelta(seconds=218))["elapsed_seconds"] == 53
            assert conn.execute("SELECT done FROM study_tasks WHERE id=?",
                                (task_id,)).fetchone()["done"] == 1
            conn.execute("DELETE FROM study_session_tracking WHERE task_id=?", (task_id,))
            conn.execute("UPDATE study_tasks SET done=0,completed_at='' WHERE id=?",
                         (task_id,))
            conn.commit()
            task = conn.execute("SELECT * FROM study_tasks WHERE id=?",
                                (task_id,)).fetchone()
            apply_action(project, conn, task, student, "start", t)
            stale = read_state(conn, task, student, t+timedelta(minutes=10))
            assert stale["status"] == "paused"
            assert stale["elapsed_seconds"] == 45  # No 10-minute fake session.
            try:
                apply_action(project, conn, task, student, "heartbeat",
                             t+timedelta(minutes=10))
                assert False, "Expired heartbeat must be rejected."
            except StudyTrackingError as e:
                assert e.status == 409
            resumed = apply_action(project, conn, task, student, "resume",
                                   t+timedelta(minutes=10))
            assert resumed["elapsed_seconds"] == 45
            assert resumed["status"] == "running"
            conn.commit()
            conn.close()

            # Stale roadmap is blocked even if the client has a valid CSRF token.
            conn = project.db()
            updated = json.loads(json.dumps(lessons))
            updated[0]["topics"] = ["Nội dung khác"]
            conn.execute("UPDATE course_roadmaps SET sessions_json=? "
                         "WHERE user_id=? AND subject_id=?",
                         (json.dumps(updated, ensure_ascii=False), student, subject))
            conn.commit()
            conn.close()
            assert client.get(api_url).status_code == 409
            assert post("finish").status_code == 409
            assert client.get(room_url).status_code == 409
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload


if __name__ == "__main__":
    test()
    print("6.4 verified study timer / CSRF / progress / stale-roadmap checks OK")
