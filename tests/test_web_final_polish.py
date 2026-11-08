"""Release Web polish: weekly totals prefer real timer, preserve legacy estimates.

Disposable DB only. Does not call external AI APIs or touch real student files.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from study_session_tracking import ensure_tracking_schema


def run():
    original_db, original_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as tmp:
            project.DB_PATH = Path(tmp) / "web-polish.sqlite"
            project.UPLOAD_DIR = Path(tmp) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            today = datetime.now().replace(second=0, microsecond=0)
            stamp = today.isoformat(timespec="minutes")
            last_week = (today - timedelta(days=7)).isoformat(timespec="minutes")
            owner = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES(?,?,?,?,?)",
                ("Web QA", "web-polish@test.local", "hash", "student", stamp),
            ).lastrowid
            stranger = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES(?,?,?,?,?)",
                ("Other", "other-web-polish@test.local", "hash", "student", stamp),
            ).lastrowid
            subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,credits,created_at) "
                "VALUES(?,?,?,?,?)",
                (owner, "Kiểm thử Web", "WEB-QA", 3, stamp),
            ).lastrowid

            def task(uid, when, duration, done=1):
                return conn.execute(
                    "INSERT INTO study_tasks(user_id,subject_id,title,study_at,"
                    "duration,done,completed_at,source,created_at) "
                    "VALUES(?,?,?,?,?,?,?,'manual',?)",
                    (uid, subject if uid == owner else None, "Học thử",
                     when, duration, done, when if done else "", stamp),
                ).lastrowid

            timed = task(owner, stamp, 90)
            legacy = task(owner, stamp, 45)
            previous = task(owner, last_week, 120)
            task(owner, stamp, 200, done=0)
            task(stranger, stamp, 300)
            ensure_tracking_schema(conn)
            for task_id, when, elapsed in [
                (timed, stamp, 15 * 60),
                (previous, last_week, 30 * 60),
            ]:
                conn.execute(
                    "INSERT INTO study_session_tracking(task_id,user_id,subject_id,"
                    "status,started_at,last_heartbeat_at,elapsed_seconds,completed_at,"
                    "updated_at) VALUES(?,?,?,'completed',?,?,?,?,?)",
                    (task_id, owner, subject, when, when, elapsed, when, when),
                )
            conn.commit()
            conn.close()
            client = project.app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = owner
                session["user_name"] = "Web QA"
            response = client.get("/dashboard")
            assert response.status_code == 200, response.get_data(as_text=True)[:1000]
            html = response.get_data(as_text=True)
            data_match = re.search(
                r"window\.weeklyStudyData = (\[[^;]*\]);", html
            )
            assert data_match, "Dashboard must expose real weekly values"
            values = json.loads(data_match.group(1))
            assert len(values) == 7
            assert values[today.weekday()] == 1.0, values
            assert abs(sum(values) - 1.0) < 0.001, values
            assert "1.0 giờ" in html, "Total: 15m real + 45m legacy"
            assert "+100%" in html, "Previous week: 30m real"
            assert "weeklyChartFallback" in html
            assert "Chưa xếp lịch" not in html, "Roadmap badges belong on learning path"

            # Older databases can have no tracking table at all. Do not fail
            # on those users; planned duration remains the fallback estimate.
            conn = project.db()
            conn.execute("DROP TABLE study_session_tracking")
            conn.commit()
            conn.close()
            no_timer = client.get("/dashboard")
            assert no_timer.status_code == 200
            match = re.search(
                r"window\.weeklyStudyData = (\[[^;]*\]);",
                no_timer.get_data(as_text=True),
            )
            assert match
            assert json.loads(match.group(1))[today.weekday()] == 2.25

    finally:
        project.DB_PATH, project.UPLOAD_DIR = original_db, original_upload
    print("Web polish PASS: timer-backed hours, legacy fallback, private scope, chart data")


if __name__ == "__main__":
    run()
