"""Phase 7.2-7.4 Web routes: bounded preparation and explicit timed Quiz start."""
import secrets
import sys

from flask import (Blueprint, current_app, jsonify, redirect, request,
                   session, url_for)

from chapter_chat_context import LessonContextError
from study_session_quiz_runtime import (
    ensure_quiz_runtime_schema, ordered_tasks, preparation_status,
    prepare_step, start_quiz,
)

session_quiz_bp = Blueprint("session_quiz", __name__)


def _auth(project, conn, uid, subject_id):
    user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    if not user or user["role"] != "student":
        raise LessonContextError("Chỉ sinh viên được chuẩn bị Quiz.", 403)
    course = conn.execute(
        "SELECT id FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not course:
        raise LessonContextError("Môn học không thuộc tài khoản.", 404)


def _csrf():
    expected = session.get("session_quiz_csrf") or ""
    supplied = request.headers.get("X-Quiz-CSRF", "") or \
               request.form.get("csrf_token", "")
    return bool(expected and secrets.compare_digest(expected, supplied))


@session_quiz_bp.route("/api/subjects/<int:subject_id>/quiz-preparation",
                       methods=["GET"])
def status(subject_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập."}), 401
    conn = project.db()
    try:
        _auth(project, conn, uid, subject_id)
        ensure_quiz_runtime_schema(conn)
        items = preparation_status(conn, project, uid, subject_id)
        from quiz_preparation_jobs import status as job_status
        ready = sum(1 for item in items if item["status"] == "ready")
        return jsonify({"total": len(items), "ready": ready, "items": items,
                        "done": bool(items) and ready == len(items),
                        "job": job_status(conn,uid,subject_id)})
    except LessonContextError as err:
        return jsonify({"error": err.message}), err.status
    finally:
        conn.close()


@session_quiz_bp.route("/api/subjects/<int:subject_id>/quiz-preparation/next",
                       methods=["POST"])
def next_step(subject_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập."}), 401
    if not _csrf():
        return jsonify({"error": "Phiên xác nhận không hợp lệ."}), 403
    conn = project.db()
    try:
        _auth(project, conn, uid, subject_id)
        ensure_quiz_runtime_schema(conn)
        result = prepare_step(project, conn, uid, subject_id)
        return jsonify(result)
    except LessonContextError as err:
        conn.rollback()
        return jsonify({"error": err.message}), err.status
    finally:
        conn.close()


@session_quiz_bp.route(
    "/api/subjects/<int:subject_id>/quiz-preparation/background",
    methods=["POST"])
def start_background(subject_id):
    """Queue a durable job; never call Gemini inside this HTTP request."""
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập."}), 401
    if not _csrf():
        return jsonify({"error": "Phiên xác nhận không hợp lệ."}), 403
    conn = project.db()
    try:
        _auth(project, conn, uid, subject_id)
        from quiz_preparation_jobs import enqueue, start_local_worker
        state = enqueue(conn, project, uid, subject_id)
        # Supported for persistent Flask processes (local python app.py).
        # Production/serverless requires a dedicated persistent worker.
        start_local_worker(project)
        return jsonify({"state":state,"accepted":True})
    except LessonContextError as err:
        conn.rollback()
        return jsonify({"error": err.message}), err.status
    finally:
        conn.close()


@session_quiz_bp.route(
    "/api/subjects/<int:subject_id>/quiz-preparation/background/pause",
    methods=["POST"])
def pause_background(subject_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập."}), 401
    if not _csrf():
        return jsonify({"error": "Phiên xác nhận không hợp lệ."}), 403
    conn = project.db()
    try:
        _auth(project, conn, uid, subject_id)
        from quiz_preparation_jobs import pause
        state=pause(conn,uid,subject_id)
        return jsonify({"state":state})
    except LessonContextError as err:
        return jsonify({"error":err.message}),err.status
    finally:
        conn.close()


@session_quiz_bp.route("/quiz/<int:quiz_id>/start-session", methods=["POST"])
def open_quiz(quiz_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="login"))
    if not _csrf():
        return "Phiên xác nhận không hợp lệ. Hãy tải lại trang Quiz.", 403
    conn = project.db()
    try:
        ensure_quiz_runtime_schema(conn)
        link = conn.execute("""
            SELECT task_id FROM quiz_session_links
            WHERE quiz_id=? AND user_id=?
        """, (quiz_id, uid)).fetchone()
        if not link or not link["task_id"]:
            return "Không tìm thấy bài kiểm tra của buổi học.", 404
        try:
            start_quiz(conn, project, uid, quiz_id)
        except LessonContextError as err:
            conn.rollback()
            return err.message, err.status
        conn.commit()
        return redirect(url_for("quiz", task_id=link["task_id"]), code=303)
    finally:
        conn.close()
