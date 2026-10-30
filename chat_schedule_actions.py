"""Explicit, source-of-truth rescheduling inside the Web floating Chat AI.

All reads are per owning student and conversation subject. Never interpret a
model sentence as permission to mutate a timetable. Preview holds a short-lived
proposal in the signed Flask session and confirmation rechecks all schedules
inside a write transaction. No Gemini calls are made.
"""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request, session
from adaptive_review_schedule import local_now
from study_schedule_conflicts import _interval, _next_free_slot, find_study_conflicts

chat_schedule_bp = Blueprint("chat_schedule", __name__)
DATETIME_LOCAL = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
MAX_VISIBLE_TASKS = 80


class ScheduleProblem(Exception):
    def __init__(self, message, status=400, suggestion=""):
        self.message, self.status, self.suggestion = message, status, suggestion


def _project():
    import sys
    from flask import current_app
    return sys.modules[current_app.import_name]


def _scope(conn, uid, conversation_id):
    try:
        if isinstance(conversation_id, bool):
            raise ValueError()
        conversation_id = int(conversation_id)
        if conversation_id <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        raise ScheduleProblem("Chọn một môn học trước khi xem lịch.", 400)
    row = conn.execute("""
        SELECT c.id, c.subject_id, s.name
        FROM chat_conversations c
        JOIN subjects s ON s.id=c.subject_id AND s.user_id=c.user_id
        WHERE c.id=? AND c.user_id=?
    """, (conversation_id, uid)).fetchone()
    if not row:
        raise ScheduleProblem("Không tìm thấy cuộc trò chuyện của môn này.", 404)
    return row


def _tasks(conn, uid):
    from course_schedule_sync import ensure_session_schedule_schema
    ensure_session_schedule_schema(conn)
    return conn.execute("""
        SELECT id,subject_id,title,study_at,duration,done,source,
               roadmap_session_id
        FROM study_tasks WHERE user_id=?
        ORDER BY study_at ASC, id ASC
    """, (uid,)).fetchall()


def _snapshot(rows):
    values = [[r["id"], r["subject_id"], r["study_at"], r["duration"],
               r["done"], r["source"], r["roadmap_session_id"]] for r in rows]
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _choice(rows, task_id, subject_id):
    try:
        if isinstance(task_id, bool):
            raise ValueError()
        task_id = int(task_id)
    except (ValueError, TypeError):
        raise ScheduleProblem("Buổi học không hợp lệ.", 400)
    task = next((row for row in rows if row["id"] == task_id
                 and row["subject_id"] == subject_id), None)
    if not task:
        raise ScheduleProblem("Buổi học không thuộc môn đã chọn.", 404)
    if task["done"]:
        raise ScheduleProblem("Buổi học đã hoàn thành; không đổi lịch đã học.", 409)
    return task


def _datetime(text):
    if not isinstance(text, str) or not DATETIME_LOCAL.fullmatch(text):
        raise ScheduleProblem("Hãy chọn ngày và giờ hợp lệ.", 400)
    try:
        date = datetime.fromisoformat(text)
        if date.tzinfo or date <= local_now():
            raise ValueError()
    except ValueError:
        raise ScheduleProblem("Giờ học mới phải nằm trong tương lai.", 400)
    return date


def _conflicts(rows, moving_id, start, duration):
    end = start + timedelta(minutes=duration)
    clashing, busy = [], []
    for row in rows:
        if row["id"] == moving_id:
            continue
        span = _interval(row)
        if not span:
            continue
        other_start, other_end = span
        busy.append(span)
        if start < other_end and other_start < end:
            clashing.append({"id": row["id"], "title": row["title"],
                             "study_at": row["study_at"]})
    suggestion = _next_free_slot(start, timedelta(minutes=duration), busy)
    return clashing, suggestion


