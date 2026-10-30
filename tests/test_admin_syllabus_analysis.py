"""Admin syllabus analyzer: odd prefixes, grounded Gemini, approval and isolation."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from admin_syllabus_analysis import (
    approved_shared_units, combine_proposals, syllabus_chunks, validate_ai_chapters,
)
from chapter_material_routes import chapter_key, official_syllabus
from course_path_learning import parse_chapter_details
from syllabus_learning import extract_syllabus_units, syllabus_hash

SYLLABUS = """ĐỀ CƯƠNG CHI TIẾT HỌC PHẦN
Mục tiêu học phần
. Chương 1. Tổng quan về dữ liệu
1.1. Kiến thức cơ bản về dữ liệu và thuật toán
► Chương 2. Danh sách liên kết
2.1. Danh sách liên kết đơn và kép
[3] Chương 3. Cấu trúc cây
3.1. Khái niệm cây nhị phân
PHẦN IV: ỨNG DỤNG VÀ KIỂM THỬ
4.1. Kiểm thử đơn vị và ứng dụng
Chuẩn đầu ra học phần
CLO1
"""
UNUSUAL = "PHẦN IV: ỨNG DỤNG VÀ KIỂM THỬ"
OFFICIAL_TEXT = SYLLABUS.strip()


def run():
    units = extract_syllabus_units(SYLLABUS)
    assert len(units) == 3, units
    assert [chapter_key(x["evidence"]) for x in units] == ["1", "2", "3"]
    for section in parse_chapter_details(SYLLABUS, units):
        assert section["evidence"] in SYLLABUS
    malformed = json.dumps({"chapters": [
        {"evidence": UNUSUAL},
        {"evidence": "Chương 99. Chương tự bịa"},
        {"evidence": "Chuẩn đầu ra học phần"},
        {"evidence": "Mục tiêu học phần"},
    ]}, ensure_ascii=False)
    validated = validate_ai_chapters(malformed, SYLLABUS)
    assert [row["evidence"] for row in validated] == [UNUSUAL], validated
    combined = combine_proposals(SYLLABUS, validated)
    assert len(combined) == 4, combined
    assert all(item["evidence"] in SYLLABUS for item in combined)

    long_text = "\n".join("Dữ liệu" + str(i) + " " + ("x"*100) for i in range(400))
    chunks = syllabus_chunks(long_text)
    assert len(chunks) > 1 and "".join(chunks).count("Dữ liệu") == 400

    previous_db, previous_dir = project.DB_PATH, project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as tmp:
        project.DB_PATH = Path(tmp) / "syllabus-ai.sqlite"
        project.UPLOAD_DIR = Path(tmp) / "uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn = project.db()
            stamp = project.now()
            admin_id = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Admin','admin@syllabus-ai.test','hash','admin',?)",
                (stamp,)
            ).lastrowid
            student_id = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Student','student@syllabus-ai.test','hash','student',?)",
                (stamp,)
            ).lastrowid
            shared_id = conn.execute(
                "INSERT INTO shared_subjects(subject_key,code,name,syllabus_text,"
                "admin_managed,created_at,updated_at) VALUES(?,?,?,?,1,?,?)",
                ("TESTAI-SYLL","TESTAI-SYLL","Đồ án dữ liệu",SYLLABUS,stamp,stamp)
            ).lastrowid
            own_subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (student_id,"Đồ án dữ liệu","TESTAI-SYLL",stamp)
            ).lastrowid
            conn.commit()
            conn.close()

            admin = project.app.test_client()
            with admin.session_transaction() as sess:
                sess["user_id"] = admin_id
            other = project.app.test_client()
            with other.session_transaction() as sess:
                sess["user_id"] = student_id
            url = f"/admin/subjects/{shared_id}/syllabus-analysis"
            assert other.get(url).status_code == 403
            assert admin.get(url).status_code == 200
            admin_html = admin.get("/admin/documents").get_data(as_text=True)
            assert url in admin_html
            with admin.session_transaction() as sess:
                csrf = sess["admin_csrf_token"]
            source_hash = syllabus_hash(OFFICIAL_TEXT)
            assert admin.post(url,data={"action":"analyze","source_hash":source_hash}).status_code == 403
            assert admin.post(url,data={"action":"analyze","source_hash":"changed",
                                        "csrf_token":csrf}).status_code == 409

            calls = []
            def fake_gemini(prompt):
                calls.append(prompt)
                assert "PHẦN IV" in prompt
                assert "ĐỀ CƯƠNG" in prompt
                return malformed, None
            with patch.dict(os.environ, {"GEMINI_API_KEY":"offline-test"}):
                with patch.object(project,"gemini_generate",fake_gemini):
                    response = admin.post(url,data={
                        "action":"analyze","source_hash":source_hash,"csrf_token":csrf
                    })
            assert response.status_code == 303 and len(calls) == 1
            conn = project.db()
            assert approved_shared_units(conn,shared_id,OFFICIAL_TEXT) is None
            state = conn.execute("SELECT status,draft_json FROM admin_syllabus_analysis "
                                 "WHERE shared_subject_id=?",(shared_id,)).fetchone()
            assert state["status"] == "draft"
            draft = json.loads(state["draft_json"])
            assert len(draft) == 4, draft
            conn.close()
            assert admin.post(url,data={
                "action":"confirm","source_hash":source_hash,
                "csrf_token":csrf,"include":["99"]
            }).status_code == 400
            payload = {"action":"confirm","source_hash":source_hash,
                       "csrf_token":csrf,"include":[str(i) for i in range(4)]}
            payload.update({f"title_{i}":item["title"] for i,item in enumerate(draft)})
            assert admin.post(url,data=payload).status_code == 303
            conn = project.db()
            verified = approved_shared_units(conn,shared_id,OFFICIAL_TEXT)
            assert verified and len(verified) == 4
            assert verified[-1]["evidence"] == UNUSUAL
            source,_,_=official_syllabus(conn,shared_id)
            from bulk_chapter_mapping import chapter_index
            chapters = chapter_index(source,conn,shared_id)
            assert len(chapters) == 4
            conn.close()
            student_page = other.get(f"/subjects/{own_subject}/syllabus")
            assert student_page.status_code == 200
            with other.session_transaction() as sess:
                student_csrf=sess["syllabus_csrf_token"]
            # Student reuses approved Admin analysis, no new API call.
            with patch.object(project,"gemini_generate",
                              side_effect=AssertionError("Unexpected Gemini call")):
                result=other.post(f"/subjects/{own_subject}/syllabus",data={
                    "action":"analyze","csrf_token":student_csrf
                },follow_redirects=True)
            assert result.status_code == 200
            assert "PHẦN IV" in result.get_data(as_text=True)

            conn=project.db()
            conn.execute("UPDATE shared_subjects SET syllabus_text=? WHERE id=?",
                         (OFFICIAL_TEXT+"\nChương 5. Môn học đổi cấu trúc",shared_id))
            conn.commit()
            assert approved_shared_units(conn,shared_id,
                SYLLABUS+"\nChương 5. Môn học đổi cấu trúc") is None
            conn.close()
            assert admin.post(url,data=payload).status_code == 409
        finally:
            project.DB_PATH,project.UPLOAD_DIR=previous_db,previous_dir
    print("Admin syllabus AI PASS: odd heading prefixes, grounded evidence, role, "
          "CSRF, human approval, student reuse and stale versions")


if __name__ == "__main__":
    run()
