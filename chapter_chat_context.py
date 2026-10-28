"""Server-side validated context for one existing Chat AI conversation.

Students can launch Chat AI from a chapter; neither URL params nor JSON fields
are trusted as proof of access. Only confirmed syllabus units and Admin-approved
shared documents are available in this mode.
"""
import json

from chapter_material_routes import (
    approved_document_rows, chapter_key, ensure_chapter_material_schema,
    official_syllabus,
)
from chapter_tutor import prepared_sources
from chat_lesson_memory import approved_source_signature
from course_path_learning import parse_chapter_details
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema


class LessonContextError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status
        super().__init__(message)


def list_chapter_options(project, conn, uid, subject_id):
    """Only confirmed, up-to-date syllabus units for this student's course.

    A chapter is selectable for guided tutoring only when Admin-reviewed,
    text-readable shared resources actually exist for that exact chapter.
    """
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not subject:
        raise LessonContextError("Môn học không thuộc tài khoản.", 404)

    ensure_syllabus_schema(conn)
    ensure_chapter_material_schema(conn)
    kind, source, _ = _source(project, conn, uid, subject_id)
    if kind != "shared" or not source:
        raise LessonContextError(
            "Chưa có đề cương chung của Admin cho môn này.", 409
        )
    fingerprint = syllabus_hash(source)
    review = conn.execute("""
        SELECT units_json,status,source_hash FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """, (uid, subject_id)).fetchone()
    if not review or review["status"] != "confirmed" or review["source_hash"] != fingerprint:
        raise LessonContextError(
            "Hãy phân tích và xác nhận đề cương môn học trước.", 409
        )
    try:
        units = json.loads(review["units_json"])
    except (ValueError, TypeError):
        raise LessonContextError("Dữ liệu chương đã xác nhận không hợp lệ.", 409)
    if not isinstance(units, list) or not units:
        raise LessonContextError("Chưa có chương được xác nhận.", 409)
    shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    if not shared or not shared["admin_managed"]:
        raise LessonContextError("Chưa có đề cương chung do Admin quản lý.", 409)
    official, official_hash, _ = official_syllabus(conn, shared["id"])
    if not official or official_hash != fingerprint:
        raise LessonContextError("Đề cương chung đã thay đổi. Hãy xác nhận lại.", 409)

    options = []
    for index, section in enumerate(parse_chapter_details(source, units)):
        key = chapter_key(section["evidence"])
        rows = approved_document_rows(conn, shared["id"], key, fingerprint)
        ready = prepared_sources(rows)
        options.append({
            "chapter_number": index + 1,
            "title": section["chapter"],
            "topics": section["topics"] if section["topics"] else [section["chapter"]],
            "available": bool(ready),
            "source_names": [item["name"] for item in ready],
        })
    return {"subject_id": subject_id, "subject_name": subject["name"], "chapters": options}


def resolve_lesson_context(project, conn, uid, subject_id, chapter_number,
                           topic_index=None, question=""):
    """Authorize a whole confirmed chapter, or legacy explicit topic context."""
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not subject:
        raise LessonContextError("Môn học không thuộc tài khoản.", 404)

    ensure_syllabus_schema(conn)
    ensure_chapter_material_schema(conn)
    kind, text, source_name = _source(project, conn, uid, subject_id)
    if kind != "shared" or not text:
        raise LessonContextError(
            "Chế độ học có dẫn nguồn cần đề cương chung được Admin quản lý.", 409
        )

    fingerprint = syllabus_hash(text)
    reviewed = conn.execute("""
        SELECT status,source_hash,units_json FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """, (uid, subject_id)).fetchone()
    if not reviewed or (reviewed["status"] != "confirmed" or
                        reviewed["source_hash"] != fingerprint):
        raise LessonContextError(
            "Đề cương đã thay đổi hoặc chưa được xác nhận; hãy xác nhận lại.", 409
        )
    try:
        units = json.loads(reviewed["units_json"])
    except (ValueError, TypeError):
        raise LessonContextError("Dữ liệu chương đã xác nhận không hợp lệ.", 409)
    if (isinstance(chapter_number, bool) or
        not isinstance(chapter_number, int) or
        chapter_number < 1 or chapter_number > len(units)):
        raise LessonContextError("Chương không thuộc đề cương đã xác nhận.", 400)

    section = parse_chapter_details(text, units)[chapter_number - 1]
    topics = section["topics"]
    if topic_index is not None and (
        isinstance(topic_index, bool) or not isinstance(topic_index, int)
        or topic_index < 0 or topic_index >= max(1, len(topics))
    ):
        raise LessonContextError("Tiểu mục không thuộc chương đã xác nhận.", 400)

    shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    if not shared or not shared["admin_managed"]:
        raise LessonContextError("Không có môn học chung do Admin quản lý.", 409)
    official_text, official_hash, _ = official_syllabus(conn, shared["id"])
    if not official_text or official_hash != fingerprint:
        raise LessonContextError("Đề cương chung đã thay đổi; hãy xác nhận lại.", 409)

    key = chapter_key(section["evidence"])
    rows = approved_document_rows(conn, shared["id"], key, fingerprint)
    sources = prepared_sources(rows, question=question)
    if not sources:
        raise LessonContextError(
            "Chương này chưa có học liệu được Admin duyệt và đọc được nội dung.", 409
        )

    # Hash *all* approved source texts, not just the question-specific chunks.
    # Selecting 2.1 then 2.2 keeps one chapter memory unless Admin changes
    # the syllabus, approved documents, or their actual extracted content.
    full_source_signature = approved_source_signature(fingerprint, [
        {"id": row["id"], "name": row["original_name"],
         "excerpt": row["extracted_text"] or ""}
        for row in rows if (row["extracted_text"] or "").strip()
    ])

    return {
        "subject_id": subject_id,
        "subject_name": subject["name"],
        "chapter_number": chapter_number,
        "chapter": section["chapter"],
        "topic_index": topic_index,
        "topic": (topics[topic_index] if topics else section["chapter"])
                 if topic_index is not None else section["chapter"],
        "topics": topics,
        "source_name": source_name,
        "source_signature": full_source_signature,
        "sources": sources,
    }
