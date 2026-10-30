"""Deterministic multi-subject conflict-free roadmap import and safe reflow."""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from adaptive_plan_phase8 import is_manual_roadmap_time, lock_manual_roadmap_time
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import (
    _free_study_slot, import_roadmap_lessons, session_signature,
)
from study_schedule_conflicts import find_study_conflicts


NOW = datetime(2026, 11, 2, 12)


def lessons(first="2026-11-03", count=2):
    day = datetime.fromisoformat(first)
    return [{
        "session_id": i + 1, "unit_id": 1, "chapter": "Chương 1",
        "source_evidence": "Chương 1", "title": f"Buổi học {i+1}",
        "date": (day + timedelta(days=i)).date().isoformat(),
        "time": "19:00", "duration": 45,
        "topics": ["Kiến thức thật"], "objectives": [], "activities": [],
    } for i in range(count)]


def task(conn, uid, sid, when, source="manual", done=0, roadmap_id=None,
         signature=None):
    return conn.execute("""
        INSERT INTO study_tasks(
            user_id,subject_id,title,study_at,duration,note,done,source,
            created_at,roadmap_session_id,roadmap_session_signature
        ) VALUES(?,?,?,?,45,'',?,?,?, ?, ?)
    """, (uid, sid, source, when, done, source, "2026-11-02T09:00",
          roadmap_id, signature)).lastrowid


def test():
    # The study-plan API and schema use SQLite; no Gemini calls required.
    previous = project.DB_PATH
    try:
        with tempfile.TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "smart-schedule.sqlite"
            project.init_db()
            conn = project.db()
            ensure_roadmap_schema(conn)
            student = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student A','schedule-smart-a@test.local','hash','student','now')
            """).lastrowid
            outsider = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student B','schedule-smart-b@test.local','hash','student','now')
            """).lastrowid
            courses = [conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, f"Môn {i}", f"SMART{i}", "now")).lastrowid
                for i in range(1, 4)]
            src = lessons()
            for sid in courses:
                conn.execute("""
                    INSERT INTO course_roadmaps(
                        user_id,subject_id,source_hash,units_hash,sessions_json,updated_at
                    ) VALUES(?,?,?,?,?,?)
                """, (student, sid, "verified", "verified", json.dumps(src), "now"))
            # The 19:00 time is already reserved by a manual task on both days.
            originals = [
                task(conn, student, courses[0], "2026-11-03T19:00"),
                task(conn, student, courses[0], "2026-11-04T19:00"),
            ]
            # Other student's data must not become a scheduling constraint.
            task(conn, outsider, None, "2026-11-03T20:00")
            conn.commit()

            a = import_roadmap_lessons(
                conn, student, courses[0], src, "now", reference_time=NOW
            )
            b = import_roadmap_lessons(
                conn, student, courses[1], src, "now", reference_time=NOW
            )
            assert a["created"] == b["created"] == 2
            rows = conn.execute("""
                SELECT id,subject_id,study_at,duration,roadmap_auto_study_at
                FROM study_tasks WHERE user_id=? AND source='roadmap'
                ORDER BY subject_id,roadmap_session_id
            """, (student,)).fetchall()
            assert len(rows) == 4
            assert all(r["study_at"] == r["roadmap_auto_study_at"] for r in rows)
            assert all("T19:00" not in r["study_at"] for r in rows)
            assert not find_study_conflicts(conn.execute("""
                SELECT id,title,study_at,duration FROM study_tasks WHERE user_id=?
            """, (student,)).fetchall())
            for row in rows:
                assert not is_manual_roadmap_time(conn, student, row["id"])
                start = datetime.fromisoformat(row["study_at"])
                assert start.hour >= 7
                assert start + timedelta(minutes=45) <= start.replace(
                    hour=22, minute=30)
                assert start > NOW
            assert [r[0] for r in conn.execute("""
                SELECT study_at FROM study_tasks WHERE id IN (?,?)
            """, originals)] == ["2026-11-03T19:00", "2026-11-04T19:00"]

            before = {r["id"]: r["study_at"] for r in rows}
            repeat = import_roadmap_lessons(
                conn, student, courses[0], src, "now", reference_time=NOW
            )
            assert repeat["created"] == repeat["moved"] == 0
            assert {r["id"]: r["study_at"] for r in conn.execute("""
                SELECT id,study_at FROM study_tasks WHERE user_id=?
                  AND source='roadmap'
            """, (student,))} == before

            # Explicit user edits create a lock and survive reflow.
            first = rows[0]["id"]
            lock_manual_roadmap_time(conn, student, first)
            conn.execute("UPDATE study_tasks SET study_at=? WHERE id=?",
                         ("2026-11-08T16:00", first))
            assert is_manual_roadmap_time(conn, student, first)

            # Legacy pre-fix 19:00 import colliding with an existing course.
            old_plan = lessons("2026-11-05", 1)
            conn.execute("""
                UPDATE course_roadmaps SET sessions_json=?
                WHERE user_id=? AND subject_id=?
            """, (json.dumps(old_plan), student, courses[2]))
            legacy_id = task(conn, student, courses[2], "2026-11-05T19:00",
                             source="roadmap", roadmap_id=1,
                             signature=session_signature(old_plan[0]))
            manual_id = task(conn, student, courses[0], "2026-11-05T19:00")
            assert not is_manual_roadmap_time(conn, student, legacy_id)
            conn.commit()
            changed = import_roadmap_lessons(
                conn, student, courses[2], old_plan, "now",
                reschedule_existing=True, reference_time=NOW
            )
            assert changed["moved"] == 1, changed
            legacy_after = conn.execute("""
                SELECT study_at,roadmap_auto_study_at FROM study_tasks
                WHERE id=?
            """, (legacy_id,)).fetchone()
            assert legacy_after["study_at"] != "2026-11-05T19:00"
            assert legacy_after["study_at"] == legacy_after["roadmap_auto_study_at"]
            assert not is_manual_roadmap_time(conn, student, legacy_id)
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (manual_id,)).fetchone()[0] == "2026-11-05T19:00"
            # Reflow of a course with a manually locked session must keep it.
            import_roadmap_lessons(
                conn, student, courses[0], src, "now",
                reschedule_existing=True, reference_time=NOW
            )
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (first,)).fetchone()[0] == "2026-11-08T16:00"
            # Complete lessons are immutable even when the preferred time clashes.
            conn.execute("UPDATE study_tasks SET done=1 WHERE id=?", (legacy_id,))
            last_time = legacy_after["study_at"]
            task(conn, student, courses[0], last_time)
            import_roadmap_lessons(
                conn, student, courses[2], old_plan, "now",
                reschedule_existing=True, reference_time=NOW
            )
            assert conn.execute("SELECT study_at FROM study_tasks WHERE id=?",
                                (legacy_id,)).fetchone()[0] == last_time

            # A whole occupied day pushes the new lesson to a future day.
            next_day = _free_study_slot(
                datetime(2026, 11, 3, 19), 45,
                [(datetime(2026, 11, 3, 7), datetime(2026, 11, 3, 22, 30))],
                NOW,
            )
            assert next_day == datetime(2026, 11, 4, 19)
            conn.close()
    finally:
        project.DB_PATH = previous
    print("Smart roadmap scheduling PASS: multi-course conflicts, breaks, privacy, "
          "future daytime, reflow, legacy, manual locks, done, and idempotency")


if __name__ == "__main__":
    test()
