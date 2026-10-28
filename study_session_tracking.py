"""Phase 6.4: accountable study timing for a verified roadmap lesson.

Only foreground heartbeats record activity. A stale heartbeat automatically
pauses after a short bounded interval; leaving a tab open overnight never
adds hours of fictitious study time. The planner remains the source of the
task completion flag, and the roadmap remains the source of lesson content.
"""
from datetime import datetime, timezone

from course_path_learning import PLAN_VERSION, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, session_signature
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema
import json

HEARTBEAT_CAP = 45
STALE_AFTER = 90
ACTIONS = {"start", "pause", "resume", "heartbeat", "finish"}


class StudyTrackingError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.message = message
        self.status = status


def ensure_tracking_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS study_session_tracking (
            task_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'paused'
                CHECK(status IN ('running','paused','completed')),
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            elapsed_seconds INTEGER NOT NULL DEFAULT 0
                CHECK(elapsed_seconds >= 0),
            completed_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(subject_id) REFERENCES subjects(id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_study_session_tracking_owner
        ON study_session_tracking(user_id, subject_id)
    """)


def utcnow():
    return datetime.now(timezone.utc)


def _read_stamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def verified_roadmap_task(project, conn, uid, task_id):
    """Apply the same confirmed-syllabus + saved-session identity constraints as
    the lesson room. No approved tutor files needed for studying/timing itself."""
    user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    if not user or user["role"] != "student":
        raise StudyTrackingError("Chỉ sinh viên được ghi nhận phiên học.", 403)
    ensure_session_schedule_schema(conn)
    task = conn.execute("""
        SELECT t.* FROM study_tasks t
        JOIN subjects s ON s.id=t.subject_id AND s.user_id=t.user_id
        WHERE t.id=? AND t.user_id=? AND t.source='roadmap'
          AND t.roadmap_session_id IS NOT NULL
    """, (task_id, uid)).fetchone()
    if not task:
        raise StudyTrackingError("Không tìm thấy buổi học hợp lệ của bạn.", 404)
    ensure_syllabus_schema(conn)
    ensure_roadmap_schema(conn)
    _, syllabus, _ = _source(project, conn, uid, task["subject_id"])
    fingerprint = syllabus_hash(syllabus) if syllabus else ""
    review = conn.execute("""
        SELECT status,source_hash,units_json FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """, (uid, task["subject_id"])).fetchone()
    roadmap = conn.execute("""
        SELECT source_hash,units_hash,sessions_json FROM course_roadmaps
        WHERE user_id=? AND subject_id=?
    """, (uid, task["subject_id"])).fetchone()
    if not fingerprint or not review or review["status"] != "confirmed" or \
            review["source_hash"] != fingerprint or not roadmap:
        raise StudyTrackingError("Đề cương đã thay đổi hoặc chưa xác nhận; không thể ghi phiên học.")
    try:
        units = json.loads(review["units_json"])
        sessions = json.loads(roadmap["sessions_json"])
        if not isinstance(units, list) or not isinstance(sessions, list):
            raise ValueError("invalid saved data")
        fresh = bool(sessions and all(isinstance(s, dict) for s in sessions)
                     and sessions[0].get("planner_version") == PLAN_VERSION
                     and roadmap["source_hash"] == fingerprint
                     and roadmap["units_hash"] == unit_fingerprint(units))
        item = next((s for s in sessions
                     if s.get("session_id") == task["roadmap_session_id"]), None)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise StudyTrackingError("Lộ trình không hợp lệ; hãy rà soát lại.")
    if not fresh or not item or \
            session_signature(item) != task["roadmap_session_signature"]:
        raise StudyTrackingError("Buổi học đã thay đổi nội dung. Hãy rà soát lộ trình trước khi học.")
    return task


def _project_state(row, task, at):
    if row is None:
        return {"status": "completed" if task["done"] else "idle",
                "elapsed_seconds": 0, "started_at": "",
                "completed_at": task["completed_at"] or ""}
    status = row["status"]
    total = max(0, int(row["elapsed_seconds"] or 0))
    if task["done"]:
        status = "completed"
    elif status == "completed":
        # A student may have explicitly unchecked the old planner task.
        status = "paused"
    elif status == "running":
        last = _read_stamp(row["last_heartbeat_at"])
        gap = max(0, (at - last).total_seconds()) if last else STALE_AFTER + 1
        total += int(min(gap, HEARTBEAT_CAP))
        if gap > STALE_AFTER:
            status = "paused"
    return {"status": status, "elapsed_seconds": total,
            "started_at": row["started_at"],
            "completed_at": (task["completed_at"] or row["completed_at"] or "")
                            if task["done"] else ""}


def read_state(conn, task, uid, at=None):
    at = at or utcnow()
    row = conn.execute("""
        SELECT * FROM study_session_tracking WHERE task_id=? AND user_id=?
    """, (task["id"], uid)).fetchone()
    result = _project_state(row, task, at)
    result.update({"task_id": task["id"], "subject_id": task["subject_id"],
                   "planned_minutes": int(task["duration"] or 45),
                   "done": bool(task["done"])})
    return result


def apply_action(project, conn, task, uid, action, at=None):
    if action not in ACTIONS:
        raise StudyTrackingError("Thao tác phiên học không hợp lệ.", 400)
    at = at or utcnow()
    stamp = at.isoformat(timespec="seconds")
    # Caller begins IMMEDIATE transaction to serialize simultaneous requests.
    old = conn.execute("""
        SELECT * FROM study_session_tracking WHERE task_id=? AND user_id=?
    """, (task["id"], uid)).fetchone()
    current = _project_state(old, task, at)
    state = current["status"]
    if task["done"] or state == "completed":
        raise StudyTrackingError("Buổi này đã hoàn thành. Không tự thay đổi kết quả cũ.")
    if action == "start" and state != "idle":
        raise StudyTrackingError("Buổi đã bắt đầu. Hãy tiếp tục hoặc tạm dừng.")
    if action == "resume" and state != "paused":
        raise StudyTrackingError("Chỉ có thể tiếp tục buổi đã tạm dừng.")
    if action in ("pause", "heartbeat") and state != "running":
        raise StudyTrackingError("Phiên học không đang chạy. Hãy bấm Tiếp tục.")
    if action == "finish" and state == "idle":
        raise StudyTrackingError("Hãy bắt đầu học trước khi hoàn thành.")

    if action == "start":
        conn.execute("""
            INSERT INTO study_session_tracking(task_id,user_id,subject_id,status,
                started_at,last_heartbeat_at,elapsed_seconds,updated_at)
            VALUES(?,?,?,'running',?,?,0,?)
        """, (task["id"], uid, task["subject_id"], stamp, stamp, stamp))
    else:
        seconds = current["elapsed_seconds"]
        new_status = {
            "pause": "paused", "resume": "running",
            "heartbeat": "running", "finish": "completed"
        }[action]
        conn.execute("""
            UPDATE study_session_tracking
            SET status=?,elapsed_seconds=?,last_heartbeat_at=?,updated_at=?,
                completed_at=CASE WHEN ?='completed' THEN ? ELSE completed_at END
            WHERE task_id=? AND user_id=?
        """, (new_status, seconds, stamp, stamp, new_status, stamp,
              task["id"], uid))

    if action == "finish":
        conn.execute("""
            UPDATE study_tasks SET done=1,completed_at=?
            WHERE id=? AND user_id=? AND done=0
        """, (project.now(), task["id"], uid))
        project.recalculate_subject_progress(uid, task["subject_id"], conn)

    updated_task = conn.execute(
        "SELECT * FROM study_tasks WHERE id=? AND user_id=?",
        (task["id"], uid)).fetchone()
    # "at" ensures the response matches the just-committed server clock.
    return read_state(conn, updated_task, uid, at)
