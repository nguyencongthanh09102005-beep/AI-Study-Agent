"""Mobile roadmap and verified study-room JSON endpoints.

Reuse the same syllabus, roadmap signatures and timer state machine as Web.
Never trust lesson text, material approval, completion time or ownership from
the phone. All saved plan edits remain server-authoritative.
"""
import json
import secrets
import sys

from flask import Blueprint, current_app, jsonify, request, session
from course_path_routes import ensure_roadmap_schema
from course_path_learning import PLAN_VERSION, unit_fingerprint
from course_schedule_sync import ensure_session_schedule_schema, session_signature
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema
from study_session_tracking import (
    StudyTrackingError, ensure_tracking_schema,
    verified_roadmap_task, read_state, apply_action,
)
from chapter_material_routes import (
    ensure_chapter_material_schema, approved_document_rows,
    chapter_key, official_syllabus,
)

mobile_learning_bp = Blueprint("mobile_learning", __name__)


def _project():
    return sys.modules[current_app.import_name]


def _student(project):
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "Hãy đăng nhập lại."}), 401)
    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    finally:
        conn.close()
    if not user or user["role"] != "student":
        return None, (jsonify({"error": "Chỉ sinh viên có quyền truy cập."}), 403)
    return uid, None


def _verified_course(conn, project, uid, subject_id):
    subject = conn.execute(
        "SELECT id,name,code FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid),
    ).fetchone()
    if not subject:
        return None, None, None, "Không tìm thấy môn học."
    ensure_syllabus_schema(conn)
    ensure_roadmap_schema(conn)
    kind, text, syllabus_name = _source(project, conn, uid, subject_id)
    fingerprint = syllabus_hash(text) if text else ""
    review = conn.execute(
        "SELECT status,source_hash,units_json FROM syllabus_reviews "
        "WHERE user_id=? AND subject_id=?", (uid, subject_id),
    ).fetchone()
    plan = conn.execute(
        "SELECT source_hash,units_hash,sessions_json FROM course_roadmaps "
        "WHERE user_id=? AND subject_id=?", (uid, subject_id),
    ).fetchone()
    if not review or review["status"] != "confirmed" or not fingerprint or (
        review["source_hash"] != fingerprint
    ):
        return dict(subject), None, None, "Đề cương chưa được xác nhận hoặc đã thay đổi."
    try:
        units = json.loads(review["units_json"])
        sessions = json.loads(plan["sessions_json"]) if plan else []
        if not isinstance(units, list) or not isinstance(sessions, list):
            raise ValueError("invalid syllabus or sessions")
        fresh = bool(plan and sessions and
                     sessions[0].get("planner_version") == PLAN_VERSION and
                     plan["source_hash"] == fingerprint and
                     plan["units_hash"] == unit_fingerprint(units))
    except (ValueError, TypeError, KeyError, AttributeError):
        return dict(subject), None, None, "Đề cương hoặc lộ trình không đọc được."
    if not fresh:
        return dict(subject), units, None, "Lộ trình chưa tạo hoặc đã lỗi thời."
    return dict(subject), units, sessions, ""


def _safe_items(lesson):
    # Never expose raw stale material associations or unseen student files.
    keys = ("session_id", "unit_id", "title", "duration", "chapter",
            "topics", "objectives", "activities", "clo_refs", "date", "time")
    return {key: lesson[key] for key in keys if key in lesson}


@mobile_learning_bp.route("/api/mobile/subjects/<int:subject_id>/roadmap")
def mobile_roadmap(subject_id):
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    conn = project.db()
    try:
        subject, units, sessions, notice = _verified_course(
            conn, project, uid, subject_id,
        )
        if subject is None:
            return jsonify({"error": notice}), 404
        result = {"subject": subject, "ready": bool(sessions),
                  "notice": notice, "chapters": [], "sessions": []}
        if units:
            result["chapters"] = [
                {"number": i+1, "title": str(unit.get("title") or ("Chương " + str(i+1))),
                 "topics": unit.get("topics") or []}
                for i,unit in enumerate(units) if isinstance(unit, dict)
            ]
        if sessions:
            ensure_session_schedule_schema(conn)
            tasks = conn.execute(
                "SELECT id,roadmap_session_id,roadmap_session_signature,study_at,done "
                "FROM study_tasks WHERE user_id=? AND subject_id=? "
                "AND source='roadmap' AND roadmap_session_id IS NOT NULL",
                (uid, subject_id)
            ).fetchall()
            indexed = {str(row["roadmap_session_id"]): dict(row) for row in tasks}
            for lesson in sessions:
                if not isinstance(lesson, dict):
                    continue
                row = indexed.get(str(lesson.get("session_id")))
                valid = bool(row and row["roadmap_session_signature"] == session_signature(lesson))
                item = _safe_items(lesson)
                item["scheduled_task_id"] = row["id"] if valid else None
                item["study_at"] = row["study_at"] if valid else ""
                item["done"] = bool(row["done"]) if valid else False
                result["sessions"].append(item)
        return jsonify(result)
    finally:
        conn.close()


