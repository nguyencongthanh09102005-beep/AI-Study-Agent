"""Syllabus analysis and human review, scoped to one student and one course.

This first stage does not replace or silently modify the old study planner.
"""
import json
import os
import secrets
import sys

from flask import Blueprint, current_app, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename

from syllabus_learning import extract_syllabus_units, syllabus_hash, syllabus_llm_prompt

syllabus_bp = Blueprint("syllabus", __name__)


def ensure_syllabus_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS syllabus_reviews (
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            source_hash TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            units_json TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('draft', 'confirmed')),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, subject_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def _source(project, conn, uid, subject_id):
    shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    if shared:
        official = conn.execute("""
            SELECT original_name, extracted_text FROM shared_documents
            WHERE shared_subject_id=? AND is_syllabus=1
            ORDER BY id DESC LIMIT 1
        """, (shared["id"],)).fetchone()
        if official and (official["extracted_text"] or "").strip():
            return "shared", official["extracted_text"].strip(), official["original_name"]
        if (shared["syllabus_text"] or "").strip():
            return "shared", shared["syllabus_text"].strip(), "Đề cương chung từ Admin"
    row = conn.execute("""
        SELECT d.extracted_text, d.original_name FROM documents d
        JOIN subjects s ON s.personal_syllabus_document_id = d.id
        WHERE s.id=? AND s.user_id=? AND d.user_id=? AND d.subject_id=s.id
    """, (subject_id, uid, uid)).fetchone()
    if row and (row["extracted_text"] or "").strip():
        return "personal", row["extracted_text"].strip(), row["original_name"]
    return "none", "", "Chưa có đề cương"


def _back(subject_id, **kwargs):
    return redirect(url_for("syllabus.review", subject_id=subject_id, **kwargs), code=303)


