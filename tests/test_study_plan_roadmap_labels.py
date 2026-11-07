"""Verified roadmap labels in Web timetable: owner, snapshot, final exam and fallback."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, session_signature
from study_plan_roadmap_labels import roadmap_timetable_labels


def lesson(number, chapter, *, final=False):
    entry = {
        "session_id": number, "unit_id": 1,
        "title": "Ôn tập tổng hợp và kiểm tra cuối môn" if final
                 else f"{chapter} — Buổi 2/3",
        "chapter": chapter,
        "source_evidence": chapter, "topics": ["Kiến thức 1"],
        "objectives": ["Nắm vững kiến thức"], "activities": ["Học bài"],
    }
    if final:
        entry["quiz"] = {"action": "quiz_final", "recommended_questions": 60}
    return entry


def run():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "roadmap-timetable.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            ensure_roadmap_schema(conn)
            ensure_session_schedule_schema(conn)
            now = project.now()
            uid = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                ("Calendar Student", "calendar-student@test.local", "hash", now)
            ).lastrowid
            foreign_uid = conn.execute(
                "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
                ("Other Student", "calendar-other@test.local", "hash", now)
            ).lastrowid
            subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (uid, "Lịch sử Đảng", "HIS", now)
            ).lastrowid
            foreign_subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (foreign_uid, "Môn bí mật", "PRIVATE", now)
            ).lastrowid

            active = lesson(2, "Chương 1. Tổng quan")
            final = lesson(15, "Chương 4. Tổng kết", final=True)
            newer = lesson(3, "Chương 2. Nội dung đã cập nhật")
            foreign = lesson(2, "Chương 9. Không được xem")
            conn.execute(
                """INSERT INTO course_roadmaps
                   (user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (uid, subject, "source", "units",
                 json.dumps([active, final, newer], ensure_ascii=False), now)
            )
            conn.execute(
                """INSERT INTO course_roadmaps
                   (user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)
                   VALUES(?,?,?,?,?,?)""",
                (foreign_uid, foreign_subject, "source", "units",
                 json.dumps([foreign], ensure_ascii=False), now)
            )
            on_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT19:00")
            task_ids = {}
            rows = [
                ("linked", uid, subject, "roadmap", 2, session_signature(active),
                 "Tên dài buổi học chương 1"),
                ("final", uid, subject, "roadmap", 15, session_signature(final),
                 "Ôn tập tổng hợp và kiểm tra cuối môn"),
                ("stale", uid, subject, "roadmap", 3, "old-snapshot-hash",
                 "Chương 2 theo lịch cũ"),
                ("manual", uid, subject, "manual", None, None,
                 "Tự học Figma do sinh viên nhập"),
                ("other", foreign_uid, foreign_subject, "roadmap", 2,
                 session_signature(foreign), "Không dành cho tài khoản này"),
            ]
            for key, student, course, source, sid, signature, title in rows:
                task_ids[key] = conn.execute(
                    """INSERT INTO study_tasks
                       (user_id,subject_id,title,study_at,duration,note,done,source,
                        created_at,roadmap_session_id,roadmap_session_signature)
                       VALUES(?,?,?,?,45,'',0,?,?,?,?)""",
                    (student, course, title, on_date, source, now, sid, signature)
                ).lastrowid
            conn.commit()
            all_rows = conn.execute("SELECT * FROM study_tasks").fetchall()
            labels = roadmap_timetable_labels(conn, uid, all_rows)
            assert labels == {
                task_ids["linked"]: "Chương 1 · Buổi 2",
                task_ids["final"]: "Ôn tập cuối môn · Buổi 15",
            }, labels
            # No crashes or manufactured labels for accounts without roadmaps.
            assert roadmap_timetable_labels(conn, 987654, all_rows) == {}
            conn.close()

            client = project.app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = uid
                session["user_name"] = "Calendar Student"
            res = client.get("/study-plan")
            assert res.status_code == 200, res.get_data(as_text=True)[:700]
            html = res.get_data(as_text=True)
            assert html.count('data-task-roadmap-label="Chương 1 · Buổi 2"') == 1
            assert html.count(
                'data-task-roadmap-label="Ôn tập cuối môn · Buổi 15"'
            ) == 1
            assert html.count('data-task-roadmap-label=""') >= 2
            assert "Chương 9. Không được xem" not in html
            assert "Không dành cho tài khoản này" not in html
            assert "Tự học Figma do sinh viên nhập" in html
            assert "Chương 2 theo lịch cũ" in html
            js = (Path(__file__).resolve().parents[1] /
                  "static/js/study_plan.js").read_text(encoding="utf-8")
            assert 'item.dataset.taskRoadmapLabel' in js
            assert 'const subtitle = roadmapLabel || title;' in js
            assert 'makeDiv("study-hour-event-tag", "Từ lộ trình")' not in js
            assert 'makeDiv("study-hour-event-complete", "✓")' in js
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Verified timetable roadmap labels PASS: source, final, stale, manual, owner")


if __name__ == "__main__":
    run()
