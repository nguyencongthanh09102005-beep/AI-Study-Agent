"""Regression: Study Plan is a calendar sourced from verified roadmap.

Removing the duplicate Web AI Planner MUST NOT delete existing AI plans,
roadmap lessons, manually scheduled sessions, reminders or mobile/backend APIs.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_schedule_sync import ensure_session_schedule_schema


def run():
    orig_db, orig_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "roadmap-first.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_session_schedule_schema(conn)
            now = project.now()
            students = []
            for name in ("planner-student", "second-student"):
                students.append(conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,'student',?)",
                    (name, name + "@local.test", "hash", now)
                ).lastrowid)
            uid, other_uid = students
            sid = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) "
                "VALUES(?,'Lịch sử Đảng','HIS102',?)", (uid, now)
            ).lastrowid
            day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT19:00")
            sources = {
                "roadmap": "Chương 1 – Buổi học từ lộ trình",
                "ai": "Kế hoạch AI cũ cần bảo toàn",
                "manual": "Buổi học thêm thủ công",
            }
            saved = {}
            for kind, title in sources.items():
                saved[kind] = conn.execute(
                    """INSERT INTO study_tasks(user_id,subject_id,title,study_at,
                        duration,note,done,source,created_at,roadmap_session_id)
                       VALUES(?,?,?,?,45,'',0,?,?,?)""",
                    (uid, sid, title, day, kind, now,
                     1 if kind == "roadmap" else None)
                ).lastrowid
            reminder = conn.execute(
                """INSERT INTO reminders(user_id,subject_id,title,due_at,source,created_at)
                   VALUES(?,?,?,?,'ai',?)""",
                (uid, sid, "Deadline của kế hoạch cũ", day, now)
            ).lastrowid
            conn.commit()

            client = project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = uid
            res = client.get("/study-plan")
            assert res.status_code == 200, res.get_data(as_text=True)[:700]
            html = res.get_data(as_text=True)
            for forbidden in ('id="openAiPlanner"', 'id="aiPlannerModal"',
                              'id="aiPlannerForm"', 'Tạo kế hoạch mới'):
                assert forbidden not in html, forbidden
            assert 'id="openQuickTask"' in html
            assert 'id="taskModal"' in html
            assert 'id="plannerTimetable"' in html
            assert 'data-view="week"' in html
            assert 'data-view="month"' in html
            assert 'data-view="list"' in html
            assert 'id="deadline-list"' in html
            assert "Tiến độ tuần này" in html
            assert "Gợi ý từ Study Agent" in html
            assert "Mục tiêu & deadline" in html
            for kind, title in sources.items():
                assert title in html
                assert f'data-task-source="{kind}"' in html
                assert html.count(f'data-task-id="{saved[kind]}"') == 1
            assert "Bắt đầu học" in html  # existing roadmap study-room link
            assert "Deadline của kế hoạch cũ" in html
            assert 'href="/subjects"' in html  # guidance to course roadmap

            # Rendering cannot remove, recreate or silently reschedule old tasks.
            current = conn.execute(
                "SELECT id,source,study_at,done FROM study_tasks "
                "WHERE user_id=? ORDER BY id", (uid,)
            ).fetchall()
            assert [(x["id"],x["source"],x["study_at"],x["done"]) for x in current] == [
                (saved[kind], kind, day, 0) for kind in sources
            ]
            assert conn.execute(
                "SELECT COUNT(*) FROM reminders WHERE id=?", (reminder,)
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE user_id=?",
                (other_uid,)
            ).fetchone()[0] == 0

            added = client.post("/study-plan/tasks/create", data={
                "subject_id": str(sid), "title": "Ôn tập bổ sung",
                "study_at": day, "duration": 30, "note": "Tự chọn",
            })
            assert added.status_code in (302, 303)
            after = conn.execute(
                "SELECT source FROM study_tasks WHERE user_id=? AND title=?",
                (uid, "Ôn tập bổ sung")
            ).fetchone()
            assert after and after["source"] == "manual"
            assert conn.execute(
                "SELECT COUNT(*) FROM study_tasks WHERE user_id=? "
                "AND source='ai'", (uid,)
            ).fetchone()[0] == 1
            assert callable(project.generate_study_plan_route), (
                "Retain legacy backend for Mobile and existing links"
            )
            conn.close()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = orig_db, orig_upload
    print("Study Plan roadmap-first PASS: old AI/roadmap sessions, deadline, manual add, views, privacy")


if __name__ == "__main__":
    run()