def _validate_limits(conn, uid, task, start, rows):
    # Preserve chapter order when editing a roadmap session. The normal
    # Study Plan editor is deliberately more flexible; this AI-facing helper
    # should not recommend silently reversing a verified roadmap.
    order = task["roadmap_session_id"]
    if task["source"] == "roadmap" and order is not None:
        for row in rows:
            if row["id"] == task["id"] or row["subject_id"] != task["subject_id"]:
                continue
            if row["source"] != "roadmap" or row["roadmap_session_id"] is None:
                continue
            span = _interval(row)
            if not span:
                continue
            if row["roadmap_session_id"] < order and start < span[1]:
                raise ScheduleProblem("Giờ mới phải sau buổi trước trong lộ trình.", 409)
            if row["roadmap_session_id"] > order and start + timedelta(
                    minutes=int(task["duration"])) > span[0]:
                raise ScheduleProblem("Giờ mới không được vượt qua buổi sau trong lộ trình.", 409)
        deadline = conn.execute("""
            SELECT MIN(due_at) AS due FROM reminders
            WHERE user_id=? AND subject_id=? AND done=0
              AND due_at IS NOT NULL AND due_at != ''
        """, (uid, task["subject_id"])).fetchone()
        if deadline and deadline["due"]:
            try:
                due = datetime.fromisoformat(deadline["due"])
                if due.tzinfo is None and start + timedelta(
                        minutes=int(task["duration"])) > due:
                    raise ScheduleProblem("Giờ mới vượt hạn hoàn thành của môn học.", 409)
            except ValueError:
                pass


def _user():
    uid = session.get("user_id")
    if not uid:
        raise ScheduleProblem("Phiên đăng nhập đã hết hạn.", 401)
    return uid


def _check_csrf():
    expected = session.get("chat_schedule_csrf", "")
    supplied = request.headers.get("X-CSRF-Token", "")
    if not expected or not secrets.compare_digest(str(supplied), str(expected)):
        raise ScheduleProblem("Phiên xác nhận lịch không hợp lệ. Hãy mở lại lịch trong Chat.", 403)


@chat_schedule_bp.errorhandler(ScheduleProblem)
def _error(exc):
    return jsonify({"error": exc.message, "suggested_at": exc.suggestion}), exc.status


@chat_schedule_bp.route("/api/chat/schedule", methods=["GET"])
def list_schedule():
    uid = _user()
    project = _project()
    conn = project.db()
    try:
        scope = _scope(conn, uid, request.args.get("conversation_id"))
        rows = _tasks(conn, uid)
        conflicts = find_study_conflicts(rows)
        selected = [r for r in rows if r["subject_id"] == scope["subject_id"]
                    and not r["done"]]
        selected.sort(key=lambda r: (not (r["id"] in conflicts), r["study_at"], r["id"]))
        visible = []
        for row in selected[:MAX_VISIBLE_TASKS]:
            conflict = conflicts.get(row["id"], {})
            suggested = conflict.get("suggested_at", "")
            # Don't offer past time slots as new schedule suggestions.
            if suggested:
                try:
                    if datetime.fromisoformat(suggested) <= local_now():
                        suggested = ""
                except ValueError:
                    suggested = ""
            visible.append({
                "id": row["id"], "title": row["title"],
                "study_at": row["study_at"][:16], "duration": row["duration"],
                "source": row["source"],
                "conflict_titles": conflict.get("with_titles", []),
                "suggested_at": suggested
            })
        if not session.get("chat_schedule_csrf"):
            session["chat_schedule_csrf"] = secrets.token_urlsafe(32)
        return jsonify({
            "subject_id": scope["subject_id"],
            "subject_name": scope["name"],
            "tasks": visible,
            "conflict_count": sum(bool(conflicts.get(r["id"])) for r in selected),
            "csrf_token": session["chat_schedule_csrf"],
            "limited": len(selected) > MAX_VISIBLE_TASKS
        })
    finally:
        conn.close()