@mobile_learning_bp.route("/api/mobile/study-room/<int:task_id>")
def mobile_study_room(task_id):
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    conn = project.db()
    try:
        ensure_tracking_schema(conn)
        task = verified_roadmap_task(project, conn, uid, task_id)
        subject, units, sessions, notice = _verified_course(
            conn, project, uid, task["subject_id"]
        )
        if not sessions:
            return jsonify({"error": notice or "Buổi học đã thay đổi."}), 409
        lesson = next((row for row in sessions
                       if row.get("session_id") == task["roadmap_session_id"]), None)
        if not lesson or session_signature(lesson) != task["roadmap_session_signature"]:
            return jsonify({"error": "Nội dung buổi học đã thay đổi."}), 409
        kind, text, _ = _source(project, conn, uid, task["subject_id"])
        sources = []
        if kind == "shared" and units:
            shared = project.ensure_shared_subject_for_user_subject(
                conn, uid, task["subject_id"],
            )
            if shared and shared["admin_managed"]:
                _, official_hash, _ = official_syllabus(conn, shared["id"])
                if official_hash == syllabus_hash(text):
                    index = lesson.get("unit_id")
                    if isinstance(index, int) and 1 <= index <= len(units):
                        ensure_chapter_material_schema(conn)
                        key = chapter_key(units[index-1].get("evidence", ""))
                        sources = [
                            {"id": r["id"], "name": r["original_name"]}
                            for r in approved_document_rows(
                                conn, shared["id"], key, official_hash
                            )
                        ]
        csrf = session.get("study_session_csrf")
        if not csrf:
            csrf = secrets.token_hex(24)
            session["study_session_csrf"] = csrf
        return jsonify({
            "subject": subject, "task": {
                "id": task["id"], "title": task["title"],
                "study_at": task["study_at"], "duration": task["duration"],
                "subject_id": task["subject_id"],
            },
            "lesson": _safe_items(lesson),
            "sources": sources,
            "timer": read_state(conn, task, uid),
            "timer_csrf": csrf,
        })
    except StudyTrackingError as exc:
        return jsonify({"error": exc.message}), exc.status
    finally:
        conn.close()


@mobile_learning_bp.route("/api/mobile/study-room/<int:task_id>/timer",
                          methods=["POST"])
def mobile_study_timer(task_id):
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    token = session.get("study_session_csrf", "")
    if not token or not secrets.compare_digest(
        token, request.headers.get("X-Study-CSRF", "")
    ):
        return jsonify({"error": "Phiên xác nhận hết hạn. Mở lại buổi học."}), 403
    body = request.get_json(silent=True)
    action = body.get("action") if isinstance(body, dict) else None
    if action not in ("start", "pause", "resume", "finish", "heartbeat"):
        return jsonify({"error": "Thao tác phiên học không hợp lệ."}), 400
    conn = project.db()
    try:
        ensure_tracking_schema(conn)
        task = verified_roadmap_task(project, conn, uid, task_id)
        conn.execute("BEGIN IMMEDIATE")
        locked = conn.execute(
            "SELECT t.* FROM study_tasks t JOIN subjects s "
            "ON s.id=t.subject_id AND s.user_id=t.user_id "
            "WHERE t.id=? AND t.user_id=? AND t.source='roadmap' "
            "AND t.roadmap_session_id=? AND t.roadmap_session_signature=?",
            (task_id, uid, task["roadmap_session_id"], task["roadmap_session_signature"]),
        ).fetchone()
        if not locked:
            conn.rollback()
            return jsonify({"error": "Buổi học đã được cập nhật."}), 409
        result = apply_action(project, conn, locked, uid, action)
        conn.commit()
        return jsonify(result)
    except StudyTrackingError as exc:
        conn.rollback()
        return jsonify({"error": exc.message}), exc.status
    finally:
        conn.close()


def _quiz_token():
    token = session.get("session_quiz_csrf")
    if not token:
        token = secrets.token_hex(24)
        session["session_quiz_csrf"] = token
    return token


def _valid_quiz_csrf():
    expected = session.get("session_quiz_csrf") or ""
    supplied = request.headers.get("X-Quiz-CSRF") or ""
    return bool(expected and secrets.compare_digest(expected, supplied))


@mobile_learning_bp.route("/api/mobile/study-room/<int:task_id>/quiz-status")
def mobile_session_quiz_status(task_id):
    """Never leak question payloads for pending or locked Quiz."""
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    conn = project.db()
    try:
        from chapter_chat_context import LessonContextError
        from study_session_chat_context import verified_study_session
        from study_session_quiz_runtime import per_lesson_quiz_status
        verified_study_session(project, conn, uid, task_id)
        data = per_lesson_quiz_status(conn, project, uid, task_id)
        data["quiz_csrf"] = _quiz_token()
        return jsonify(data)
    except LessonContextError as exc:
        return jsonify({"error": exc.message}), exc.status
    finally:
        conn.close()


