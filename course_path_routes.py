"""Per-course learning-path page built only from confirmed syllabus units."""
import json
import secrets
import sys

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from course_path_learning import (
    PLAN_VERSION, build_course_roadmap, parse_chapter_details, unit_fingerprint,
)
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema

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


def _course_documents(project, conn, user_id, subject_id, shared_subject, syllabus_id):
    """Only this student's documents or the matching course's shared documents."""
    docs = []
    personal = conn.execute("""
        SELECT id,original_name,extracted_text FROM documents
        WHERE user_id=? AND subject_id=? AND id!=COALESCE(?, -1)
        ORDER BY id DESC LIMIT 30
    """, (user_id, subject_id, syllabus_id)).fetchall()
    for row in personal:
        if (row["extracted_text"] or "").strip():
            docs.append({
                "id": row["id"], "name": row["original_name"],
                "text": row["extracted_text"], "kind": "personal",
            })
    if shared_subject:
        shared = conn.execute("""
            SELECT id,original_name,extracted_text FROM shared_documents
            WHERE shared_subject_id=? AND is_syllabus=0
            ORDER BY id DESC LIMIT 30
        """, (shared_subject["id"],)).fetchall()
        for row in shared:
            if (row["extracted_text"] or "").strip():
                docs.append({
                    "id": row["id"], "name": row["original_name"],
                    "text": row["extracted_text"], "kind": "shared",
                })
    return docs


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
        token = session.get("syllabus_csrf_token")
        if not token:
            token = secrets.token_hex(24)
            session["syllabus_csrf_token"] = token

        _, text, syllabus_name = _source(project, conn, uid, subject_id)
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
            if request.form.get("action") != "generate":
                return "Thao tác không hợp lệ.", 400
            if not units:
                return redirect(url_for("syllabus.review", subject_id=subject_id,
                                        error="Hãy xác nhận đề cương trước khi lập lộ trình."), code=303)
            chapters = parse_chapter_details(text, units)
            shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
            docs = _course_documents(project, conn, uid, subject_id, shared,
                                     subject["personal_syllabus_document_id"])
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
        return render_template(
            "course_learning_path.html", page="subjects", subject=subject,
            syllabus_name=syllabus_name, units=units, sessions=sessions,
            stale=bool(plan_row and not fresh),
            notice=request.args.get("notice", ""), csrf_token=token,
        )
    finally:
        conn.close()
