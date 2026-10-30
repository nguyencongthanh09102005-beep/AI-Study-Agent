"""Admin-reviewed chapter-to-shared-document mapping, with student-only chapter reading.

The syllabus determines the chapter structure. Content extracted from shared files
is supplementary evidence, never a substitute for confirmed syllabus headings.
"""
import json
import re
import sys

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for

from ai_chapter_suggestions import chapter_ai_prompt, validate_ai_suggestions
from course_path_learning import (
    match_course_materials, parse_chapter_details, personal_course_documents, _terms,
)
from syllabus_learning import extract_syllabus_units, syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema

chapter_material_bp = Blueprint("chapter_material", __name__)

CHAPTER_KEY_RE = re.compile(r"^(?:chương|chapter|bài|lesson|unit|module)\s+(\d+)\b", re.I)


def chapter_key(evidence):
    found = CHAPTER_KEY_RE.match((evidence or "").strip())
    return found.group(1) if found else ""


def ensure_chapter_material_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_document_chapters (
            document_id INTEGER NOT NULL,
            shared_subject_id INTEGER NOT NULL,
            chapter_key TEXT NOT NULL,
            syllabus_hash TEXT NOT NULL,
            confirmed_by INTEGER NOT NULL,
            confirmed_at TEXT NOT NULL,
            PRIMARY KEY (document_id, chapter_key),
            FOREIGN KEY (document_id) REFERENCES shared_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (shared_subject_id) REFERENCES shared_subjects(id) ON DELETE CASCADE,
            FOREIGN KEY (confirmed_by) REFERENCES users(id)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_shared_document_chapters_lookup
        ON shared_document_chapters(shared_subject_id, chapter_key, syllabus_hash)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_document_ai_suggestions (
            document_id INTEGER PRIMARY KEY,
            shared_subject_id INTEGER NOT NULL,
            source_hash TEXT NOT NULL,
            document_hash TEXT NOT NULL,
            suggestions_json TEXT NOT NULL,
            analyzed_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES shared_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (shared_subject_id) REFERENCES shared_subjects(id) ON DELETE CASCADE
        )
    """)
    conn.commit()


def official_syllabus(conn, shared_subject_id):
    row = conn.execute("""
        SELECT original_name,extracted_text
        FROM shared_documents WHERE shared_subject_id=? AND is_syllabus=1
        ORDER BY id DESC LIMIT 1
    """, (shared_subject_id,)).fetchone()
    if row and (row["extracted_text"] or "").strip():
        text = row["extracted_text"].strip()
        return text, syllabus_hash(text), row["original_name"]
    shared = conn.execute(
        "SELECT syllabus_text FROM shared_subjects WHERE id=?",
        (shared_subject_id,),
    ).fetchone()
    text = (shared["syllabus_text"] or "").strip() if shared else ""
    return text, syllabus_hash(text) if text else "", "Đề cương chung"


def approved_document_rows(conn, shared_subject_id, key, fingerprint):
    """Never expose old mappings after the official syllabus is replaced."""
    if not shared_subject_id or not key or not fingerprint:
        return []
    return conn.execute("""
        SELECT sd.id,sd.original_name,sd.extracted_text
        FROM shared_document_chapters map
        JOIN shared_documents sd
          ON sd.id=map.document_id AND sd.shared_subject_id=map.shared_subject_id
        WHERE map.shared_subject_id=? AND map.chapter_key=?
          AND map.syllabus_hash=? AND sd.is_syllabus=0
        ORDER BY sd.id DESC
    """, (shared_subject_id, key, fingerprint)).fetchall()


def evidence_excerpt(text, section):
    """Return short verbatim lines with topical overlap, not AI-invented explanations."""
    search_terms = _terms(section["chapter"] + " " + " ".join(section["topics"]))
    if not search_terms:
        return []
    excerpts = []
    for raw in (text or "").splitlines():
        line = " ".join(raw.split())
        if len(line) < 20 or len(line) > 600:
            continue
        matched = search_terms & _terms(line)
        if len(matched) >= 2 and line not in excerpts:
            excerpts.append(line[:440])
        if len(excerpts) >= 4:
            break
    return excerpts


@chapter_material_bp.route("/admin/documents/<int:document_id>/chapters",
                           methods=["GET", "POST"])
def admin_chapter_mapping(document_id):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="admin"))
    conn = project.db()
    try:
        role = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not role or role["role"] != "admin":
            return "Không có quyền quản lý học liệu chung.", 403
        ensure_chapter_material_schema(conn)
        document = conn.execute("""
            SELECT sd.*,ss.code AS subject_code,ss.name AS subject_name
            FROM shared_documents sd
            JOIN shared_subjects ss ON ss.id=sd.shared_subject_id
            WHERE sd.id=? AND ss.admin_managed=1
        """, (document_id,)).fetchone()
        if not document:
            return "Không tìm thấy tài liệu chung.", 404
        if document["is_syllabus"]:
            return redirect(url_for("admin_shared_documents",
                                    error="Đề cương tổng không cần gắn vào một chương."), code=303)

        source_text, source_hash, source_name = official_syllabus(
            conn, document["shared_subject_id"],
        )
        units = extract_syllabus_units(source_text)
        valid = {}
        for unit in units:
            key = chapter_key(unit["evidence"])
            if key and key not in valid:
                valid[key] = unit

        saved = conn.execute("""
            SELECT chapter_key,syllabus_hash FROM shared_document_chapters
            WHERE document_id=?
        """, (document_id,)).fetchall()
        selected = {row["chapter_key"] for row in saved
                    if row["syllabus_hash"] == source_hash}

        # Enrich official chapter titles with genuine syllabus subtopics.
        sections = parse_chapter_details(source_text, list(valid.values())) if valid else []
        for unit, section in zip(valid.values(), sections):
            unit["topics"] = section["topics"][:8]

        if request.method == "POST":
            if not project.admin_csrf_valid():
                return "Phiên biểu mẫu không hợp lệ.", 403
            if not source_hash or not valid:
                return redirect(url_for("chapter_material.admin_chapter_mapping",
                                        document_id=document_id, error="Chưa có đề cương chuẩn hợp lệ."), code=303)
            action = request.form.get("action", "save")
            if action == "analyze_ai":
                prompt = chapter_ai_prompt(
                    document["extracted_text"] or "", valid, document["subject_code"]
                )
                generated, api_error = project.gemini_generate(prompt)
                if not generated:
                    return redirect(url_for(
                        "chapter_material.admin_chapter_mapping",
                        document_id=document_id,
                        error="AI chưa phản hồi. Kiểm tra cấu hình API và kết nối mạng của máy chủ.",
                    ), code=303)
                result = validate_ai_suggestions(
                    generated, valid, document["extracted_text"] or ""
                )
                if result is None:
                    return redirect(url_for(
                        "chapter_material.admin_chapter_mapping",
                        document_id=document_id,
                        error="AI trả về dữ liệu không đúng định dạng. Chưa lưu gợi ý.",
                    ), code=303)
                conn.execute("""
                    INSERT INTO shared_document_ai_suggestions(
                        document_id,shared_subject_id,source_hash,document_hash,
                        suggestions_json,analyzed_at
                    ) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(document_id) DO UPDATE SET
                        shared_subject_id=excluded.shared_subject_id,
                        source_hash=excluded.source_hash,
                        document_hash=excluded.document_hash,
                        suggestions_json=excluded.suggestions_json,
                        analyzed_at=excluded.analyzed_at
                """, (
                    document_id, document["shared_subject_id"], source_hash,
                    syllabus_hash(document["extracted_text"] or ""),
                    json.dumps(result, ensure_ascii=False), project.now(),
                ))
                conn.commit()
                return redirect(url_for(
                    "chapter_material.admin_chapter_mapping",
                    document_id=document_id,
                    notice=(
                        f"AI đề xuất {len(result)} chương có bằng chứng nguyên văn. "
                        "Vui lòng kiểm tra trước khi duyệt."
                    ),
                ), code=303)
            if action != "save":
                return "Thao tác không hợp lệ.", 400
            chosen = request.form.getlist("chapters")
            if len(chosen) > 40 or len(set(chosen)) != len(chosen) or any(
                key not in valid for key in chosen
            ):
                return "Danh sách chương không hợp lệ.", 400
            # Replace atomically: no partial publication after a bad selection.
            conn.execute("DELETE FROM shared_document_chapters WHERE document_id=?",
                         (document_id,))
            for key in chosen:
                conn.execute("""
                    INSERT INTO shared_document_chapters(
                        document_id,shared_subject_id,chapter_key,syllabus_hash,
                        confirmed_by,confirmed_at
                    ) VALUES(?,?,?,?,?,?)
                """, (document_id, document["shared_subject_id"], key, source_hash,
                      uid, project.now()))
            conn.commit()
            return redirect(url_for("chapter_material.admin_chapter_mapping",
                                    document_id=document_id,
                                    notice="Đã xác nhận liên kết tài liệu với chương học."), code=303)

        suggested = set()
        doc_value = {"id": document_id, "name": document["original_name"],
                     "text": document["extracted_text"], "kind": "shared"}
        for unit in valid.values():
            # Hints are only suggestions and NEVER persisted without Admin approval.
            section = {"chapter": unit["title"], "topics": []}
            if match_course_materials(section, [doc_value]):
                suggested.add(chapter_key(unit["evidence"]))

        ai_record = conn.execute("""
            SELECT source_hash,document_hash,suggestions_json
            FROM shared_document_ai_suggestions WHERE document_id=?
        """, (document_id,)).fetchone()
        ai_valid = bool(
            ai_record
            and ai_record["source_hash"] == source_hash
            and ai_record["document_hash"] ==
                syllabus_hash(document["extracted_text"] or "")
        )
        ai_suggestions = (
            json.loads(ai_record["suggestions_json"]) if ai_valid else []
        )
        ai_by_key = {entry["key"]: entry["evidence"] for entry in ai_suggestions}

        chapters = [
            {"key": key, "title": unit["title"],
             "approved": key in selected, "suggested": key in suggested}
            for key, unit in valid.items()
        ]
        return render_template(
            "admin_chapter_mapping.html", page="admin", document=document,
            source_name=source_name, chapters=chapters,
            source_present=bool(source_hash and valid),
            syllabus_uploaded=bool(source_text.strip()),
            syllabus_preview="\n".join(source_text.splitlines()[:18])[:1200],
            ai_by_key=ai_by_key, ai_analyzed=ai_valid,
            stale=bool(saved and not selected and any(row["syllabus_hash"] != source_hash
                                                      for row in saved)),
            csrf_token=project.admin_form_token(),
            notice=request.args.get("notice", "")[:250],
            error=request.args.get("error", "")[:250],
        )
    finally:
        conn.close()


@chapter_material_bp.route("/subjects/<int:subject_id>/chapters/<int:chapter_number>")
def student_chapter(subject_id, chapter_number):
    project = sys.modules[current_app.import_name]
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login", tab="login"))
    conn = project.db()
    try:
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        if not user or user["role"] != "student":
            return "Chỉ sinh viên có quyền học chương.", 403
        subject = conn.execute(
            "SELECT * FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid),
        ).fetchone()
        if not subject:
            return "Không tìm thấy môn học thuộc tài khoản.", 404
        ensure_syllabus_schema(conn)
        ensure_chapter_material_schema(conn)
        kind, source, source_name = _source(project, conn, uid, subject_id)
        fingerprint = syllabus_hash(source) if source else ""
        review = conn.execute("""
            SELECT units_json,status,source_hash
            FROM syllabus_reviews WHERE user_id=? AND subject_id=?
        """, (uid, subject_id)).fetchone()
        if not review or review["status"] != "confirmed" or review["source_hash"] != fingerprint:
            return redirect(url_for("syllabus.review", subject_id=subject_id,
                                    error="Hãy xác nhận đề cương hiện tại trước khi học theo chương."),
                            code=303)
        units = json.loads(review["units_json"])
        if chapter_number < 1 or chapter_number > len(units):
            return "Không tìm thấy chương được xác nhận.", 404
        section = parse_chapter_details(source, units)[chapter_number-1]
        shared = project.ensure_shared_subject_for_user_subject(conn, uid, subject_id)
        mapping_allowed = False
        materials = []
        if shared and kind == "shared":
            official_text, official_hash, _ = official_syllabus(conn, shared["id"])
            mapping_allowed = bool(official_text and official_hash == fingerprint)
        if mapping_allowed:
            key = chapter_key(section["evidence"])
            for row in approved_document_rows(conn, shared["id"], key, fingerprint):
                materials.append({
                    "id": row["id"], "name": row["original_name"],
                    "kind": "shared",
                    "excerpts": evidence_excerpt(row["extracted_text"], section),
                })
        # Personal study notes stay private; suggest only if content matches.
        private_docs = personal_course_documents(
            conn, uid, subject_id,
            subject["personal_syllabus_document_id"], source, limit=50
        )
        private_candidates = []
        for doc in private_docs:
            if match_course_materials(section, [doc]):
                private_candidates.append({
                    "name": doc["name"],
                    "excerpts": evidence_excerpt(doc["text"], section),
                })
        return render_template(
            "student_chapter.html", page="subjects", subject=subject,
            chapter=section, chapter_number=chapter_number, total_chapters=len(units),
            materials=materials, personal_materials=private_candidates[:5],
            source_name=source_name, source_kind=kind,
            mapping_allowed=mapping_allowed,
        )
    finally:
        conn.close()
