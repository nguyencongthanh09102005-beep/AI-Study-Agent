"""Mobile study-room parity: owned course, confirmed syllabus, timer CSRF.

No Gemini calls; uses a temporary SQLite database. Shared timer integrity is
the same as the verified Web study-session endpoint.
"""
import json
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import (
    build_course_roadmap, parse_chapter_details, unit_fingerprint
)
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, import_roadmap_lessons
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema


def login(client, uid):
    with client.session_transaction() as sess:
        sess.clear()
        if uid:
            sess["user_id"] = uid
            sess["user_name"] = "Sinh viên kiểm thử"


def check():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    with TemporaryDirectory() as root:
        try:
            project.DB_PATH = Path(root) / "mobile-room.sqlite"
            project.UPLOAD_DIR = Path(root) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            t0 = project.now()
            users = {}
            for role, code in [("student", "a"), ("student", "b"), ("admin", "c")]:
                users[code] = conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (code, code+"@mobile-room.example", "hash", role,t0)
                ).lastrowid
            uid = users["a"]
            subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,credits,created_at) "
                "VALUES(?,?,?,?,?)", (uid,"Cấu trúc dữ liệu","MOBILE_RM",3,t0)
            ).lastrowid
            syllabus = (
                "Chương 1. Cấu trúc dữ liệu\n"
                "1.1. Khái niệm danh sách\n"
                "1.2. Thao tác thêm và xóa\n"
                "Mục tiêu: Nhận biết được cấu trúc dữ liệu"
            )
            units = [{
                "title":"Chương 1. Cấu trúc dữ liệu",
                "evidence":"Chương 1. Cấu trúc dữ liệu",
            }]
            doc = conn.execute(
                "INSERT INTO documents(user_id,subject_id,original_name,stored_name,"
                "extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                (uid,subject,"Syllabus riêng","mobile-rm.txt",syllabus,t0)
            ).lastrowid
            conn.execute(
                "UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                (doc,subject)
            )
            hashed = syllabus_hash(syllabus)
            conn.execute(
                "INSERT INTO syllabus_reviews "
                "(user_id,subject_id,source_hash,source_kind,units_json,status,updated_at) "
                "VALUES(?,?,?,?,?,'confirmed',?)",
                (uid,subject,hashed,"personal",json.dumps(units),t0)
            )
            sessions = build_course_roadmap(
                parse_chapter_details(syllabus,units),[],
                {"goal":"Học cấu trúc dữ liệu","preferred_time":"19:00",
                 "daily_minutes":45,"credits":3},
                start_date=date(2026,11,2)
            )
            conn.execute(
                "INSERT INTO course_roadmaps "
                "(user_id,subject_id,source_hash,units_hash,sessions_json,updated_at) "
                "VALUES(?,?,?,?,?,?)",
                (uid,subject,hashed,unit_fingerprint(units),
                 json.dumps(sessions,ensure_ascii=False),t0)
            )
            import_roadmap_lessons(conn,uid,subject,sessions,t0)
            task = conn.execute(
                "SELECT id FROM study_tasks WHERE user_id=? AND subject_id=? "
                "AND source='roadmap' ORDER BY roadmap_session_id LIMIT 1",
                (uid,subject)
            ).fetchone()["id"]
            conn.commit()
            conn.close()
            client = project.app.test_client()
            path = f"/api/mobile/subjects/{subject}/roadmap"
            room = f"/api/mobile/study-room/{task}"
            timer = room + "/timer"

            assert client.get(path).status_code == 401
            assert client.get(room).status_code == 401
            login(client,users["b"])
            assert client.get(path).status_code == 404
            assert client.get(room).status_code == 404
            login(client,users["c"])
            assert client.get(path).status_code == 403
            assert client.get(room).status_code == 403

            login(client,uid)
            result = client.get(path)
            assert result.status_code == 200, result.get_data(as_text=True)
            data = result.get_json()
            assert data["ready"] is True
            assert len(data["sessions"]) == 15
            assert data["chapters"][0]["title"] == units[0]["title"]
            assert data["sessions"][0]["scheduled_task_id"] == task
            assert data["sessions"][0]["clo_refs"] == []
            assert all("materials" not in s for s in data["sessions"])

            opened = client.get(room)
            assert opened.status_code == 200, opened.get_data(as_text=True)
            detail = opened.get_json()
            assert detail["timer"]["status"] == "idle"
            assert detail["lesson"]["unit_id"] == 1
            assert detail["task"]["id"] == task
            assert detail["sources"] == []  # Personal files are not shared evidence.
            csrf = detail["timer_csrf"]
            assert client.post(timer,json={"action":"start"}).status_code == 403
            assert client.post(timer,json={"action":"start"},
                               headers={"X-Study-CSRF":"bad"}).status_code == 403
            headers = {"X-Study-CSRF":csrf}
            assert client.post(timer,json={"action":"unknown"},
                               headers=headers).status_code == 400
            start = client.post(timer,json={"action":"start"},headers=headers)
            assert start.status_code == 200, start.get_data(as_text=True)
            assert start.get_json()["status"] == "running"
            assert client.post(timer,json={"action":"pause"},
                               headers=headers).get_json()["status"] == "paused"
            assert client.post(timer,json={"action":"resume"},
                               headers=headers).get_json()["status"] == "running"
            finish = client.post(timer,json={"action":"finish"},headers=headers)
            assert finish.status_code == 200
            assert finish.get_json()["done"] is True
            assert client.post(timer,json={"action":"finish"},
                               headers=headers).status_code == 409
            conn = project.db()
            assert conn.execute("SELECT done FROM study_tasks WHERE id=?",
                                (task,)).fetchone()["done"] == 1
            # A changed roadmap must revoke prior lesson access.
            tampered = json.loads(json.dumps(sessions))
            tampered[0]["topics"] = ["Nội dung bị thay đổi"]
            conn.execute("UPDATE course_roadmaps SET sessions_json=? "
                         "WHERE user_id=? AND subject_id=?",
                         (json.dumps(tampered),uid,subject))
            conn.commit()
            conn.close()
            assert client.get(room).status_code == 409
            print("Mobile verified roadmap and timer PASS: ACL, 15 sessions, CSRF, stale")
        finally:
            project.DB_PATH,project.UPLOAD_DIR = old_db,old_upload


if __name__ == "__main__":
    check()
