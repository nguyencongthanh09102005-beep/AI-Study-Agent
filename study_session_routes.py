"""Phase 6.3.1: read-only, per-roadmap-lesson learning space.

Access is per student and subject. Viewing does not mark a task started/done,
alter progress, call an LLM, or generate a quiz.
"""
import json
import secrets
import sys
from datetime import datetime, timedelta
from flask import Blueprint, current_app, render_template, session, redirect, url_for, jsonify, request

from course_path_learning import PLAN_VERSION, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, session_signature
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema
from chapter_material_routes import (
    approved_document_rows, chapter_key, ensure_chapter_material_schema,
    official_syllabus,
)
from chapter_tutor import prepared_sources
from study_session_tracking import (ensure_tracking_schema, verified_roadmap_task,
                                    read_state, apply_action, StudyTrackingError)
from study_session_quiz import get_session_quiz_context, public_session_quiz_context
from chapter_chat_context import LessonContextError

study_session_bp = Blueprint("study_session", __name__)


def _unavailable(subject, message):
    return render_template("study_session_unavailable.html",
                           page="study_plan", subject=subject, message=message), 409


def _schedule_display(value, minutes):
    try:
        start = datetime.fromisoformat(value)
        end = start + timedelta(minutes=int(minutes))
        return start.strftime("%d/%m/%Y · %H:%M"), end.strftime("%H:%M")
    except (TypeError, ValueError, OverflowError):
        return value or "", ""


