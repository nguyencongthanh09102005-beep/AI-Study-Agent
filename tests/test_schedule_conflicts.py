"""Pure scheduling and Flask regression checks for Phase 6.2.2."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from study_schedule_conflicts import find_study_conflicts
import app as project


def _row(id, start, duration=45, title=None):
    return {"id": id, "study_at": start, "duration": duration, "title": title or f"Buổi {id}"}


def verify_logic():
    # Different start times that partially intersect must be detected.
    rows = [_row(1, "2026-11-02T19:00"),
            _row(2, "2026-11-02T19:30"),
            _row(3, "2026-11-02T20:15"),
            _row(4, "2026-11-03T19:00")]
    collisions = find_study_conflicts(rows)
    assert set(collisions) == {1, 2}
    assert collisions[1]["with_ids"] == [2]
    # 19:30-20:15 blocks 19:00-19:45; allow a break until 20:30.
    assert collisions[1]["suggested_at"] == "2026-11-02T20:30"
    assert collisions[2]["suggested_at"] == "2026-11-02T20:00"
    assert not find_study_conflicts([_row(1, "2026-11-02T19:00"),
                                     _row(2, "2026-11-02T19:45")])
    # Midnight crossing, not just matching the YYYY-MM-DD substring.
    midnight = find_study_conflicts([
        _row(5, "2026-11-02T23:45", 45),
        _row(6, "2026-11-03T00:10", 45)])
    assert set(midnight) == {5, 6}
    assert midnight[5]["suggested_at"] == ""
    assert not find_study_conflicts([_row(1, "bad-date"), _row(2, "2026-11-02T19:00")])
    # Two different courses can overlap; suggestions never mutate task records.
    assert rows[0]["study_at"] == "2026-11-02T19:00"


def verify_web():
    with TemporaryDirectory() as directory:
        old = project.DB_PATH
        try:
            project.DB_PATH = Path(directory) / "schedule_collision.db"
            project.init_db()
            conn = project.db()
            student = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                ("Schedule A", "scheduling-a@test.local", "hash", project.now())
            ).lastrowid
            outsider = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                ("Schedule B", "scheduling-b@test.local", "hash", project.now())
            ).lastrowid
            subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (student, "CTDL", "DS-OVERLAP", project.now())
            ).lastrowid
            other_subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (student, "OOP", "OOP-OVERLAP", project.now())
            ).lastrowid
            for i, (owner, course, at, dur) in enumerate([
                    (student, subject, "2026-11-02T19:00", 45),
                    (student, other_subject, "2026-11-02T19:30", 45),
                    (outsider, None, "2026-11-02T19:00", 45)], 1):
                conn.execute("""INSERT INTO study_tasks
                    (user_id,subject_id,title,study_at,duration,note,done,source,created_at)
                    VALUES(?,?,?,?,?,'',0,'manual',?)""",
                    (owner, course, f"Kiểm tra {i}", at, dur, project.now()))
            conn.commit()
            conn.close()
            client = project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"], sess["user_name"] = student, "Schedule A"
            body = client.get("/study-plan").get_data(as_text=True)
            assert "2 buổi học đang trùng giờ" in body
            assert 'data-task-conflict="1"' in body
            assert "20:30" in body
            assert "study_schedule_conflicts.css" in body
            assert "Kiểm tra 3" not in body
            # The edit endpoint remains user-controlled; detect, don't auto-shift.
            before = project.db().execute("SELECT study_at FROM study_tasks WHERE id=1").fetchone()[0]
            assert before == "2026-11-02T19:00"
            with client.session_transaction() as sess:
                sess["user_id"], sess["user_name"] = outsider, "Schedule B"
            other_body = client.get("/study-plan").get_data(as_text=True)
            assert "2 buổi học đang trùng giờ" not in other_body
        finally:
            project.DB_PATH = old


if __name__ == "__main__":
    verify_logic()
    verify_web()
    print("Phase 6.2.2 schedule conflicts and suggestions OK")
