"""Phase 7.1: read-only, verified per-session Quiz context and opt-in Quiz linkage.

The existing document/subject/weakness Quiz generation and grading are
unchanged. This module prepares a provenance-backed link for Phase 7.2:
never trust a task id, material id or chapter number supplied by the browser.
"""
import hashlib
import json

from chapter_chat_context import LessonContextError
from chapter_material_routes import (
    approved_document_rows, chapter_key, official_syllabus,
    ensure_chapter_material_schema,
)
from study_session_chat_context import verified_study_session, validated_session_chat
from syllabus_learning import syllabus_hash
from syllabus_routes import _source


def ensure_session_quiz_schema(conn):
    """Additive only: no migration or rewrite of quizzes / quiz_attempts."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_session_links (
            quiz_id INTEGER PRIMARY KEY,
            task_id INTEGER,
            user_id INTEGER NOT NULL,
            subject_id INTEGER,
            chapter_number INTEGER NOT NULL CHECK(chapter_number >= 1),
            session_title TEXT NOT NULL,
            session_signature TEXT NOT NULL,
            source_signature TEXT NOT NULL,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
            FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE SET NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_quiz_session_owner
        ON quiz_session_links(user_id,subject_id,task_id)
    """)
    # Repeated calls are safe; caller controls transaction.


def get_session_quiz_context(project, conn, uid, task_id):
    """Resolve exactly one confirmed roadmap session and current Admin sources.

    Expose only IDs/names of approved files, NEVER file bodies, legacy private
    files or guessed questions. If no sources are ready, still show a truthful
    preview of the student's own session (without enabling generation).
    """
    user = conn.execute(
        "SELECT role FROM users WHERE id=?", (uid,)
    ).fetchone()
    if not user or user["role"] != "student":
        raise LessonContextError("Chỉ sinh viên được sử dụng Quiz theo buổi.", 403)

    identity = verified_study_session(project, conn, uid, task_id)
    subject_id = identity["subject_id"]
    course = conn.execute(
        "SELECT name,code FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not course:
        raise LessonContextError("Môn học không thuộc tài khoản.", 404)

    lesson = identity["lesson"]
    result = {
        "task_id": identity["task_id"],
        "subject_id": subject_id,
        "subject_name": course["name"],
        "subject_code": course["code"] or "",
        "chapter_number": identity["chapter_number"],
        "chapter": str(lesson.get("chapter") or "")[:200],
        "session_title": str(lesson.get("title") or "")[:200],
        "objectives": [str(v)[:260] for v in (lesson.get("objectives") or [])[:8]],
        "topics": [str(v)[:260] for v in (lesson.get("topics") or [])[:12]],
        "task_signature": identity["task_signature"],
        "source_signature": "",
        "source_ids": [],
        "source_names": [],
        "ready": False,
        "reason": "",
    }

    # Reuse the SAME validation as the scoped AI tutor, including
    # Admin ownership, matching current official syllabus, chapter mapping,
    # readable non-empty extracted source and content-signature checks.
    try:
        tutor = validated_session_chat(project, conn, uid, task_id)
    except LessonContextError as error:
        if error.status != 409:
            raise
        result["reason"] = error.message
        return result

    kind, syllabus, _ = _source(project, conn, uid, subject_id)
    shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    if kind != "shared" or not shared or not shared["admin_managed"]:
        result["reason"] = "Chưa có học liệu chung được Admin duyệt."
        return result
    official, approved_hash, _ = official_syllabus(conn, shared["id"])
    fingerprint = syllabus_hash(syllabus)
    if not official or fingerprint != approved_hash:
        result["reason"] = "Đề cương chung đã thay đổi, cần xác nhận lại."
        return result

    units = conn.execute("""
        SELECT units_json FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """, (uid, subject_id)).fetchone()
    try:
        sections = json.loads(units["units_json"])
        evidence = sections[identity["chapter_number"]-1].get("evidence", "")
    except (TypeError, ValueError, IndexError, AttributeError, KeyError):
        raise LessonContextError("Chương trong đề cương không hợp lệ.", 409)

    ensure_chapter_material_schema(conn)
    key = chapter_key(evidence)
    approved = approved_document_rows(conn, shared["id"], key, fingerprint)
    sources = [row for row in approved if (row["extracted_text"] or "").strip()]
    if not sources:
        result["reason"] = "Chương chưa có học liệu chung đọc được đã được Admin duyệt."
        return result

    result.update({
        "source_ids": [int(row["id"]) for row in sources],
        "source_names": [str(row["original_name"]) for row in sources],
        "source_signature": hashlib.sha256(
            ("session-quiz-v1|" + str(task_id) + "|" +
             identity["task_signature"] + "|" + tutor["source_signature"])
            .encode("utf-8")
        ).hexdigest(),
        "ready": True,
    })
    return result


def public_session_quiz_context(context):
    """No source body, task signature, internal IDs or AI answer keys."""
    keep = ("task_id", "subject_id", "subject_name", "subject_code",
            "chapter_number", "chapter", "session_title", "objectives",
            "topics", "source_names", "ready", "reason")
    return {name: context[name] for name in keep}


def link_generated_quiz(conn, uid, quiz_id, context, created_at):
    """Phase 7.2 will call after a successful, owner-scoped Quiz INSERT.

    The caller must freshly resolve context in the same transaction as insert.
    A legacy Quiz cannot silently become a session Quiz and quiz results are
    never rewritten. Idempotency/retries fail without replacing prior links.
    """
    ensure_session_quiz_schema(conn)
    quiz = conn.execute("""
        SELECT id,subject_id FROM quizzes WHERE id=? AND user_id=?
    """, (quiz_id, uid)).fetchone()
    if not quiz or quiz["subject_id"] != context["subject_id"]:
        raise LessonContextError("Quiz không thuộc môn học và tài khoản này.", 404)
    if not context.get("ready") or not context.get("source_signature"):
        raise LessonContextError("Học liệu của buổi chưa được xác thực.", 409)
    current = conn.execute(
        "SELECT quiz_id FROM quiz_session_links WHERE quiz_id=?", (quiz_id,)
    ).fetchone()
    if current:
        raise LessonContextError("Quiz đã được liên kết với một buổi học.", 409)
    conn.execute("""
        INSERT INTO quiz_session_links(
          quiz_id,task_id,user_id,subject_id,chapter_number,
          session_title,session_signature,source_signature,
          source_ids_json,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        quiz_id, context["task_id"], uid, context["subject_id"],
        context["chapter_number"], context["session_title"],
        context["task_signature"], context["source_signature"],
        json.dumps(context["source_ids"]), created_at,
    ))