@syllabus_bp.route("/subjects/<int:subject_id>/syllabus", methods=["GET", "POST"])
def review(subject_id):
    # Resolve the actual running app even when launched as python app.py.
    project = sys.modules[current_app.import_name]

    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="login"))
    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["role"] != "student":
            return "Chỉ sinh viên được truy cập đề cương cá nhân.", 403
        subject = conn.execute(
            "SELECT * FROM subjects WHERE id=? AND user_id=?", (subject_id, uid)
        ).fetchone()
        if not subject:
            return "Không tìm thấy môn học thuộc tài khoản.", 404
        ensure_syllabus_schema(conn)
        token = session.get("syllabus_csrf_token")
        if not token:
            token = secrets.token_hex(24)
            session["syllabus_csrf_token"] = token

        kind, text, name = _source(project, conn, uid, subject_id)
        fingerprint = syllabus_hash(text) if text else ""
        review_row = conn.execute(
            "SELECT * FROM syllabus_reviews WHERE user_id=? AND subject_id=?",
            (uid, subject_id)
        ).fetchone()

        if request.method == "POST":
            if not secrets.compare_digest(
                request.form.get("csrf_token", ""), token
            ):
                return "Phiên biểu mẫu không hợp lệ.", 403
            action = request.form.get("action", "")

            if action == "upload":
                uploaded = request.files.get("file")
                if not uploaded or not uploaded.filename or not project.allowed_file(uploaded.filename):
                    return _back(subject_id, error="Chọn file PDF, DOCX, TXT hoặc MD hợp lệ.")
                original = os.path.basename(uploaded.filename.replace("\\", "/"))[:180]
                safe = secure_filename(original)
                if not safe:
                    return _back(subject_id, error="Tên file không hợp lệ.")
                stored = "syllabus_" + secrets.token_hex(12) + "_" + safe
                path = project.UPLOAD_DIR / stored
                try:
                    uploaded.save(path)
                    extracted = project.extract_text(path)
                    if not extracted.strip():
                        path.unlink(missing_ok=True)
                        return _back(subject_id, error="Không trích xuất được nội dung từ file. PDF scan cần OCR; Word phải là DOCX hợp lệ.")
                    cursor = conn.execute("""
                        INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                              extracted_text,created_at)
                        VALUES (?,?,?,?,?,?)
                    """, (uid, subject_id, original, stored, extracted, project.now()))
                    conn.execute("""
                        UPDATE subjects SET personal_syllabus_document_id=?
                        WHERE id=? AND user_id=?
                    """, (cursor.lastrowid, subject_id, uid))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    path.unlink(missing_ok=True)
                    raise
                return _back(subject_id, notice="Đã lưu đề cương riêng trong môn. Nếu có đề cương chung, bản chung vẫn được ưu tiên.")

            if action == "analyze":
                if not text:
                    return _back(subject_id, error="Hãy tải lên hoặc chọn đề cương trước.")
                model_response = None
                if os.getenv("GEMINI_API_KEY", "").strip():
                    model_response, _ = project.gemini_generate(syllabus_llm_prompt(text))
                units = extract_syllabus_units(text, model_response)
                if not units:
                    return _back(subject_id, error="Chưa tìm được tiêu đề chương/bài đáng tin cậy. Kiểm tra file đề cương hoặc yêu cầu GVHD hỗ trợ.")
                conn.execute("""
                    INSERT INTO syllabus_reviews(user_id,subject_id,source_hash,source_kind,
                                                  units_json,status,updated_at)
                    VALUES (?,?,?,?,?,'draft',?)
                    ON CONFLICT(user_id,subject_id) DO UPDATE SET
                        source_hash=excluded.source_hash,
                        source_kind=excluded.source_kind,
                        units_json=excluded.units_json,
                        status='draft', updated_at=excluded.updated_at
                """, (uid, subject_id, fingerprint, kind, json.dumps(units, ensure_ascii=False), project.now()))
                conn.commit()
                return _back(subject_id, notice="Đã phân tích; hãy kiểm tra từng chương rồi xác nhận.")

            if action == "confirm":
                if not review_row or review_row["status"] != "draft":
                    return _back(subject_id, error="Chưa có kết quả phân tích mới để xác nhận.")
                if not text or review_row["source_hash"] != fingerprint:
                    return _back(subject_id, error="Đề cương đã thay đổi. Cần phân tích lại trước khi xác nhận.")
                saved = json.loads(review_row["units_json"])
                confirmed = []
                for i, item in enumerate(saved):
                    if request.form.get(f"include_{i}") != "1":
                        continue
                    title = " ".join(request.form.get(f"title_{i}", "").split())[:180]
                    if len(title) < 3:
                        return _back(subject_id, error="Tên chương không hợp lệ.")
                    confirmed.append({"title": title, "evidence": item["evidence"]})
                if not confirmed:
                    return _back(subject_id, error="Cần giữ lại ít nhất một chương học.")
                conn.execute("""
                    UPDATE syllabus_reviews SET units_json=?,status='confirmed',updated_at=?
                    WHERE user_id=? AND subject_id=? AND source_hash=?
                """, (json.dumps(confirmed, ensure_ascii=False), project.now(), uid, subject_id, fingerprint))
                conn.commit()
                return _back(subject_id, notice="Đã xác nhận danh sách chương cho môn học này.")
            return "Thao tác không hợp lệ.", 400

        is_current = bool(review_row and text and review_row["source_hash"] == fingerprint)
        units = json.loads(review_row["units_json"]) if is_current else []
        return render_template(
            "syllabus_review.html", page="subjects", subject=subject,
            source_kind=kind, source_name=name, source_text=text,
            units=units, review_status=review_row["status"] if is_current else "none",
            is_stale=bool(review_row and not is_current),
            csrf_token=token, notice=request.args.get("notice", ""),
            error=request.args.get("error", ""), upload_max_mb=project.MAX_UPLOAD_MB,
        )
    finally:
        conn.close()
