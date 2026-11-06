"""Phase 6.1: opt-in, non-destructive import from verified roadmap to Study Plan.

The roadmap remains the source of WHAT to study. Study Plan tasks schedule WHEN.
Existing tasks and deadlines are never replaced, and a changed roadmap is not
silently applied to tasks the student has already rescheduled/completed.
"""
import hashlib
import json
import re
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roadmap_schedule_preferences (
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            preferred_start_time TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (user_id, subject_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
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
            SELECT id,title,roadmap_session_id,roadmap_session_signature,
                   study_at,duration,done,roadmap_auto_study_at
            FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND roadmap_session_id IS NOT NULL
        """, (user_id, subject_id))
    }



def reconcile_blocker(conn, uid, subject_id, task):
    """Protect finished lessons, tracked study time and submitted Quiz history.

    No Quiz answers, history or source provenance are rewritten. This check is
    also repeated on POST; the display-time check is informational only.
    """
    if task["done"]:
        return "Buổi đã hoàn thành; không thể đổi nội dung học đã ghi nhận."
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if "study_session_tracking" in tables:
        tracked = conn.execute("""
            SELECT status, elapsed_seconds FROM study_session_tracking
            WHERE task_id=? AND user_id=?
        """, (task["id"], uid)).fetchone()
        if tracked and (tracked["status"] != "idle" or
                        int(tracked["elapsed_seconds"] or 0) > 0):
            return "Buổi đã ghi nhận thời gian học; cần đối chiếu thủ công."
    if "quiz_session_links" in tables and "quiz_attempts" in tables:
        attempted = conn.execute("""
            SELECT 1 FROM quiz_attempts a
            JOIN quiz_session_links l ON l.quiz_id=a.quiz_id
            WHERE l.task_id=? AND l.user_id=? AND a.user_id=?
            LIMIT 1
        """, (task["id"], uid, uid)).fetchone()
        if attempted:
            return "Buổi đã có kết quả Quiz; không thể tự thay đổi nội dung cũ."
    if "quiz_preparation_jobs" in tables:
        busy = conn.execute("""
            SELECT 1 FROM quiz_preparation_jobs
            WHERE user_id=? AND subject_id=? AND state IN ('queued','running')
        """, (uid, subject_id)).fetchone()
        if busy:
            return "Đang chuẩn bị Quiz cho môn; hãy tạm dừng tác vụ trước."
    return None


def confirm_changed_roadmap_lesson(conn, uid, subject_id, task_id, lesson,
                                   expected_old, expected_new):
    """Explicitly accept ONE regenerated lesson; never replace its schedule.

    Historic Quiz rows keep their original provenance and remain archived if
    the content no longer matches. Re-preparation uses the new verified lesson.
    The owning Flask route must first verify the confirmed syllabus/roadmap.
    """
    if not isinstance(lesson, dict) or not isinstance(lesson.get("session_id"), int):
        raise ValueError("Buổi học trong lộ trình không hợp lệ.")
    signature = session_signature(lesson)
    if not expected_old or not expected_new or signature != expected_new:
        raise ValueError("Lộ trình đã thay đổi khi đang rà soát; hãy tải lại trang.")
    task = conn.execute("""
        SELECT * FROM study_tasks
        WHERE id=? AND user_id=? AND subject_id=? AND source='roadmap'
          AND roadmap_session_id IS NOT NULL
    """, (task_id, uid, subject_id)).fetchone()
    if not task or int(task["roadmap_session_id"]) != lesson["session_id"]:
        raise ValueError("Buổi học không thuộc lộ trình đã xác nhận của tài khoản.")
    if task["roadmap_session_signature"] != expected_old:
        raise ValueError("Buổi đã được thay đổi ở nơi khác; hãy tải lại trang.")
    reason = reconcile_blocker(conn, uid, subject_id, task)
    if reason:
        raise ValueError(reason)
    if expected_old == signature:
        return False
    new_title = str(lesson.get("title") or "").strip()[:160]
    if not new_title:
        raise ValueError("Buổi học mới thiếu tên.")
    updated = conn.execute("""
        UPDATE study_tasks SET roadmap_session_signature=?,title=?
        WHERE id=? AND user_id=? AND subject_id=? AND source='roadmap'
          AND roadmap_session_signature=? AND done=0
    """, (signature, new_title, task_id, uid, subject_id,
          expected_old))
    if updated.rowcount != 1:
        raise ValueError("Buổi học vừa thay đổi; hãy tải lại trang.")
    return True


# A preferred time is a preference, never an unconditional appointment.
# The actual timetable is built from all of this student's existing tasks.
OFFICIAL_WINDOWS = ((time(7, 30), time(11, 30)), (time(13, 0), time(17, 0)))
# Self-study suggestions use 19:00–22:00; imported official lessons never
# occupy the evening automatically. Sunday is a day off for both.
SELF_STUDY_WINDOW = (time(19, 0), time(22, 0))
BREAK_MINUTES = 15
MAX_SEARCH_DAYS = 180


def _ceil_quarter(value):
    base = value.replace(minute=(value.minute // 15) * 15,
                         second=0, microsecond=0)
    return base if base >= value else base + timedelta(minutes=15)


def _validated_study_clock(value):
    """An optional user-selected clock time; never parse arbitrary date text."""
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("Giờ học mong muốn không hợp lệ. Hãy chọn theo định dạng HH:MM.")
    return time.fromisoformat(value)


def _free_study_slot(preferred, duration_minutes, occupied, earliest,
                     exact_time=None):
    """Find a free Mon–Sat slot, preserving a 15-minute break.

    Automatic mode uses daytime windows. When a student explicitly supplies
    a clock time, keep that precise time and move to the next free day rather
    than silently shifting the clock hour.
    """
    duration = timedelta(minutes=duration_minutes)
    pause = timedelta(minutes=BREAK_MINUTES)
    starting_day = max(preferred.date(), earliest.date())
    for offset in range(MAX_SEARCH_DAYS):
        day = starting_day + timedelta(days=offset)
        if day.weekday() == 6:
            continue
        choices = []
        if exact_time is not None:
            selected = datetime.combine(day, exact_time)
            if (selected >= earliest and
                    selected + duration <= datetime.combine(
                        day + timedelta(days=1), time.min)):
                choices = [selected]
        else:
            for window_start, window_end in OFFICIAL_WINDOWS:
                cursor = _ceil_quarter(max(datetime.combine(day, window_start),
                                           earliest))
                latest = datetime.combine(day, window_end) - duration
                while cursor <= latest:
                    choices.append(cursor)
                    cursor += timedelta(minutes=15)
            target = datetime.combine(day, preferred.time())
            choices.sort(key=lambda candidate: (
                abs((candidate - target).total_seconds()),
                candidate,
            ))
        for candidate in choices:
            end = candidate + duration
            if all(end + pause <= busy_start or
                   candidate >= busy_end + pause
                   for busy_start, busy_end in occupied):
                return candidate
    if exact_time is not None:
        raise ValueError(
            "Không tìm được ngày trống vào đúng giờ đã chọn trong 180 ngày "
            "(thứ Hai–thứ Bảy). Hãy chọn giờ khác hoặc kiểm tra Kế hoạch học."
        )
    raise ValueError(
        "Không còn giờ trống chính khóa từ thứ Hai đến thứ Bảy "
        "trong 180 ngày tới. Hãy kiểm tra thời khóa biểu hoặc tự chọn giờ."
    )


def import_roadmap_lessons(conn, user_id, subject_id, sessions, created_at,
                           reschedule_existing=False, reference_time=None,
                           preferred_start_time=None):
    """Import missing lessons into free time without moving any existing task.

    An explicitly requested reflow may move only future, unfinished roadmap
    sessions whose original source can be verified and whose time is not
    manually locked. Neither action touches old manual/AI/deadline tasks.
    """
    if not isinstance(sessions, list) or not 1 <= len(sessions) <= 80:
        raise ValueError("Lộ trình cần có từ 1 đến 80 buổi hợp lệ.")
    selected_clock = _validated_study_clock(preferred_start_time)

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

    # Reject impossible same-day clock times before changing any task.
    if selected_clock is not None:
        for _sid, _title, _at, duration, _note, _signature in prepared:
            start = datetime.combine(datetime.fromisoformat(_at).date(), selected_clock)
            if (start + timedelta(minutes=duration)).date() != start.date():
                raise ValueError(
                    "Giờ bắt đầu đã chọn khiến buổi học kết thúc sang ngày hôm sau. "
                    "Hãy chọn giờ sớm hơn."
                )
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
        start_of_day = selected_clock or OFFICIAL_WINDOWS[0][0]
        earliest = max(datetime.combine(preferred.date(), start_of_day),
                       future_floor)
        if previous_start is not None:
            earliest = max(earliest, datetime.combine(
                previous_start.date() + timedelta(days=1), start_of_day))
        assigned = _free_study_slot(
            preferred, duration, occupied, earliest, exact_time=selected_clock
        )
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
