"""Course-first syllabus workflow regression and access tests.

Runs with an isolated SQLite database; does not touch the user's demo data.
"""
import io
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from syllabus_learning import extract_syllabus_units, syllabus_hash


def verify():
    sample = """1. Mục tiêu học phần
2. Chuẩn đầu ra học phần
3. Tài liệu tham khảo
Chương 1. Tổng quan cấu trúc dữ liệu
Chương 2. Danh sách liên kết
Chương 3. Ngăn xếp
"""
    assert len(extract_syllabus_units(sample)) == 3
    # Real PDFs often split the numeric heading from its title.
    split_lines = """ĐỀ CƯƠNG CHI TIẾT HỌC PHẦN
Chương 1
Tổng quan về tư duy thiết kế
1.1. Khái niệm
Chương 2:
Thấu cảm và xác định vấn đề
2.1. Nghiên cứu người dùng
"""
    split_units = extract_syllabus_units(split_lines)
    assert [x["evidence"] for x in split_units] == ["Chương 1", "Chương 2:"]
    assert "Tổng quan về tư duy thiết kế" in split_units[0]["title"]
    assert "Thấu cảm và xác định vấn đề" in split_units[1]["title"]
    # Never convert administrative syllabus sections into learning chapters.
    assert extract_syllabus_units("Chương 1\nChuẩn đầu ra học phần") == []
    assert extract_syllabus_units("1. Mục tiêu\n2. Tài liệu tham khảo") == []
    fake = '{"chapters":[{"evidence":"Chương 99. Giả mạo"}]}'
    assert len(extract_syllabus_units(sample, fake)) == 3
    assert syllabus_hash(sample) != syllabus_hash(sample + " đổi")

    original_db = project.DB_PATH
    original_dir = project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as tmp:
        project.DB_PATH = Path(tmp) / "study.db"
        project.UPLOAD_DIR = Path(tmp) / "uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn = project.db()
            student = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?)
            """, ("Học viên A", "a@syllabus.test", "hash", "student", project.now())).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?)
            """, ("Học viên B", "b@syllabus.test", "hash", "student", project.now())).lastrowid
            admin = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?)
            """, ("Admin", "admin@syllabus.test", "hash", "admin", project.now())).lastrowid
            subject_id = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)
            """, (student, "Cấu trúc dữ liệu", "CTDL100", project.now())).lastrowid
            conn.commit()
            conn.close()

            client = project.app.test_client()
            anonymous = project.app.test_client()
            assert anonymous.get(f"/subjects/{subject_id}/syllabus").status_code in (302, 303)
            with client.session_transaction() as sess:
                sess["user_id"] = student
                sess["user_name"] = "A"
            get = client.get(f"/subjects/{subject_id}/syllabus")
            assert get.status_code == 200, get.get_data(as_text=True)[:200]
            with client.session_transaction() as sess:
                token = sess["syllabus_csrf_token"]
            assert client.post(f"/subjects/{subject_id}/syllabus",
                               data={"action": "analyze"}).status_code == 403

            uploaded = client.post(
                f"/subjects/{subject_id}/syllabus",
                data={
                    "csrf_token": token, "action": "upload",
                    "file": (io.BytesIO(sample.encode("utf-8")), "de_cuong.txt"),
                },
                content_type="multipart/form-data",
            )
            assert uploaded.status_code == 303
            assert "Đề cương riêng" in client.get(
                f"/subjects/{subject_id}/syllabus"
            ).get_data(as_text=True) or "de_cuong.txt" in client.get(
                f"/subjects/{subject_id}/syllabus"
            ).get_data(as_text=True)

            parsed = client.post(f"/subjects/{subject_id}/syllabus",
                                 data={"csrf_token": token, "action": "analyze"})
            assert parsed.status_code == 303
            page = client.get(f"/subjects/{subject_id}/syllabus").get_data(as_text=True)
            assert "Chương 1" in page and "Chương 3" in page
            confirmed = client.post(
                f"/subjects/{subject_id}/syllabus",
                data={"csrf_token": token, "action": "confirm",
                      "include_0": "1", "title_0": "Chương 1. Tổng quan",
                      "include_1": "1", "title_1": "Chương 2. Liên kết"},
            )
            assert confirmed.status_code == 303
            conn = project.db()
            reviewed = conn.execute(
                "SELECT * FROM syllabus_reviews WHERE user_id=? AND subject_id=?",
                (student, subject_id),
            ).fetchone()
            assert reviewed and reviewed["status"] == "confirmed"
            assert conn.execute("SELECT count(*) FROM syllabus_reviews").fetchone()[0] == 1
            conn.close()

            client_b = project.app.test_client()
            with client_b.session_transaction() as sess:
                sess["user_id"] = other
            assert client_b.get(f"/subjects/{subject_id}/syllabus").status_code == 404
            client_admin = project.app.test_client()
            with client_admin.session_transaction() as sess:
                sess["user_id"] = admin
            assert client_admin.get(f"/subjects/{subject_id}/syllabus").status_code == 403

            conn = project.db()
            conn.execute("""
                UPDATE documents SET extracted_text=extracted_text || ?
                WHERE user_id=? AND subject_id=?
            """, ("\nChương 4. Cây nhị phân", student, subject_id))
            conn.commit()
            conn.close()
            stale = client.get(f"/subjects/{subject_id}/syllabus").get_data(as_text=True)
            assert "không còn hiệu lực" in stale
        finally:
            project.DB_PATH = original_db
            project.UPLOAD_DIR = original_dir
    print("Course syllabus upload, review, isolation, and staleness: OK")


if __name__ == "__main__":
    verify()
