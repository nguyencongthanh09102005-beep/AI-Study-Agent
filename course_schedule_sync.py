"""Phase 6.1: opt-in, non-destructive import from verified roadmap to Study Plan.

The roadmap remains the source of WHAT to study. Study Plan tasks schedule WHEN.
Existing tasks and deadlines are never replaced, and a changed roadmap is not
silently applied to tasks the student has already rescheduled/completed.
"""
import hashlib
import json
from datetime import datetime, time, timedelta

from study_schedule_conflicts import _interval
from adaptive_review_schedule import local_now


def ensure_session_schedule_schema(conn):
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(study_tasks)")}
    if "roadmap_session_id" not in columns:
        conn.execute("ALTER TABLE study_tasks ADD COLUMN roadmap_session_id INTEGER")
    if "roadmap_session_signature" not in columns:
        conn.execute("ALTER TABLE study_tasks ADD COLUMN roadmap_session_signature TEXT")
    if "roadmap_auto_study_at" not in columns:
        conn.execute("ALTER TABLE study_tasks ADD COLUMN roadmap_auto_study_at TEXT")
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
                   study_at,duration,done,roadmap_auto_study_at
            FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND roadmap_session_id IS NOT NULL
        """, (user_id, subject_id))
    }



# A preferred time is a preference, never an unconditional appointment.
# The actual timetable is built from all of this student's existing tasks.
DAY_START = time(7, 0)
DAY_END = time(22, 30)
BREAK_MINUTES = 15
MAX_SEARCH_DAYS = 180


def _ceil_quarter(value):
    base = value.replace(minute=(value.minute // 15) * 15,
                         second=0, microsecond=0)
    return base if base >= value else base + timedelta(minutes=15)


def _free_study_slot(preferred, duration_minutes, occupied, earliest):
    """Nearest available 15-minute slot, daytime only, with a study break.

    First search the requested day, then future days. No API/LLM call or
    invented external availability: only study_tasks belonging to this user.
    """
    duration = timedelta(minutes=duration_minutes)
    pause = timedelta(minutes=BREAK_MINUTES)
    starting_day = max(preferred.date(), earliest.date())
    for offset in range(MAX_SEARCH_DAYS):
        day = starting_day + timedelta(days=offset)
        first = _ceil_quarter(max(
            datetime.combine(day, DAY_START), earliest
        ))
        latest = datetime.combine(day, DAY_END) - duration
        choices = []
        cursor = first
        while cursor <= latest:
            choices.append(cursor)
            cursor += timedelta(minutes=15)
        target = datetime.combine(day, preferred.time())
        choices.sort(key=lambda candidate: (
            abs((candidate - target).total_seconds()),
            candidate < target, candidate,
        ))
        for candidate in choices:
            end = candidate + duration
            if all(end + pause <= busy_start or
                   candidate >= busy_end + pause
                   for busy_start, busy_end in occupied):
                return candidate
    raise ValueError(
        "Không còn giờ trống phù hợp trong 180 ngày tới. "
        "Hãy kiểm tra các buổi học, deadline và giờ học ưu tiên."
    )


def import_roadmap_lessons(conn, user_id, subject_id, sessions, created_at,
                           reschedule_existing=False, reference_time=None):
    """Import missing lessons into free time without moving any existing task.

    An explicitly requested reflow may move only future, unfinished roadmap
    sessions whose original source can be verified and whose time is not
    manually locked. Neither action touches old manual/AI/deadline tasks.
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

    # All validation above finishes before we consider changing any tasks.
    prepared.sort(key=lambda row: row[0])
    linked = scheduled_lessons(conn, user_id, subject_id)
    # Study times are Vietnam-local naive datetimes, not server UTC.
    now = reference_time or local_now()
    if not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError("Giờ hiện tại không hợp lệ.")
    future_floor = _ceil_quarter(now + timedelta(minutes=15))

    movable = set()
    if reschedule_existing:
        from adaptive_plan_phase8 import is_manual_roadmap_time
        for sid, _title, _at, _duration, _note, signature in prepared:
            old = linked.get(sid)
            if (old and not old["done"]
                    and old["roadmap_session_signature"] == signature
                    and datetime.fromisoformat(old["study_at"]) >= now
                    and not is_manual_roadmap_time(conn, user_id, old["id"])):
                movable.add(old["id"])

    occupied = []
    for row in conn.execute(
        "SELECT id,study_at,duration FROM study_tasks WHERE user_id=?",
        (user_id,),
    ):
        if row["id"] in movable:
            continue
        interval = _interval(row)
        if interval:
            occupied.append(interval)

    new_count = unchanged_count = changed_count = moved_count = 0
    previous_start = None
    for session_id, title, study_at, duration, note, signature in prepared:
        old = linked.get(session_id)
        if old and old["id"] not in movable:
            if old["roadmap_session_signature"] == signature:
                unchanged_count += 1
            else:
                changed_count += 1
            # Preserve the original order as far as existing, immutable
            # sessions permit. Never move those older sessions automatically.
            try:
                previous_start = datetime.fromisoformat(old["study_at"])
            except ValueError:
                pass
            continue

        preferred = datetime.fromisoformat(study_at)
        earliest = max(datetime.combine(preferred.date(), DAY_START),
                       future_floor)
        if previous_start is not None:
            earliest = max(earliest, datetime.combine(
                previous_start.date() + timedelta(days=1), DAY_START))
        assigned = _free_study_slot(preferred, duration, occupied, earliest)
        assigned_at = assigned.isoformat(timespec="minutes")
        if old:
            if assigned_at != old["study_at"]:
                conn.execute("""
                    UPDATE study_tasks
                    SET study_at=?,roadmap_auto_study_at=?
                    WHERE id=? AND user_id=? AND source='roadmap' AND done=0
                """, (assigned_at, assigned_at, old["id"], user_id))
                moved_count += 1
            else:
                # Mark legacy unedited roadmap times as system-assigned so
                # a later Agent proposal does not mistake them for user edits.
                conn.execute("""
                    UPDATE study_tasks SET roadmap_auto_study_at=?
                    WHERE id=? AND user_id=?
                """, (assigned_at, old["id"], user_id))
            unchanged_count += 1
        else:
            conn.execute("""
                INSERT INTO study_tasks (
                    user_id,subject_id,title,study_at,duration,note,done,source,
                    created_at,roadmap_session_id,roadmap_session_signature,
                    roadmap_auto_study_at
                ) VALUES (?,?,?,?,?,?,0,'roadmap',?,?,?,?)
            """, (
                user_id, subject_id, title, assigned_at, duration, note,
                created_at, session_id, signature, assigned_at,
            ))
            new_count += 1
        occupied.append((assigned, assigned + timedelta(minutes=duration)))
        previous_start = assigned

    return {
        "created": new_count,
        "existing": unchanged_count,
        "changed": changed_count,
        "moved": moved_count,
    }