@study_session_bp.route("/study-plan/tasks/<int:task_id>/learn")
def learning_session(task_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="login"))
    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["role"] != "student":
            return "Chỉ sinh viên có quyền mở Không gian học tập.", 403

        ensure_session_schedule_schema(conn)
        task = conn.execute("""
            SELECT t.*,s.name AS subject_name,s.code AS subject_code,
                   s.personal_syllabus_document_id
            FROM study_tasks t
            JOIN subjects s ON s.id=t.subject_id AND s.user_id=t.user_id
            WHERE t.id=? AND t.user_id=? AND t.source='roadmap'
              AND t.roadmap_session_id IS NOT NULL
        """, (task_id, uid)).fetchone()
        if not task:
            return "Không tìm thấy buổi học từ lộ trình của bạn.", 404

        subject = {"id": task["subject_id"], "name": task["subject_name"],
                   "code": task["subject_code"]}
        ensure_syllabus_schema(conn)
        ensure_roadmap_schema(conn)
        kind, syllabus_text, syllabus_name = _source(
            project, conn, uid, task["subject_id"]
        )
        fingerprint = syllabus_hash(syllabus_text) if syllabus_text else ""
        review = conn.execute("""
            SELECT status,source_hash,units_json FROM syllabus_reviews
            WHERE user_id=? AND subject_id=?
        """, (uid, task["subject_id"])).fetchone()
        roadmap = conn.execute("""
            SELECT source_hash,units_hash,sessions_json FROM course_roadmaps
            WHERE user_id=? AND subject_id=?
        """, (uid, task["subject_id"])).fetchone()
        if not review or review["status"] != "confirmed" or not syllabus_text or \
                review["source_hash"] != fingerprint or not roadmap:
            return _unavailable(subject,
                "Đề cương chưa được xác nhận hoặc đã thay đổi. Hãy rà soát lại trước khi học.")
        try:
            units = json.loads(review["units_json"])
            sessions = json.loads(roadmap["sessions_json"])
            if not isinstance(units, list) or not isinstance(sessions, list):
                raise ValueError("Invalid saved structure")
            fresh = (bool(sessions)
                     and all(isinstance(x, dict) for x in sessions)
                     and sessions[0].get("planner_version") == PLAN_VERSION
                     and roadmap["source_hash"] == fingerprint
                     and roadmap["units_hash"] == unit_fingerprint(units))
            lesson = next((item for item in sessions
                           if item.get("session_id") == task["roadmap_session_id"]), None)
        except (ValueError, KeyError, TypeError, AttributeError):
            return _unavailable(subject, "Lộ trình không đọc được. Hãy tạo lại từ đề cương đã xác nhận.")
        if not fresh or not lesson or \
                session_signature(lesson) != task["roadmap_session_signature"]:
            return _unavailable(subject,
                "Nội dung lộ trình khác buổi đã lưu. Hãy rà soát lại lộ trình; giờ và tiến độ cũ vẫn được giữ.")

        # Saved roadmap hints are not authorization: resolve private documents
        # from the current user's CURRENT subject on every page request.
        private_docs = []
        seen = set()
        for item in lesson.get("materials") or []:
            if not isinstance(item, dict) or item.get("kind") != "personal":
                continue
            try:
                doc_id = int(item.get("id"))
            except (ValueError, TypeError):
                continue
            if doc_id in seen:
                continue
            row = conn.execute("""
                SELECT id,original_name,stored_name FROM documents
                WHERE id=? AND user_id=? AND subject_id=? AND id!=COALESCE(?, -1)
            """, (doc_id, uid, task["subject_id"],
                  task["personal_syllabus_document_id"])).fetchone()
            if row:
                private_docs.append({
                    "name": row["original_name"],
                    "link": url_for("uploaded_file", filename=row["stored_name"]),
                })
                seen.add(doc_id)

        # Only currently Admin-approved shared documents mapped to the CURRENT
        # official syllabus chapter; ignore shared IDs embedded in saved JSON.
        shared_docs = []
        if kind == "shared":
            shared = project.ensure_shared_subject_for_user_subject(
                conn, uid, task["subject_id"]
            )
            if shared:
                official, official_hash, _ = official_syllabus(conn, shared["id"])
                chapter_index = lesson.get("unit_id")
                if (official and official_hash == fingerprint
                        and isinstance(chapter_index, int)
                        and 1 <= chapter_index <= len(units)):
                    ensure_chapter_material_schema(conn)
                    key = chapter_key(units[chapter_index - 1].get("evidence", ""))
                    for row in approved_document_rows(
                            conn, shared["id"], key, fingerprint):
                        shared_docs.append({
                            "name": row["original_name"],
                            "link": url_for("shared_document_file", doc_id=row["id"]),
                        })

        # The chapter tutor requires non-empty, readable, currently approved
        # shared files. Personal documents stay available in the room but
        # are not silently reclassified as Admin-approved source material.
        chat_ready = bool(
            kind == "shared" and shared_docs and shared["admin_managed"] and
            prepared_sources(approved_document_rows(
                conn, shared["id"],
                chapter_key(units[chapter_index - 1].get("evidence", "")),
                fingerprint
            ))
        ) if kind == "shared" and shared_docs else False

        ensure_tracking_schema(conn)
        study_state = read_state(conn, task, uid)
        study_csrf = session.get("study_session_csrf")
        if not study_csrf:
            study_csrf = secrets.token_hex(24)
            session["study_session_csrf"] = study_csrf
        start_text, end_text = _schedule_display(task["study_at"], task["duration"])
        return render_template(
            "study_session.html", page="study_plan",
            subject=subject, task=task, lesson=lesson,
            syllabus_name=syllabus_name, private_docs=private_docs,
            shared_docs=shared_docs, start_text=start_text, end_text=end_text,
            chat_ready=chat_ready, study_state=study_state, study_csrf=study_csrf,
        )
    finally:
        conn.close()


