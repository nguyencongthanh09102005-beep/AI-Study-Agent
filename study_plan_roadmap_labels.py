"""Read-only roadmap labels for the compact Web study timetable.

A scheduled study task links to a *snapshot* of a course roadmap session.
Display verified lesson metadata only when the saved snapshot signature still
matches that exact session, subject, and student. No scheduling or updates.
"""
import json
import re

from course_schedule_sync import session_signature


_CHAPTER_PREFIX = re.compile(
    r"^\s*(Chương|Bài|Phần|Chapter|Unit|Module)\s+([0-9]+|[IVXLCDM]+)\b",
    re.IGNORECASE,
)


def _short_chapter(chapter):
    """Keep an explicit chapter heading; never invent a chapter number."""
    name = str(chapter or "").strip()
    if not name:
        return ""
    match = _CHAPTER_PREFIX.match(name)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    # If the syllabus uses named units rather than numbered chapters,
    # retain the actual confirmed heading (the browser truncates visually).
    return name[:120]


def roadmap_timetable_labels(conn, user_id, tasks):
    """Return {task_id: short_label} using this student's linked roadmap.

    A stale, missing, invalid or foreign roadmap never becomes an invented
    chapter label. Its calendar card simply shows the original task title.
    """
    owned = {}
    for task in tasks:
        if (task["user_id"] != user_id or task["source"] != "roadmap"
                or not task["roadmap_session_id"]
                or not task["roadmap_session_signature"]
                or not task["subject_id"]):
            continue
        try:
            sid = int(task["roadmap_session_id"])
        except (TypeError, ValueError):
            continue
        if sid < 1:
            continue
        owned[(task["subject_id"], sid)] = task

    if not owned:
        return {}

    # Existing accounts that have never built a roadmap need no migrations.
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='course_roadmaps'"
    ).fetchone():
        return {}

    labels = {}
    for row in conn.execute(
        "SELECT subject_id, sessions_json FROM course_roadmaps WHERE user_id=?",
        (user_id,),
    ).fetchall():
        try:
            sessions = json.loads(row["sessions_json"])
        except (TypeError, ValueError):
            continue
        if not isinstance(sessions, list):
            continue
        for lesson in sessions:
            if not isinstance(lesson, dict):
                continue
            try:
                sid = int(lesson["session_id"])
            except (KeyError, TypeError, ValueError):
                continue
            task = owned.get((row["subject_id"], sid))
            if not task or task["roadmap_session_signature"] != session_signature(lesson):
                continue

            quiz = lesson.get("quiz")
            # The final 60-question session belongs to the whole course,
            # even though unit_id references the last chapter for access.
            if isinstance(quiz, dict) and quiz.get("action") == "quiz_final":
                label = f"Ôn tập cuối môn · Buổi {sid}"
            else:
                chapter = _short_chapter(lesson.get("chapter"))
                if not chapter:
                    continue
                label = f"{chapter} · Buổi {sid}"
            labels[task["id"]] = label
    return labels
