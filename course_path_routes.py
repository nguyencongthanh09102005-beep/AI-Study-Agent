"""Per-course learning-path page built only from confirmed syllabus units."""
import json
import secrets
import sys

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from course_path_learning import (
    PLAN_VERSION, build_course_roadmap, parse_chapter_details, unit_fingerprint,
    personal_course_documents,
)
from syllabus_learning import syllabus_hash
from course_schedule_sync import (
    ensure_session_schedule_schema, import_roadmap_lessons,
    scheduled_lessons, session_signature,
)
from syllabus_routes import _source, ensure_syllabus_schema
from chapter_material_routes import (
    approved_document_rows, chapter_key, ensure_chapter_material_schema, official_syllabus,
)

course_path_bp = Blueprint("course_path", __name__)


def ensure_roadmap_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS course_roadmaps (
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            source_hash TEXT NOT NULL,
            units_hash TEXT NOT NULL,
            sessions_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, subject_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def _course_documents(project, conn, user_id, subject_id, shared_subject,
                      syllabus_id, source_text):
    """Only unique private study documents; never offer the syllabus as a slide."""
    return personal_course_documents(
        conn, user_id, subject_id, syllabus_id, source_text
    )

@course_path_bp.route("/subjects/<int:subject_id>/learning-path", methods=["GET", "POST"])
def learning_path(subject_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="login"))

    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["role"] != "student":
            return "Chỉ sinh viên được truy cập lộ trình cá nhân.", 403
        subject = conn.execute(
            "SELECT * FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid),
        ).fetchone()
        if not subject:
            return "Không tìm thấy môn học thuộc tài khoản.", 404

        ensure_syllabus_schema(conn)
        ensure_roadmap_schema(conn)
        ensure_session_schedule_schema(conn)
        token = session.get("syllabus_csrf_token")
        if not token:
            token = secrets.token_hex(24)
            session["syllabus_csrf_token"] = token

        source_kind, text, syllabus_name = _source(project, conn, uid, subject_id)
        fingerprint = syllabus_hash(text) if text else ""
        review_row = conn.execute("""
            SELECT * FROM syllabus_reviews WHERE user_id=? AND subject_id=?
        """, (uid, subject_id)).fetchone()
        units = []
        if (review_row and review_row["status"] == "confirmed"
                and text and review_row["source_hash"] == fingerprint):
            units = json.loads(review_row["units_json"])
        unit_hash = unit_fingerprint(units) if units else ""

        plan_row = conn.execute("""
            SELECT * FROM course_roadmaps WHERE user_id=? AND subject_id=?
        """, (uid, subject_id)).fetchone()
        saved_sessions = json.loads(plan_row["sessions_json"]) if plan_row else []
        fresh = bool(plan_row and units and saved_sessions
                     and plan_row["source_hash"] == fingerprint
                     and plan_row["units_hash"] == unit_hash
                     and saved_sessions[0].get("planner_version") == PLAN_VERSION)

        if request.method == "POST":
            if not secrets.compare_digest(request.form.get("csrf_token", ""), token):
                return "Phiên biểu mẫu không hợp lệ.", 403
            action = request.form.get("action")
            if action == "schedule":
                # Import is explicit: creating a roadmap alone never creates
                # or deletes Study Plan tasks, and old/stale plans are rejected.
                if not fresh:
                    return redirect(url_for(
                        "course_path.learning_path", subject_id=subject_id,
                        notice="Lộ trình chưa hợp lệ. Hãy phân tích/tạo lại trước khi đưa vào lịch.",
                    ), code=303)
                try:
                    summary = import_roadmap_lessons(
                        conn, uid, subject_id, saved_sessions, project.now()
                    )
                except ValueError as exc:
                    return redirect(url_for(
                        "course_path.learning_path", subject_id=subject_id,
                        notice=str(exc),
                    ), code=303)
                if summary["created"]:
                    project.recalculate_subject_progress(uid, subject_id, conn)
                conn.commit()
                message = (
                    f"Đã đưa {summary['created']} buổi mới vào Kế hoạch học; "
                    f"{summary['existing']} buổi đã có được giữ nguyên."
                )
                if summary["changed"]:
                    message += (
                        f" Có {summary['changed']} buổi đã thay đổi nội dung; "
                        "lịch cũ được giữ để bạn rà soát, không tự ghi đè."
                    )
                # Detect collisions across all subjects after import, but do
                # not automatically reschedule any existing lesson.
                from study_schedule_conflicts import find_study_conflicts
                conflicts = find_study_conflicts(conn.execute(
                    "SELECT id,title,study_at,duration FROM study_tasks WHERE user_id=?",
                    (uid,)
                ).fetchall())
                overlapping_roadmap = conn.execute(
                    """SELECT id FROM study_tasks
                       WHERE user_id=? AND subject_id=? AND source='roadmap'
                         AND roadmap_session_id IS NOT NULL""",
                    (uid, subject_id)
                ).fetchall()
                affected = sum(1 for item in overlapping_roadmap
                               if item["id"] in conflicts)
                if affected:
                    message += (
                        f" Cảnh báo: {affected} buổi từ lộ trình đang trùng giờ "
                        "với lịch khác. Mở Kế hoạch học → Giờ để chọn giờ mới."
                    )
                return redirect(url_for(
                    "course_path.learning_path", subject_id=subject_id,
                    notice=message,
                ), code=303)
            if action != "generate":
                return "Thao tác không hợp lệ.", 400
            if not units:
                return redirect(url_for("syllabus.review", subject_id=subject_id,
                                        error="Hãy xác nhận đề cương trước khi lập lộ trình."), code=303)
            chapters = parse_chapter_details(text, units)
            shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
            docs = _course_documents(project, conn, uid, subject_id, shared,
                                     subject["personal_syllabus_document_id"], text)
            profile = project.ensure_learning_profile(conn, uid)
            goal = (profile["goals"] or "").strip()
            if not goal and subject["target_score"]:
                goal = f'Mục tiêu đạt {subject["target_score"]} điểm'
            if not goal:
                goal = f'Hoàn thành nội dung môn {subject["name"]}'
            preferences = {
                "goal": goal, "daily_minutes": profile["daily_minutes"],
                "preferred_time": profile["preferred_study_time"],
            }
            weak_rows = conn.execute("""
                SELECT topic FROM learning_weaknesses
                WHERE user_id=? AND subject_id=? AND miss_count>correct_count
                ORDER BY miss_count DESC LIMIT 10
            """, (uid, subject_id)).fetchall()
            weaknesses = [dict(row) for row in weak_rows]
            sessions = build_course_roadmap(chapters, docs, preferences, weaknesses)
            conn.execute("""
                INSERT INTO course_roadmaps(user_id,subject_id,source_hash,units_hash,
                                            sessions_json,updated_at)
                VALUES(?,?,?,?,?,?)
                ON CONFLICT(user_id,subject_id) DO UPDATE SET
                    source_hash=excluded.source_hash,
                    units_hash=excluded.units_hash,
                    sessions_json=excluded.sessions_json,
                    updated_at=excluded.updated_at
            """, (uid, subject_id, fingerprint, unit_hash,
                  json.dumps(sessions, ensure_ascii=False), project.now()))
            conn.commit()
            return redirect(url_for("course_path.learning_path", subject_id=subject_id,
                                    notice="Đã xây dựng lộ trình từ đề cương đã xác nhận."), code=303)

        sessions = saved_sessions if fresh else []
        # Filter older saved plans dynamically, without deleting the user's PDFs.
        if sessions:
            valid_private = {
                d["id"] for d in personal_course_documents(
                    conn, uid, subject_id,
                    subject["personal_syllabus_document_id"], text
                )
            }
            for lesson in sessions:
                lesson["materials"] = [
                    doc for doc in lesson.get("materials", [])
                    if doc.get("kind") != "personal" or doc.get("id") in valid_private
                ]
        # Show confirmed shared materials live, even when Admin approves/revokes
        # a document after the student's roadmap was generated.
        if sessions and source_kind == "shared":
            shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
            if shared:
                official_text, official_hash, _ = official_syllabus(conn, shared["id"])
                if official_text and official_hash == fingerprint:
                    ensure_chapter_material_schema(conn)
                    linked_by_chapter = {}
                    for index, unit in enumerate(units):
                        key = chapter_key(unit["evidence"])
                        if key:
                            linked_by_chapter[index + 1] = [
                                {"id": row["id"], "name": row["original_name"],
                                 "kind": "shared", "approved": True}
                                for row in approved_document_rows(
                                    conn, shared["id"], key, fingerprint)
                            ]
                    for lesson in sessions:
                        existing = lesson.get("materials") or []
                        confirmed = linked_by_chapter.get(lesson["unit_id"], [])
                        # Only personal suggestions plus explicitly reviewed shared files.
                        lesson["materials"] = [
                            doc for doc in existing if doc.get("kind") == "personal"
                        ] + confirmed
        linked = scheduled_lessons(conn, uid, subject_id) if sessions else {}
        schedule_status = {
            int(lesson["session_id"]): (
                "current" if linked[int(lesson["session_id"])]["roadmap_session_signature"]
                == session_signature(lesson) else "changed"
            )
            for lesson in sessions
            if int(lesson["session_id"]) in linked
        }
        return render_template(
            "course_learning_path.html", page="subjects", subject=subject,
            syllabus_name=syllabus_name, units=units, sessions=sessions,
            schedule_status=schedule_status,
            stale=bool(plan_row and not fresh),
            notice=request.args.get("notice", "")[:400], csrf_token=token,
        )
    finally:
        conn.close()
