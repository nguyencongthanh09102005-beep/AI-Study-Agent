"""Final audit regressions: Admin/student role boundary and safe AI plan regeneration."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def test():
    conn = project.db()
    student_id = conn.execute(
        "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
        ("Student", "audit-student@study.local",
         project.generate_password_hash("student-password-2026"),
         "student", project.now())
    ).lastrowid
    admin_id = conn.execute(
        "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
        ("Admin", "audit-admin@study.local",
         project.generate_password_hash("admin-password-2026"),
         "admin", project.now())
    ).lastrowid
    sid = conn.execute(
        "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
        (student_id, "Điện toán đám mây", "CLOUD101", project.now())
    ).lastrowid
    deadline = (datetime.now() + timedelta(days=14)).replace(second=0, microsecond=0)
    manual_id = conn.execute(
        "INSERT INTO reminders(user_id,subject_id,title,due_at,source,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (student_id, sid, "Deadline tự thêm – PHẢI GIỮ", deadline.isoformat(),
         "manual", project.now())
    ).lastrowid
    old_ai_id = conn.execute(
        "INSERT INTO reminders(user_id,subject_id,title,due_at,source,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (student_id, sid, "AI Plan cũ – thay thế", deadline.isoformat(),
         "ai", project.now())
    ).lastrowid
    done_ai_id = conn.execute(
        "INSERT INTO reminders(user_id,subject_id,title,due_at,done,source,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (student_id, sid, "AI Plan đã xong – giữ lịch sử",
         deadline.isoformat(), 1, "ai", project.now())
    ).lastrowid
    conn.commit()
    conn.close()

    admin = project.app.test_client()
    assert admin.post("/api/mobile/login", json={
        "email": "audit-admin@study.local", "password": "admin-password-2026"
    }).status_code == 401
    assert admin.post("/admin/login", data={
        "email": "audit-admin@study.local", "password": "admin-password-2026"
    }).status_code in (302, 303)
    assert admin.get("/admin").status_code == 200
    for route in ("/dashboard", "/subjects", "/documents", "/quiz",
                  "/study-plan", "/chat", "/api/mobile/session",
                  "/api/mobile/dashboard", "/api/mobile/documents",
                  "/api/mobile/subjects"):
        response = admin.get(route)
        assert response.status_code == 403, (route, response.status_code)
    for route in ("/api/mobile/subjects", "/api/mobile/tasks"):
        assert admin.post(route, json={
            "name": "Should never be added",
            "title": "Should never be added",
            "study_at": deadline.isoformat()
        }).status_code == 403
    assert admin.post("/api/quiz/submit", json={"quiz_id": 1, "answers": [0]}).status_code == 403
    # Old sessions issued before a role change must also be restricted.
    with admin.session_transaction() as sess:
        assert sess["user_id"] == admin_id

    student = project.app.test_client()
    assert student.post("/api/mobile/login", json={
        "email": "audit-student@study.local", "password": "student-password-2026"
    }).status_code == 200
    assert student.get("/api/mobile/session").status_code == 200
    assert student.get("/dashboard").status_code == 200
    assert student.get("/admin").status_code == 403

    backbone = {
        "personal_context": "Bài học", "syllabus_text": "Đề cương",
        "syllabus_topics": ["Chương 1"], "shared_context": "",
        "personal_document_names": [], "shared_source_names": [],
        "syllabus_source": "shared", "syllabus_source_name": "Đề cương"
    }
    tasks = [{
        "date": (datetime.now() + timedelta(days=1)).date().isoformat(),
        "time": "19:00", "title": "Ôn chương 1", "duration": 45, "note": "QA"
    }]
    with (
        patch.object(project, "get_course_learning_backbone", return_value=backbone),
        patch.object(project, "get_personal_learning_context", return_value=""),
        patch.object(project, "build_study_plan", return_value=tasks)
    ):
        response = student.post("/study-plan/generate", data={
            "subject_id": str(sid), "goal": "Ôn tập bản Web",
            "deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            "preferred_time": "19:00", "daily_minutes": "45"
        })
        assert response.status_code in (302, 303), response.get_data(as_text=True)
        assert_deadline_integrity(manual_id, old_ai_id, done_ai_id, student_id, sid, "Ôn tập bản Web")

        response = student.post("/api/mobile/study-plan", json={
            "subject_id": sid, "goal": "Ôn tập bản Mobile",
            "deadline": deadline.strftime("%Y-%m-%dT%H:%M"),
            "preferred_time": "19:00", "daily_minutes": 45
        })
        assert response.status_code == 200, response.get_data(as_text=True)
        assert_deadline_integrity(manual_id, old_ai_id, done_ai_id, student_id, sid, "Ôn tập bản Mobile")

    conn = project.db()
    assert conn.execute(
        "SELECT COUNT(*) FROM subjects WHERE user_id=?", (admin_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM reminders WHERE id=? AND source='manual'", (manual_id,)
    ).fetchone()[0] == 1
    conn.close()

    # Simulate a user's older SQLite DB without the newly introduced source
    # column. Restart migration must keep every deadline, not crash or delete.
    conn = project.db()
    count_before = conn.execute(
        "SELECT COUNT(*) FROM reminders WHERE user_id=?", (student_id,)
    ).fetchone()[0]
    conn.execute("ALTER TABLE reminders DROP COLUMN source")
    conn.commit()
    conn.close()
    project.init_db()
    conn = project.db()
    assert "source" in {
        row["name"] for row in conn.execute("PRAGMA table_info(reminders)")
    }
    assert conn.execute(
        "SELECT COUNT(*) FROM reminders WHERE user_id=?", (student_id,)
    ).fetchone()[0] == count_before
    assert conn.execute(
        "SELECT source FROM reminders WHERE id=?", (manual_id,)
    ).fetchone()["source"] == "manual"
    conn.close()


def assert_deadline_integrity(manual_id, old_ai_id, done_ai_id, user_id, subject_id, title):
    conn = project.db()
    reminders = conn.execute(
        "SELECT id,title,done,source FROM reminders WHERE user_id=? AND subject_id=?",
        (user_id, subject_id)
    ).fetchall()
    assert any(r["id"] == manual_id and r["source"] == "manual" for r in reminders)
    assert all(r["id"] != old_ai_id for r in reminders)
    assert any(r["id"] == done_ai_id and r["done"] == 1 for r in reminders)
    active_ai = [r for r in reminders if r["source"] == "ai" and not r["done"]]
    assert len(active_ai) == 1 and active_ai[0]["title"] == title
    conn.close()


if __name__ == "__main__":
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "study_agent.db"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            test()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Audit QA: role restrictions + preserving manual deadlines on Web/Mobile passed")
