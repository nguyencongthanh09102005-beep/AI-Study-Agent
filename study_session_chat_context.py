"""Validate a scheduled learning session before reusing the existing Chat AI.

A task id from a browser is never a source of authority. The user, subject,
confirmed syllabus, saved roadmap version and individual session signature
must all match. No task dates/progress are modified.
"""
import hashlib
import json

from chapter_chat_context import LessonContextError, resolve_lesson_context
from course_path_learning import PLAN_VERSION, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from course_schedule_sync import ensure_session_schedule_schema, session_signature
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema


def verified_study_session(project, conn, uid, task_id):
    ensure_session_schedule_schema(conn)
    row = conn.execute("""
        SELECT t.*,s.personal_syllabus_document_id
        FROM study_tasks t JOIN subjects s
          ON s.id=t.subject_id AND s.user_id=t.user_id
        WHERE t.id=? AND t.user_id=? AND t.source='roadmap'
          AND t.roadmap_session_id IS NOT NULL
    """, (task_id, uid)).fetchone()
    if not row:
        raise LessonContextError("Không tìm thấy buổi học trong lộ trình của bạn.", 404)

    subject_id = row["subject_id"]
    ensure_syllabus_schema(conn)
    ensure_roadmap_schema(conn)
    _, text, _ = _source(project, conn, uid, subject_id)
    fingerprint = syllabus_hash(text) if text else ""
    review = conn.execute("""
        SELECT status,source_hash,units_json FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """, (uid, subject_id)).fetchone()
    roadmap = conn.execute("""
        SELECT source_hash,units_hash,sessions_json FROM course_roadmaps
        WHERE user_id=? AND subject_id=?
    """, (uid, subject_id)).fetchone()
    if not text or not review or review["status"] != "confirmed" or \
            review["source_hash"] != fingerprint or not roadmap:
        raise LessonContextError("Đề cương chưa được xác nhận hoặc đã thay đổi.", 409)
    try:
        units = json.loads(review["units_json"])
        sessions = json.loads(roadmap["sessions_json"])
        if not isinstance(units, list) or not isinstance(sessions, list) or not sessions:
            raise ValueError("Invalid roadmap")
        valid = (all(isinstance(item, dict) for item in sessions)
                 and sessions[0].get("planner_version") == PLAN_VERSION
                 and roadmap["source_hash"] == fingerprint
                 and roadmap["units_hash"] == unit_fingerprint(units))
        lesson = next((item for item in sessions
                       if item["session_id"] == row["roadmap_session_id"]), None)
    except (ValueError, TypeError, KeyError):
        raise LessonContextError("Không thể xác thực lộ trình học.", 409)
    if not valid or not lesson or session_signature(lesson) != row["roadmap_session_signature"]:
        raise LessonContextError(
            "Lộ trình hoặc buổi học đã thay đổi; hãy rà soát và tải lại.", 409
        )
    chapter_number = lesson.get("unit_id")
    if isinstance(chapter_number, bool) or not isinstance(chapter_number, int) or \
            chapter_number < 1 or chapter_number > len(units):
        raise LessonContextError("Chương của buổi học không hợp lệ.", 409)
    return {
        "task_id": int(row["id"]), "subject_id": subject_id,
        "chapter_number": chapter_number, "lesson": lesson,
        "task_signature": row["roadmap_session_signature"],
    }


def validated_session_chat(project, conn, uid, task_id, question=""):
    task = verified_study_session(project, conn, uid, task_id)
    chapter = resolve_lesson_context(
        project, conn, uid, task["subject_id"],
        task["chapter_number"], topic_index=None, question=question
    )
    chapter["base_source_signature"] = chapter["source_signature"]
    chapter["source_signature"] = hashlib.sha256(
        ("session-v1|" + str(task["task_id"]) + "|" +
         task["task_signature"] + "|" + chapter["source_signature"])
        .encode("utf-8")
    ).hexdigest()
    chapter["session_task_id"] = task["task_id"]
    chapter["session_title"] = str(task["lesson"].get("title") or "")[:180]
    chapter["session_topics"] = list(task["lesson"].get("topics") or [])[:10]
    chapter["session_objectives"] = list(task["lesson"].get("objectives") or [])[:6]
    chapter["session_activities"] = list(task["lesson"].get("activities") or [])[:8]
    return chapter
