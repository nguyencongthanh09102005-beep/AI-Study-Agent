"""Phase 6.1: opt-in, non-destructive import from verified roadmap to Study Plan.

The roadmap remains the source of WHAT to study. Study Plan tasks schedule WHEN.
Existing tasks and deadlines are never replaced, and a changed roadmap is not
silently applied to tasks the student has already rescheduled/completed.
"""
import hashlib
import json
from datetime import date, datetime


def ensure_session_schedule_schema(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(study_tasks)")}
    if "roadmap_session_id" not in columns:
        conn.execute("ALTER TABLE study_tasks ADD COLUMN roadmap_session_id INTEGER")
    if "roadmap_session_signature" not in columns:
        conn.execute("ALTER TABLE study_tasks ADD COLUMN roadmap_session_signature TEXT")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_study_tasks_roadmap_session
        ON study_tasks(user_id, subject_id, roadmap_session_id)
        WHERE roadmap_session_id IS NOT NULL
    """)
    # Do not commit: the caller owns the transaction.


def session_signature(lesson):
    """Detect when a regenerated lesson no longer matches its scheduled snapshot."""
    data = {
        "unit_id": lesson.get("unit_id"),
        "title": lesson.get("title"),
        "source_evidence": lesson.get("source_evidence"),
        "topics": lesson.get("topics") or [],
        "objectives": lesson.get("objectives") or [],
        "activities": lesson.get("activities") or [],
    }
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scheduled_lessons(conn, user_id, subject_id):
    ensure_session_schedule_schema(conn)
    return {
        int(row["roadmap_session_id"]): dict(row)
        for row in conn.execute("""
            SELECT id,roadmap_session_id,roadmap_session_signature,
                   study_at,duration,done
            FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND roadmap_session_id IS NOT NULL
        """, (user_id, subject_id))
    }


def import_roadmap_lessons(conn, user_id, subject_id, sessions, created_at):
    """Import *only* missing lessons. A second import does not reset progress.

    Validates every lesson before mutating the DB. When the roadmap has changed,
    an existing task is left untouched and reported as requiring review.
    """
    if not isinstance(sessions, list) or not 1 <= len(sessions) <= 80:
        raise ValueError("Lộ trình cần có từ 1 đến 80 buổi hợp lệ.")

    prepared = []
    seen = set()
    for lesson in sessions:
        if not isinstance(lesson, dict):
            raise ValueError("Dữ liệu buổi học không hợp lệ.")
        try:
            session_id = int(lesson["session_id"])
            duration = int(lesson["duration"])
            when = datetime.fromisoformat(
                str(lesson["date"]) + "T" + str(lesson["time"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Buổi học thiếu ngày, giờ hoặc mã hợp lệ.") from exc
        if (session_id < 1 or session_id in seen
                or not 15 <= duration <= 240):
            raise ValueError("Mã buổi học trùng hoặc thời lượng không hợp lệ.")
        seen.add(session_id)
        title = str(lesson.get("title") or "").strip()[:160]
        chapter = str(lesson.get("chapter") or "").strip()[:160]
        topics = [str(x).strip() for x in lesson.get("topics") or []][:8]
        if not title or not chapter:
            raise ValueError("Buổi học thiếu tên hoặc chương.")
        # Never alter historical tasks, even if their originally proposed date
        # is now in the past. Review/schedule adjustments follow in Phase 6.2.
        note = "\n".join(x for x in [
            "Lộ trình theo chương · " + chapter,
            "Kiến thức: " + "; ".join(topics) if topics else "",
            "Mục tiêu: " + "; ".join(str(x) for x in
                                  (lesson.get("objectives") or [])[:2]),
            "Hoạt động: " + "; ".join(str(x) for x in
                                    (lesson.get("activities") or [])[:2]),
        ] if x)[:950]
        prepared.append((
            session_id, title, when.isoformat(timespec="minutes"), duration,
            note, session_signature(lesson),
        ))

    linked = scheduled_lessons(conn, user_id, subject_id)
    new_count = 0
    unchanged_count = 0
    changed_count = 0
    for session_id, title, study_at, duration, note, signature in prepared:
        old = linked.get(session_id)
        if old:
            if old["roadmap_session_signature"] == signature:
                unchanged_count += 1
            else:
                changed_count += 1
            continue
        conn.execute("""
            INSERT INTO study_tasks (
                user_id,subject_id,title,study_at,duration,note,done,source,
                created_at,roadmap_session_id,roadmap_session_signature
            ) VALUES (?,?,?,?,?,?,0,'roadmap',?,?,?)
        """, (
            user_id, subject_id, title, study_at, duration, note, created_at,
            session_id, signature,
        ))
        new_count += 1

    return {
        "created": new_count,
        "existing": unchanged_count,
        "changed": changed_count,
    }