@chat_schedule_bp.route("/api/chat/schedule/preview", methods=["POST"])
def preview_schedule():
    uid = _user()
    _check_csrf()
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ScheduleProblem("Nội dung yêu cầu không hợp lệ.")
    project = _project()
    conn = project.db()
    try:
        scope = _scope(conn, uid, payload.get("conversation_id"))
        rows = _tasks(conn, uid)
        task = _choice(rows, payload.get("task_id"), scope["subject_id"])
        proposed = _datetime(payload.get("study_at"))
        try:
            old = datetime.fromisoformat(task["study_at"])
        except (TypeError, ValueError):
            raise ScheduleProblem("Giờ học hiện tại không hợp lệ.", 409)
        if proposed == old:
            raise ScheduleProblem("Bạn chưa chọn giờ khác.", 400)
        length = int(task["duration"])
        collisions, suggestion = _conflicts(rows, task["id"], proposed, length)
        session.pop("chat_schedule_proposal", None)
        if collisions:
            titles = ", ".join(str(t["title"])[:70] for t in collisions[:3])
            raise ScheduleProblem("Giờ này trùng với: " + titles + ". Hãy chọn giờ khác.", 409, suggestion)
        _validate_limits(conn, uid, task, proposed, rows)
        nonce = secrets.token_urlsafe(18)
        session["chat_schedule_proposal"] = {
            "nonce": nonce, "uid": uid, "conversation": scope["id"],
            "subject": scope["subject_id"], "task": task["id"],
            "old": task["study_at"], "new": proposed.isoformat(timespec="minutes"),
            "snapshot": _snapshot(rows), "created": local_now().isoformat(timespec="seconds")
        }
        return jsonify({
            "proposal_id": nonce, "task_id": task["id"],
            "title": task["title"], "old_study_at": task["study_at"][:16],
            "new_study_at": proposed.isoformat(timespec="minutes"),
            "duration": length,
            "message": "Chưa lưu lịch. Hãy xác nhận nếu bạn đồng ý giờ mới."
        })
    finally:
        conn.close()


@chat_schedule_bp.route("/api/chat/schedule/confirm", methods=["POST"])
def confirm_schedule():
    uid = _user()
    _check_csrf()
    payload = request.get_json(silent=True) or {}
    proposal = session.pop("chat_schedule_proposal", None)
    if not isinstance(payload, dict) or not proposal or not secrets.compare_digest(
            str(payload.get("proposal_id") or ""), str(proposal.get("nonce") or "")):
        raise ScheduleProblem("Đề xuất đã hết hiệu lực. Hãy xem trước giờ mới lần nữa.", 409)
    if proposal["uid"] != uid:
        raise ScheduleProblem("Đề xuất không thuộc tài khoản này.", 403)
    try:
        created = datetime.fromisoformat(proposal["created"])
        if local_now() - created > timedelta(minutes=15):
            raise ValueError()
    except (ValueError, TypeError):
        raise ScheduleProblem("Đề xuất đã hết hạn; vui lòng kiểm tra lại lịch.", 409)
    project = _project()
    conn = project.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        scope = _scope(conn, uid, payload.get("conversation_id"))
        if scope["id"] != proposal["conversation"] or scope["subject_id"] != proposal["subject"]:
            raise ScheduleProblem("Môn học đã đổi; hãy mở lại lịch.", 409)
        rows = _tasks(conn, uid)
        if _snapshot(rows) != proposal["snapshot"]:
            raise ScheduleProblem("Lịch học đã thay đổi ở nơi khác. Hãy xem lại trước khi lưu.", 409)
        task = _choice(rows, proposal["task"], scope["subject_id"])
        if task["study_at"] != proposal["old"]:
            raise ScheduleProblem("Giờ học đã thay đổi. Hãy xem lại.", 409)
        proposed = _datetime(proposal["new"])
        clashes, _ = _conflicts(rows, task["id"], proposed, int(task["duration"]))
        if clashes:
            raise ScheduleProblem("Giờ đề xuất không còn trống. Hãy xem lại.", 409)
        _validate_limits(conn, uid, task, proposed, rows)
        result = conn.execute("""
            UPDATE study_tasks SET study_at=?
            WHERE id=? AND user_id=? AND subject_id=? AND done=0 AND study_at=?
        """,(proposed.isoformat(timespec="minutes"), task["id"], uid,
             scope["subject_id"], task["study_at"]))
        if result.rowcount != 1:
            raise ScheduleProblem("Buổi học đã được cập nhật ở nơi khác.", 409)
        if task["source"] == "roadmap":
            from adaptive_plan_phase8 import lock_manual_roadmap_time
            lock_manual_roadmap_time(conn, uid, task["id"])
        elif task["source"] == "adaptive":
            from adaptive_review_schedule import lock_adaptive_time
            lock_adaptive_time(conn, task["id"], uid)
        conn.commit()
        return jsonify({
            "success": True, "task_id": task["id"],
            "title": task["title"], "subject_id": scope["subject_id"],
            "old_study_at": task["study_at"][:16],
            "study_at": proposed.isoformat(timespec="minutes"),
            "message": "Đã đổi giờ học theo xác nhận của bạn."
        })
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
