"""Phase 8.3: opt-in, collision-free roadmap rescheduling after adaptive review.

The existing 7.5.3 adaptive task remains untouched. Only a pending roadmap
lesson can be moved, and only after the owning student explicitly confirms a
fresh, checked proposal. Manual tasks, deadlines and completed lessons stay put.
"""
import hashlib
import secrets
from datetime import datetime, timedelta

from adaptive_review_schedule import local_now, next_review_slot
from adaptive_decision_phase8 import decide_next_learning_step


def ensure_adaptive_plan_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adaptive_plan_decisions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          subject_id INTEGER NOT NULL,
          task_id INTEGER NOT NULL,
          action TEXT NOT NULL CHECK(action IN ('accepted','dismissed')),
          old_study_at TEXT NOT NULL,
          proposed_study_at TEXT NOT NULL,
          proposal_key TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(user_id, subject_id, proposal_key),
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
          FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roadmap_manual_time_locks (
          task_id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          locked_at TEXT NOT NULL,
          FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE CASCADE,
          FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)


def lock_manual_roadmap_time(conn, user_id, task_id):
    """A student-set roadmap time must never be silently moved by the Agent."""
    ensure_adaptive_plan_schema(conn)
    owned = conn.execute("""
        SELECT id FROM study_tasks
        WHERE id=? AND user_id=? AND source='roadmap'
    """, (task_id, user_id)).fetchone()
    if owned:
        conn.execute("""
            INSERT INTO roadmap_manual_time_locks(task_id,user_id,locked_at)
            VALUES(?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET locked_at=excluded.locked_at
        """, (task_id, user_id, local_now().isoformat(timespec="seconds")))


def is_manual_roadmap_time(conn, user_id, task_id):
    ensure_adaptive_plan_schema(conn)
    return bool(conn.execute("""
        SELECT 1 FROM roadmap_manual_time_locks
        WHERE task_id=? AND user_id=?
    """, (task_id, user_id)).fetchone())


def _parse_time(value):
    try:
        result = datetime.fromisoformat(str(value))
        return result if result.tzinfo is None else None
    except (TypeError, ValueError):
        return None