@mobile_learning_bp.route("/api/mobile/subjects/<int:subject_id>/quiz-preparation",
                          methods=["GET", "POST"])
def mobile_quiz_preparation(subject_id):
    """Read real preparation progress, enqueue/resume or pause via opt-in."""
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    conn = project.db()
    try:
        from chapter_chat_context import LessonContextError
        from study_session_quiz_runtime import (
            ensure_quiz_runtime_schema, preparation_status
        )
        course = conn.execute(
            "SELECT id FROM subjects WHERE user_id=? AND id=?",
            (uid,subject_id)
        ).fetchone()
        if not course:
            return jsonify({"error":"Môn học không thuộc tài khoản."}),404
        ensure_quiz_runtime_schema(conn)
        if request.method == "POST":
            if not _valid_quiz_csrf():
                return jsonify({"error":"Phiên xác nhận Quiz đã hết hạn."}),403
            body = request.get_json(silent=True) or {}
            action = body.get("action")
            if action not in ("start","pause"):
                return jsonify({"error":"Thao tác chuẩn bị Quiz không hợp lệ."}),400
            if action == "start":
                from quiz_preparation_jobs import enqueue, start_local_worker
                state = enqueue(conn, project, uid, subject_id)
                start_local_worker(project)
            else:
                from quiz_preparation_jobs import pause
                state = pause(conn, uid, subject_id)
            return jsonify({"state":state,"accepted":True})
        items = preparation_status(conn,project,uid,subject_id)
        from quiz_preparation_jobs import status as job_status
        ready = sum(1 for item in items if item.get("status")=="ready")
        return jsonify({
            "total":len(items), "ready":ready, "items":items,
            "done":bool(items) and ready==len(items),
            "job":job_status(conn,uid,subject_id),
            "quiz_csrf":_quiz_token()
        })
    except LessonContextError as exc:
        conn.rollback()
        return jsonify({"error":exc.message}),exc.status
    finally:
        conn.close()


@mobile_learning_bp.route("/api/mobile/study-room/<int:task_id>/quiz-start",
                          methods=["POST"])
def mobile_start_session_quiz(task_id):
    """Only start a prepared Quiz in the current server-approved time window."""
    project = _project()
    uid, error = _student(project)
    if error:
        return error
    if not _valid_quiz_csrf():
        return jsonify({"error":"Phiên xác nhận Quiz đã hết hạn."}),403
    conn = project.db()
    try:
        from chapter_chat_context import LessonContextError
        from study_session_chat_context import verified_study_session
        from study_session_quiz_runtime import (
            per_lesson_quiz_status,start_quiz
        )
        verified_study_session(project,conn,uid,task_id)
        info = per_lesson_quiz_status(conn,project,uid,task_id)
        quiz_id = info.get("quiz_id")
        if not quiz_id or info.get("state") in ("blocked","unprepared"):
            return jsonify({"error":info.get("reason") or "Quiz chưa được chuẩn bị."}),409
        # No client-supplied quiz id is accepted. The current roadmap binding
        # and saved, signed prepared Quiz determine what can be opened.
        start_quiz(conn,project,uid,quiz_id)
        conn.commit()
        return jsonify({"quiz_id":quiz_id,"ready":True})
    except LessonContextError as exc:
        conn.rollback()
        return jsonify({"error":exc.message}),exc.status
    finally:
        conn.close()


@mobile_learning_bp.route("/api/mobile/quizzes/<int:quiz_id>/review")
def mobile_review_quiz(quiz_id):
    """Answer key unlocks only after a real owner-scoped submitted attempt."""
    project = _project()
    uid,error = _student(project)
    if error:
        return error
    conn = project.db()
    try:
        from study_session_quiz_runtime import quiz_access
        row = conn.execute("SELECT payload FROM quizzes WHERE user_id=? AND id=?",
                           (uid,quiz_id)).fetchone()
        if not row:
            return jsonify({"error":"Không tìm thấy Quiz."}),404
        gate = quiz_access(conn,project,uid,quiz_id)
        if gate.get("linked") and not gate.get("allowed"):
            return jsonify({"error":gate.get("reason","Nguồn Quiz không còn hợp lệ.")}),409
        attempt = conn.execute(
            "SELECT id,score,correct_count,total_questions,answers_json,created_at "
            "FROM quiz_attempts WHERE user_id=? AND quiz_id=? "
            "ORDER BY id DESC LIMIT 1", (uid,quiz_id)
        ).fetchone()
        if not attempt:
            return jsonify({"error":"Chỉ được xem đáp án sau khi nộp bài."}),403
        questions = json.loads(row["payload"] or "[]")
        return jsonify({
            "attempt":dict(attempt),
            "correct_answers":[
                int(q.get("answer")) if str(q.get("answer","")).isdigit() else -1
                for q in questions
            ],
            "explanations":[str(q.get("explanation") or "") for q in questions],
        })
    finally:
        conn.close()