@study_session_bp.route("/api/study-plan/tasks/<int:task_id>/chat-history")
def learning_session_chat_history(task_id):
    """Only turns tagged with this verified session + current sources."""
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập để sử dụng Chat AI."}), 401
    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["role"] != "student":
            return jsonify({"error": "Chỉ sinh viên được sử dụng Chat theo buổi."}), 403
        from chapter_chat_context import LessonContextError
        from study_session_chat_context import validated_session_chat
        from chat_lesson_memory import history_for_mode
        try:
            context = validated_session_chat(project, conn, uid, task_id)
        except LessonContextError as error:
            return jsonify({"error": error.message}), error.status
        project.ensure_subject_chats(uid, conn)
        conversation = conn.execute("""
            SELECT id FROM chat_conversations
            WHERE user_id=? AND subject_id=? ORDER BY id LIMIT 1
        """, (uid, context["subject_id"])).fetchone()
        if not conversation:
            return jsonify({"error": "Không tìm thấy Chat theo môn học."}), 404
        messages = history_for_mode(
            conn, uid, conversation["id"], context, limit=40
        )
        return jsonify({
            "conversation_id": conversation["id"],
            "subject_id": context["subject_id"],
            "chapter_number": context["chapter_number"],
            "session_task_id": context["session_task_id"],
            "messages": [dict(item) for item in messages],
            "source_names": list(dict.fromkeys(
                item["name"] for item in context["sources"]
            )),
        })
    finally:
        conn.close()


@study_session_bp.route("/api/study-plan/tasks/<int:task_id>/study-session",
                        methods=["GET", "POST"])
def learning_session_tracking(task_id):
    """Student-only, source-verified timer. GET reads; POST commits one transition."""
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập để ghi nhận thời gian học."}), 401
    if request.method == "POST":
        token = session.get("study_session_csrf") or ""
        supplied = request.headers.get("X-Study-CSRF", "")
        if not token or not secrets.compare_digest(token, supplied):
            return jsonify({"error": "Phiên xác nhận không hợp lệ. Hãy tải lại trang học."}), 403
        if not request.is_json:
            return jsonify({"error": "Yêu cầu phải có định dạng JSON."}), 415
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not isinstance(body.get("action"), str):
            return jsonify({"error": "Thiếu thao tác phiên học."}), 400
        action = body["action"]
    else:
        action = None
    conn = project.db()
    try:
        ensure_tracking_schema(conn)
        task = verified_roadmap_task(project, conn, uid, task_id)
        if request.method == "GET":
            return jsonify(read_state(conn, task, uid))
        # Schema helpers above may commit. Lock after validation and check
        # ownership and the saved roadmap signature again under the write lock.
        conn.execute("BEGIN IMMEDIATE")
        locked = conn.execute("""
            SELECT t.* FROM study_tasks t JOIN subjects s
              ON s.id=t.subject_id AND s.user_id=t.user_id
            WHERE t.id=? AND t.user_id=? AND t.source='roadmap'
              AND t.roadmap_session_id=?
              AND t.roadmap_session_signature=? AND s.id=?
        """, (task_id, uid, task["roadmap_session_id"],
              task["roadmap_session_signature"], task["subject_id"])).fetchone()
        if not locked:
            conn.rollback()
            return jsonify({"error": "Buổi học vừa thay đổi. Hãy tải lại trang."}), 409
        state = apply_action(project, conn, locked, uid, action)
        conn.commit()
        return jsonify(state)
    except StudyTrackingError as error:
        conn.rollback()
        return jsonify({"error": error.message}), error.status
    finally:
        conn.close()


@study_session_bp.route("/api/study-plan/tasks/<int:task_id>/quiz-context",
                        methods=["GET"])
def study_session_quiz_context(task_id):
    """7.1: read-only, per-user chapter+session+approved-source preview.

    No question generation, Quiz writes, answer keys or file texts.
    """
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "Hãy đăng nhập để xem Quiz theo buổi."}), 401
    conn = project.db()
    try:
        try:
            context = get_session_quiz_context(project, conn, uid, task_id)
        except LessonContextError as error:
            return jsonify({"error": error.message}), error.status
        return jsonify(public_session_quiz_context(context))
    finally:
        conn.close()
