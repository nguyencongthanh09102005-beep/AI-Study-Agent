"""Phase 6.1 regression: opt-in roadmap -> Study Plan without data loss."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import build_course_roadmap, parse_chapter_details, unit_fingerprint
from course_schedule_sync import import_roadmap_lessons, scheduled_lessons
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema
from course_path_routes import ensure_roadmap_schema


def test_schedule_import():
    previous = project.DB_PATH
    with tempfile.TemporaryDirectory() as directory:
        project.DB_PATH = Path(directory) / "phase6.db"
        try:
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            student = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student A','schedule-a@test.local','hash','student','now')
            """).lastrowid
            stranger = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student B','schedule-b@test.local','hash','student','now')
            """).lastrowid
            subject = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Cấu trúc dữ liệu", "DATA6", project.now())).lastrowid

            syllabus = """Chương 1. Tổng quan dữ liệu
1.1. Cấu trúc dữ liệu
1.2. Big O
Chương 2. Danh sách liên kết
2.1. Node và Head
2.2. Thêm node
2.3. Xóa node"""
            doc = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                      extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (student, subject, "Đề cương", "syllabus6.txt", syllabus, project.now())
            ).lastrowid
            conn.execute(
                "UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                (doc, subject)
            )
            units = [
                {"title": "Chương 1. Tổng quan dữ liệu",
                 "evidence": "Chương 1. Tổng quan dữ liệu"},
                {"title": "Chương 2. Danh sách liên kết",
                 "evidence": "Chương 2. Danh sách liên kết"},
            ]
            fingerprint = syllabus_hash(syllabus)
            conn.execute("""
                INSERT INTO syllabus_reviews
                (user_id,subject_id,source_hash,source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, subject, fingerprint, "personal",
                  json.dumps(units, ensure_ascii=False), project.now()))
            sessions = build_course_roadmap(
                parse_chapter_details(syllabus, units), [],
                {"goal": "Học tốt", "daily_minutes": 45, "preferred_time": "19:00"}
            )
            assert len(sessions) >= 3
            conn.execute("""
                INSERT INTO course_roadmaps
                (user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)
                VALUES(?,?,?,?,?,?)
            """, (student, subject, fingerprint, unit_fingerprint(units),
                  json.dumps(sessions, ensure_ascii=False), project.now()))

            # Preexisting manual and AI tasks must be left untouched.
            for kind in ("manual", "ai"):
                conn.execute("""
                    INSERT INTO study_tasks
                    (user_id,subject_id,title,study_at,duration,note,done,source,created_at)
                    VALUES(?,?,?,'2026-11-05T19:00',45,'original',0,?,?)
                """, (student, subject, "Công việc cũ", kind, project.now()))
            conn.commit()
            conn.close()

            client = project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = student
                sess["user_name"] = "Student A"

            url = f"/subjects/{subject}/learning-path"
            html = client.get(url).get_data(as_text=True)
            assert 'value="schedule"' in html
            assert "Kết nối với Kế hoạch học" in html
            with client.session_transaction() as sess:
                token = sess["syllabus_csrf_token"]
            assert client.post(url, data={"action": "schedule"}).status_code == 403
            assert client.post(url, data={
                "action": "schedule", "csrf_token": token + "bad"
            }).status_code == 403
            conn = project.db()
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE source='roadmap'"
            ).fetchone()[0] == 0
            conn.close()

            created = client.post(url, data={
                "action": "schedule", "csrf_token": token,
            }, follow_redirects=True)
            assert created.status_code == 200
            assert "Đã đưa" in created.get_data(as_text=True)
            conn = project.db()
            rows = conn.execute("""
                SELECT * FROM study_tasks WHERE user_id=? AND subject_id=?
                  AND source='roadmap' ORDER BY roadmap_session_id
            """, (student, subject)).fetchall()
            assert len(rows) == len(sessions)
            assert [r["roadmap_session_id"] for r in rows] == [
                s["session_id"] for s in sessions
            ]
            assert all(r["done"] == 0 for r in rows)
            assert len(scheduled_lessons(conn, student, subject)) == len(sessions)
            first_id, first_title = rows[0]["id"], rows[0]["title"]
            conn.close()

            # Editing or completing on the existing Study Plan must survive
            # repeated imports. The created task remains exactly the same ID.
            assert client.post(f"/study-plan/tasks/{first_id}/toggle").status_code == 302
            assert client.post(f"/study-plan/tasks/{first_id}/update", data={
                "subject_id": subject, "title": "Tự đổi tên buổi học",
                "study_at": "2026-11-09T20:30", "duration": "60",
                "note": "Tôi muốn học lúc tối",
            }).status_code == 302
            second = client.post(url, data={
                "action": "schedule", "csrf_token": token,
            }, follow_redirects=True)
            assert "0 buổi mới" in second.get_data(as_text=True)
            conn = project.db()
            rows2 = conn.execute(
                "SELECT * FROM study_tasks WHERE source='roadmap' ORDER BY roadmap_session_id"
            ).fetchall()
            assert len(rows2) == len(sessions)
            assert rows2[0]["id"] == first_id
            assert rows2[0]["done"] == 1
            assert rows2[0]["title"] == "Tự đổi tên buổi học"
            assert rows2[0]["study_at"] == "2026-11-09T20:30"
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE source IN ('ai','manual')"
            ).fetchone()[0] == 2

            # A regenerated, changed session must be flagged for review,
            # not silently overwrite the manually rescheduled task.
            changed = json.loads(json.dumps(sessions))
            changed[0]["topics"] = ["Khác nội dung cũ"]
            conn.execute(
                "UPDATE course_roadmaps SET sessions_json=? WHERE user_id=? AND subject_id=?",
                (json.dumps(changed, ensure_ascii=False), student, subject)
            )
            conn.commit()
            conn.close()
            response = client.post(url, data={
                "action": "schedule", "csrf_token": token,
            }, follow_redirects=True)
            assert "đã thay đổi nội dung" in response.get_data(as_text=True)
            assert "cần rà soát" in response.get_data(as_text=True)
            conn = project.db()
            assert conn.execute(
                "SELECT title FROM study_tasks WHERE id=?", (first_id,)
            ).fetchone()["title"] == "Tự đổi tên buổi học"

            # Bad input must not partially import a course's sessions.
            bad = json.loads(json.dumps(sessions))
            bad[-1].pop("date")
            try:
                import_roadmap_lessons(conn, student, subject, bad, project.now())
                raise AssertionError("Missing date was accepted")
            except ValueError:
                pass
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE source='roadmap'"
            ).fetchone()[0] == len(sessions)
            conn.close()

            outsider = project.app.test_client()
            with outsider.session_transaction() as sess:
                sess["user_id"] = stranger
            assert outsider.get(url).status_code == 404
            assert outsider.post(url, data={
                "action": "schedule", "csrf_token": token
            }).status_code == 404

            # If the syllabus changes, no scheduling against a stale roadmap.
            conn = project.db()
            conn.execute(
                "UPDATE documents SET extracted_text=extracted_text || ? WHERE id=?",
                ("\nChương 3. Đồ thị", doc)
            )
            conn.commit()
            conn.close()
            invalid = client.post(url, data={
                "action": "schedule", "csrf_token": token
            }, follow_redirects=True)
            assert "chưa hợp lệ" in invalid.get_data(as_text=True)
            conn = project.db()
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE source='roadmap'"
            ).fetchone()[0] == len(sessions)
            conn.close()
            print("Phase 6.1: opt-in, idempotency, CSRF, isolation, stale, preservation OK")
        finally:
            project.DB_PATH = previous


if __name__ == "__main__":
    test_schedule_import()
