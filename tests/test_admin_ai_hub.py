"""Unified Admin AI learning-material hub: layout, authorization and links.

GET renders only and MUST NOT call the LLM. Existing approval workflows are
still separate, server-side routes; the hub must not auto-approve anything.
"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project

def run():
    previous_db,previous_upload=project.DB_PATH,project.UPLOAD_DIR
    with TemporaryDirectory() as root:
        project.DB_PATH=Path(root)/"admin-hub.sqlite"
        project.UPLOAD_DIR=Path(root)/"uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn=project.db()
            now=project.now()
            admin=conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at)"
                " VALUES(?,?,?,?,?)",
                ("Admin","admin-hub@example.test","hash","admin",now)
            ).lastrowid
            student=conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at)"
                " VALUES(?,?,?,?,?)",
                ("Student","student-hub@example.test","hash","student",now)
            ).lastrowid
            with_syllabus=conn.execute("""
                INSERT INTO shared_subjects
                (subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?,?,1,?,?)
            """,("admin-hub-1","OOP-TEST-2026","Tư Duy Thiết Kế",
                 "Chương 1. Tư duy thiết kế",now,now)).lastrowid
            without_syllabus=conn.execute("""
                INSERT INTO shared_subjects
                (subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?,'',1,?,?)
            """,("admin-hub-2","68209281","Lịch sử Đảng",now,now)).lastrowid
            conn.execute("""
                INSERT INTO shared_documents
                (shared_subject_id,original_name,stored_name,extracted_text,
                 is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?,? ,0,?,?)
            """,(with_syllabus,"chuong1.txt","test1.txt","Học liệu chương 1",admin,now))
            conn.commit()
            conn.close()
            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=admin
            student_client=project.app.test_client()
            with student_client.session_transaction() as sess:
                sess["user_id"]=student

            with patch.object(project,"gemini_generate",
                              side_effect=AssertionError("GET must not call AI")):
                response=client.get("/admin/documents")
            assert response.status_code==200,response.get_data(as_text=True)[:500]
            html=response.get_data(as_text=True)
            assert html.count('id="adminAiSubject"') == 1
            assert html.count('id="adminAiHub"') == 1
            assert 'id="bulkChapterSubject"' not in html
            assert 'id="syllabusAnalysisSubject"' not in html
            assert 'id="adminAiSyllabus"' in html
            assert 'id="adminAiBulk"' in html
            assert 'id="adminUploadForm"' in html
            assert 'id="adminUploadFile"' in html
            assert 'id="sharedSubject"' in html
            assert 'id="admin-ai-test-nonexistent"' not in html
            assert "admin_ai_hub.js" in html
            assert "Phân tích đề cương" in html
            assert "Phân loại toàn bộ" in html
            assert html.count("admin-ai-step-number") == 2
            for id in (with_syllabus,without_syllabus):
                assert f'/admin/subjects/{id}/syllabus-analysis' in html
                assert f'/admin/subjects/{id}/chapters/bulk' in html
            assert 'data-has-syllabus="1"' in html
            assert 'data-has-syllabus="0"' in html
            assert 'data-document-count="1"' in html
            assert 'data-document-count="0"' in html
            assert 'name="is_syllabus"' in html
            assert 'action="/admin/documents"' in html
            # No admin workflows or files shown to non-admin users.
            assert student_client.get("/admin/documents").status_code==403
            subjects=client.get("/admin").get_data(as_text=True)
            assert 'id="adminAiHub"' not in subjects
            assert 'id="adminSubjectForm"' in subjects
            print("Admin AI hub PASS: one selector, two safe routes, no calls, "
                  "intact upload/permissions and empty-state data")
        finally:
            project.DB_PATH,project.UPLOAD_DIR=previous_db,previous_upload

if __name__=="__main__":
    run()
