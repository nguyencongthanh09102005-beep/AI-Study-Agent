"""Batch chapter mapping regression: isolation, strict citations, approval and stale safety."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from syllabus_learning import syllabus_hash

SYLLABUS = """ĐỀ CƯƠNG HỌC PHẦN
Chương 1. Nguyên tắc về tư duy thiết kế
1.1. Phân tích và đồng cảm người dùng
Chương 2. Tạo mẫu và kiểm thử sản phẩm
2.1. Mẫu thử và nghiên cứu người dùng
"""
DOC1 = """Tư duy thiết kế phải bắt đầu từ việc quan sát hành vi người dùng thực tế.
Phương pháp thấu cảm bao gồm phỏng vấn sâu và quan sát khách hàng.
"""
DOC2 = """Tạo mẫu thử nhanh giúp nhóm nghiên cứu kiểm chứng các giả định trước khi triển khai.
Kiểm thử người dùng nên xác định nhiệm vụ, ghi nhận phản hồi và đề xuất cải tiến.
"""
QUOTE1 = "Tư duy thiết kế phải bắt đầu từ việc quan sát hành vi người dùng thực tế."
QUOTE2 = "Tạo mẫu thử nhanh giúp nhóm nghiên cứu kiểm chứng các giả định trước khi triển khai."


def verify():
    previous_db, previous_dir = project.DB_PATH, project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as tmp:
        project.DB_PATH = Path(tmp) / "db.sqlite"
        project.UPLOAD_DIR = Path(tmp) / "uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn = project.db()
            now = project.now()
            admin = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Quản trị viên","admin@batch.test","hash","admin",now)
            ).lastrowid
            student = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Học viên","student@batch.test","hash","student",now)
            ).lastrowid
            course = conn.execute(
                "INSERT INTO shared_subjects(subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at) "
                "VALUES(?,?,?,?,1,?,?)",
                ("BULK101","BULK101","Đồ án kiểm thử",SYLLABUS,now,now)
            ).lastrowid
            other = conn.execute(
                "INSERT INTO shared_subjects(subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at) "
                "VALUES(?,?,?,?,1,?,?)",
                ("OTHER101","OTHER101","Môn khác",SYLLABUS,now,now)
            ).lastrowid
            doc_ids = []
            for name, content, sid in [
                ("chapter1.txt",DOC1,course),
                ("chapter2.txt",DOC2,course),
                ("other_private.txt","Tài liệu của môn khác, không thể chia sẻ tùy tiện.",other),
            ]:
                doc_ids.append(conn.execute(
                    "INSERT INTO shared_documents(shared_subject_id,original_name,stored_name,extracted_text,"
                    "is_syllabus,created_by_user_id,created_at) VALUES(?,?,?,?,0,?,?)",
                    (sid,name,name,content,admin,now)
                ).lastrowid)
            conn.commit()
            conn.close()
            admin_client = project.app.test_client()
            with admin_client.session_transaction() as ses:
                ses["user_id"] = admin
            student_client = project.app.test_client()
            with student_client.session_transaction() as ses:
                ses["user_id"] = student
            route = f"/admin/subjects/{course}/chapters/bulk"
            assert student_client.get(route).status_code == 403
            assert admin_client.get(f"/admin/subjects/{other+10000}/chapters/bulk").status_code == 404
            index = admin_client.get("/admin/documents").get_data(as_text=True)
            assert route in index and "Phân loại toàn bộ" in index
            response = admin_client.get(route)
            assert response.status_code == 200, response.get_data(as_text=True)[:500]
            body = response.get_data(as_text=True)
            assert "chapter1.txt" in body and "chapter2.txt" in body
            assert "other_private.txt" not in body
            with admin_client.session_transaction() as ses:
                csrf = ses["admin_csrf_token"]
            hashes = {"source_hash":syllabus_hash(SYLLABUS.strip()),
                      f"hash_{doc_ids[0]}":syllabus_hash(DOC1),
                      f"hash_{doc_ids[1]}":syllabus_hash(DOC2)}
            assert admin_client.post(route, data={**hashes,"action":"analyze"}).status_code == 403
            calls = []
            def fake_model(prompt):
                calls.append(prompt)
                assert "other_private.txt" not in prompt
                assert "Tài liệu của môn khác" not in prompt
                return (json.dumps({"documents":[
                    {"document_id":doc_ids[0],"suggestions":[
                        {"chapter_key":"1","evidence":QUOTE1},
                        {"chapter_key":"2","evidence":"Dẫn chứng bịa không có thật trong tài liệu khác"}
                    ]},
                    {"document_id":doc_ids[1],"suggestions":[
                        {"chapter_key":"2","evidence":QUOTE2}
                    ]},
                    {"document_id":doc_ids[2],"suggestions":[
                        {"chapter_key":"1","evidence":QUOTE1}
                    ]}
                ]},ensure_ascii=False), None)
            with patch.object(project,"gemini_generate",fake_model):
                resp = admin_client.post(route,data={**hashes,"csrf_token":csrf,"action":"analyze"})
                assert resp.status_code == 303
            assert len(calls) == 1, len(calls)  # one model call for two documents
            conn = project.db()
            assert conn.execute("SELECT COUNT(*) FROM shared_document_chapters").fetchone()[0] == 0
            verified = conn.execute(
                "SELECT document_id,suggestions_json FROM shared_document_ai_suggestions "
                "ORDER BY document_id"
            ).fetchall()
            assert len(verified) == 2, verified
            by_id = {x["document_id"]:json.loads(x["suggestions_json"]) for x in verified}
            assert [v["key"] for v in by_id[doc_ids[0]]] == ["1"]
            assert [v["key"] for v in by_id[doc_ids[1]]] == ["2"]
            conn.close()
            page = admin_client.get(route).get_data(as_text=True)
            assert QUOTE1 in page and QUOTE2 in page
            with patch.object(project,"gemini_generate",side_effect=AssertionError("should reuse cache")):
                assert admin_client.post(route,data={**hashes,"csrf_token":csrf,"action":"analyze"}).status_code == 303
            assert admin_client.post(route,data={
                **hashes, "csrf_token":csrf, "action":"confirm", f"chapter_{doc_ids[0]}":"99"
            }).status_code == 400
            assert admin_client.post(route,data={
                **hashes,"source_hash":"stale","csrf_token":csrf,"action":"confirm"
            }).status_code == 409
            approved = admin_client.post(route,data={
                **hashes,"csrf_token":csrf,"action":"confirm",
                f"chapter_{doc_ids[0]}":"1",f"chapter_{doc_ids[1]}":"2"
            })
            assert approved.status_code == 303
            conn = project.db()
            links = conn.execute(
                "SELECT document_id,chapter_key FROM shared_document_chapters ORDER BY document_id"
            ).fetchall()
            assert [(x["document_id"],x["chapter_key"]) for x in links] == [
                (doc_ids[0],"1"),(doc_ids[1],"2")
            ]
            conn.close()
            print("Bulk chapter AI PASS: one grouped call, cache, verified quotes, isolation, CSRF, admin approval, stale checks")
        finally:
            project.DB_PATH,project.UPLOAD_DIR = previous_db,previous_dir


if __name__ == "__main__":
    verify()
