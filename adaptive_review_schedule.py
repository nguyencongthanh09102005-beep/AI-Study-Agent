"""Phase 7.5.3: conflict-free adaptive review slots and manual time locks.

This module never edits a regular roadmap/AI/manual lesson. All times are
Vietnam-local naive timestamps, consistent with the existing study planner.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

VIETNAM = ZoneInfo("Asia/Ho_Chi_Minh")


def local_now():
    return datetime.now(VIETNAM).replace(tzinfo=None)


def ensure_review_schedule_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adaptive_review_time_locks (
            task_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            locked_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)


def lock_adaptive_time(conn, task_id, user_id):
    """Called only after an owner manually edits their adaptive review task."""
    ensure_review_schedule_schema(conn)
    found = conn.execute("""
        SELECT id FROM study_tasks
        WHERE id=? AND user_id=? AND source='adaptive'
    """, (task_id, user_id)).fetchone()
    if found:
        conn.execute("""
            INSERT INTO adaptive_review_time_locks(task_id,user_id,locked_at)
            VALUES(?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
              user_id=excluded.user_id,locked_at=excluded.locked_at
        """, (task_id, user_id, local_now().isoformat(timespec="seconds")))


def has_manual_time(conn, task_id, user_id):
    ensure_review_schedule_schema(conn)
    return bool(conn.execute("""
        SELECT 1 FROM adaptive_review_time_locks
        WHERE task_id=? AND user_id=?
    """, (task_id, user_id)).fetchone())


def next_review_slot(conn, user_id, duration, preferred_time,
                     exclude_task_id=None, current=None):
    """Search free daily slots after the current time; never overlap lessons.

    Start with the user's preferred clock time, then shift by 15 minutes
    during daytime/evening (08:00-22:00), for at most 30 days.
    """
    current = current or local_now()
    try:
        hh, mm = [int(value) for value in preferred_time.split(":")]
        if not (0 <= hh < 24 and 0 <= mm < 60):
            raise ValueError()
    except (ValueError, AttributeError):
        hh, mm = 19, 0
    occupied = []
    for task in conn.execute("""
        SELECT id,study_at,duration FROM study_tasks
        WHERE user_id=? AND done=0
    """, (user_id,)):
        if exclude_task_id is not None and task["id"] == exclude_task_id:
            continue
        try:
            start = datetime.fromisoformat(task["study_at"])
            length = int(task["duration"])
            if start.tzinfo or length <= 0:
                continue
            occupied.append((start, start + timedelta(minutes=length)))
        except (ValueError, TypeError):
            continue

    # A preferred early/late time can be unsuitable; prefer feasible hours.
    duration = max(15, min(int(duration), 120))
    for day_offset in range(30):
        day = (current + timedelta(days=day_offset)).date()
        if day.weekday() == 6:  # Sunday is a rest day for automatic study
            continue
        first = datetime.combine(day, datetime.min.time()).replace(
            hour=hh, minute=mm)
        last = datetime.combine(day, datetime.min.time()).replace(hour=22)
        # Check the nearest available 15-minute slots to the preferred
        # time (19:45 before 08:00 when the 19:00-19:45 lesson is occupied).
        # When equally close, prefer after the requested time.
        options = []
        scan = datetime.combine(day, datetime.min.time()).replace(hour=8)
        while scan + timedelta(minutes=duration) <= last:
            options.append(scan)
            scan += timedelta(minutes=15)
        if first not in options:
            options.append(first)
        options.sort(key=lambda candidate: (
            abs((candidate-first).total_seconds()),
            candidate < first,
            candidate
        ))
        for candidate in options:
            finish = candidate + timedelta(minutes=duration)
            if candidate.hour < 8 or finish > last:
                continue
            if candidate <= current + timedelta(minutes=20):
                continue
            if not any(candidate < end and finish > start
                       for start, end in occupied):
                return candidate.isoformat(timespec="minutes")
    raise ValueError("Không tìm được khung giờ ôn trống trong 30 ngày tới.")
