"""Original Mobile document preview: bytes, access control, size and format.

Uses temporary SQLite and source files; no real student data or external AI.
"""
import base64
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def run():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as temporary:
            project.DB_PATH = Path(temporary) / "mobile-original-files.sqlite"
            project.UPLOAD_DIR = Path(temporary) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            stamp = project.now()

            def add_user(name, role="student"):
                return conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (name, name + "@preview.test", "hash", role, stamp),
                ).lastrowid

            owner, stranger, admin = (
                add_user("preview-owner"), add_user("preview-stranger"),
                add_user("preview-admin", "admin"),
            )
            own_subject = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (owner, "Môn kiểm thử PDF", "PREVIEW-101", stamp),
            ).lastrowid
            conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (stranger, "Môn khác", "OTHER-999", stamp),
            )
            shared = project.ensure_shared_subject_for_user_subject(
                conn, owner, own_subject
            )
            original_bytes = b"%PDF-1.4\n% original binary \x00\xff\n%%EOF"
            (project.UPLOAD_DIR / "personal.pdf").write_bytes(original_bytes)
            (project.UPLOAD_DIR / "shared.pdf").write_bytes(original_bytes)
            personal = conn.execute(
                "INSERT INTO documents(user_id,subject_id,original_name,"
                "stored_name,extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                (owner, own_subject, "bai-giang.pdf", "personal.pdf",
                 "Đây là văn bản trích xuất không được gửi trong API file.", stamp),
            ).lastrowid
            common = conn.execute(
                "INSERT INTO shared_documents(shared_subject_id,original_name,"
                "stored_name,extracted_text,is_syllabus,created_by_user_id,created_at)"
                " VALUES(?,?,?,?,0,?,?)",
                (shared["id"], "de-cuong.pdf", "shared.pdf",
                 "Nội dung OCR chỉ dùng nội bộ", admin, stamp),
            ).lastrowid
            conn.commit()
            conn.close()

            def client_for(uid):
                client = project.app.test_client()
                if uid:
                    with client.session_transaction() as state:
                        state["user_id"] = uid
                return client

            student = client_for(owner)
            other = client_for(stranger)
            admin_client = client_for(admin)
            guest = client_for(None)
            private_url = f"/api/mobile/documents/{personal}/file"
            shared_url = f"/api/mobile/shared-documents/{common}/file"

            for url in (private_url, shared_url):
                assert guest.get(url).status_code == 401
                assert admin_client.get(url).status_code == 403
                result = student.get(url)
                assert result.status_code == 200, result.get_json()
                assert result.headers.get("Cache-Control") == "private, no-store"
                body = result.get_json()
                assert body["type"] == "application/pdf"
                assert body["name"].endswith(".pdf")
                assert base64.b64decode(body["base64"]) == original_bytes
                assert "extracted_text" not in body

            assert other.get(private_url).status_code == 404
            assert other.get(shared_url).status_code == 403
            assert student.get("/api/mobile/documents/9999/file").status_code == 404
            assert student.get("/api/mobile/shared-documents/9999/file").status_code == 404

            # Oversized sources must never cross the base64 transport boundary.
            (project.UPLOAD_DIR / "personal.pdf").write_bytes(b"x" * (8 * 1024 * 1024 + 1))
            assert student.get(private_url).status_code == 413
            # A stored filename cannot escape the uploads directory.
            conn = project.db()
            conn.execute("UPDATE documents SET stored_name=? WHERE id=?",
                         ("../private.pdf", personal))
            conn.commit()
            conn.close()
            assert student.get(private_url).status_code == 404

            # A valid source with an unsupported extension must not be offered.
            conn = project.db()
            conn.execute(
                "UPDATE documents SET stored_name=?,original_name=? WHERE id=?",
                ("shared.pdf", "payload.exe", personal),
            )
            conn.commit()
            conn.close()
            assert student.get(private_url).status_code == 415

    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Mobile original file PASS: native source bytes, ACL, size, MIME, safety")


if __name__ == "__main__":
    run()