def proposal_for_subject(conn, user_id, subject_id, current=None):
    """Return a preview (no mutation) or None when rescheduling is not warranted."""
    decision = decide_next_learning_step(conn, user_id, subject_id, current)
    if not decision or decision["kind"] not in ("review", "verify"):
        return None
    review = decision["review_task"]
    if not review:
        return None
    current = current or local_now()
    review_at = _parse_time(review["study_at"])
    if not review_at or review_at <= current:
        return None
    try:
        review_duration = int(review["duration"])
    except (ValueError, TypeError):
        return None
    if review_duration < 15 or review_duration > 240:
        return None
    review_end = review_at + timedelta(minutes=review_duration)

    # Only the very next upcoming roadmap lesson, not a manually created task.
    row = conn.execute("""
        SELECT id,title,study_at,duration FROM study_tasks
        WHERE user_id=? AND subject_id=?
          AND source='roadmap' AND done=0 AND study_at>=?
        ORDER BY study_at ASC,id ASC LIMIT 1
    """, (user_id, subject_id, current.isoformat(timespec="minutes"))).fetchone()
    if not row:
        return None
    if is_manual_roadmap_time(conn, user_id, row["id"]):
        return None  # Respect any student's previous manual rescheduling.
    old_at = _parse_time(row["study_at"])
    if not old_at or old_at >= review_end:
        return None
    try:
        duration = int(row["duration"])
    except (TypeError, ValueError):
        return None
    # next_review_slot is explicitly capped at 120 minutes; never shorten a lesson.
    if not 15 <= duration <= 120:
        return None
    try:
        proposed = next_review_slot(
            conn, user_id, duration, old_at.strftime("%H:%M"),
            exclude_task_id=row["id"], current=review_end
        )
    except ValueError:
        return None
    proposed_at = _parse_time(proposed)
    if not proposed_at or proposed_at <= old_at or proposed_at < review_end:
        return None
    # F2: never put a study lesson after its subject's next deadline or
    # overtake the following roadmap lesson (including an edited next lesson).
    proposed_end = proposed_at + timedelta(minutes=duration)
    from course_schedule_sync import ensure_session_schedule_schema
    ensure_session_schedule_schema(conn)
    selected = conn.execute("""
        SELECT roadmap_session_id FROM study_tasks
        WHERE id=? AND user_id=? AND subject_id=?
    """, (row["id"], user_id, subject_id)).fetchone()
    number = selected["roadmap_session_id"] if selected else None
    if number is not None:
        # A previous session in roadmap order cannot be scheduled after us.
        previous_rows = conn.execute("""
            SELECT study_at,duration FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND done=0 AND roadmap_session_id<? AND id<>?
        """, (user_id, subject_id, number, row["id"])).fetchall()
        next_rows = conn.execute("""
            SELECT study_at FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND done=0 AND roadmap_session_id>? AND id<>?
        """, (user_id, subject_id, number, row["id"])).fetchall()
    else:
        # Legacy lesson without a session index: preserve the existing
        # chronological order of other unfinished roadmap lessons.
        previous_rows = []
        next_rows = conn.execute("""
            SELECT study_at FROM study_tasks
            WHERE user_id=? AND subject_id=? AND source='roadmap'
              AND done=0 AND study_at>? AND id<>?
        """, (row["study_at"], user_id, subject_id, row["id"])).fetchall()
    for item in previous_rows:
        previous_at = _parse_time(item["study_at"])
        try:
            previous_length = int(item["duration"])
        except (ValueError, TypeError):
            return None
        if not previous_at or previous_length <= 0:
            return None
        if proposed_at < previous_at + timedelta(minutes=previous_length):
            return None
    for item in next_rows:
        next_at = _parse_time(item["study_at"])
        if not next_at or proposed_end > next_at:
            return None
    for reminder in conn.execute("""
        SELECT due_at FROM reminders
        WHERE user_id=? AND subject_id=? AND done=0 AND due_at!=''
    """, (user_id, subject_id)):
        due = _parse_time(reminder["due_at"])
        if due and proposed_end > due:
            return None
    identity = (
        f"phase8|{user_id}|{subject_id}|{row['id']}|{row['study_at']}|"
        f"{proposed}|{review['id']}|{review['study_at']}|{review_duration}"
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    ensure_adaptive_plan_schema(conn)
    previous = conn.execute("""
        SELECT action FROM adaptive_plan_decisions
        WHERE user_id=? AND subject_id=? AND proposal_key=?
    """, (user_id, subject_id, digest)).fetchone()
    return {
        "task_id": row["id"], "title": row["title"],
        "old_at": row["study_at"], "new_at": proposed,
        "old_text": old_at.strftime("%d/%m/%Y %H:%M"),
        "new_text": proposed_at.strftime("%d/%m/%Y %H:%M"),
        "review_text": review_at.strftime("%d/%m/%Y %H:%M"),
        "proposal_key": digest, "dismissed": bool(previous and previous["action"]=="dismissed"),
    }


def apply_student_choice(conn, user_id, subject_id, submitted_key, choice):
    """Atomic revalidation and single-task update; raises ValueError on stale data."""
    if choice not in ("accept", "dismiss"):
        raise ValueError("Lựa chọn không hợp lệ.")
    conn.execute("BEGIN IMMEDIATE")
    try:
        proposal = proposal_for_subject(conn, user_id, subject_id)
        if not proposal or not secrets.compare_digest(
            str(submitted_key or ""), proposal["proposal_key"]
        ):
            raise ValueError("Đề xuất đã thay đổi. Hãy tải lại trang để xem giờ mới.")
        if proposal["dismissed"]:
            raise ValueError("Bạn đã bỏ qua đề xuất này.")
        if choice == "accept":
            result = conn.execute("""
                UPDATE study_tasks SET study_at=?
                WHERE id=? AND user_id=? AND subject_id=?
                  AND source='roadmap' AND done=0 AND study_at=?
            """, (proposal["new_at"], proposal["task_id"],
                  user_id, subject_id, proposal["old_at"]))
            if result.rowcount != 1:
                raise ValueError("Buổi học đã thay đổi. Không có lịch nào được ghi đè.")
        conn.execute("""
            INSERT INTO adaptive_plan_decisions(
              user_id,subject_id,task_id,action,old_study_at,
              proposed_study_at,proposal_key,created_at
            ) VALUES(?,?,?,?,?,?,?,?)
        """, (
            user_id,subject_id,proposal["task_id"],
            "accepted" if choice=="accept" else "dismissed",
            proposal["old_at"],proposal["new_at"],proposal["proposal_key"],
            local_now().isoformat(timespec="seconds")
        ))
        conn.commit()
        return proposal
    except Exception:
        conn.rollback()
        raise
