"""Regression checks for Step 2: syllabus-bound, course-owned study sessions."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import parse_chapter_details, match_course_materials


def check():
    example = """ĐỀ CƯƠNG CHI TIẾT
1. Chuẩn đầu ra
Chương 1. Tổng quan thuật toán
1.1. Khái niệm giải thuật
1.2. Đánh giá độ phức tạp Big O
Mục tiêu: Phân tích độ phức tạp
Bài tập: Xác định độ phức tạp đoạn mã
Chương 2. Danh sách liên kết
2.1. Danh sách liên kết đơn
2.2. Danh sách liên kết đôi
Mục tiêu: Cài đặt danh sách liên kết
Bài tập: Thêm và xóa nút
Chương 3. Ngăn xếp và hàng đợi
3.1. Ngăn xếp Stack
3.2. Hàng đợi Queue
3.3. Thao tác push pop
Chương 4. Cây nhị phân
4.1. Duyệt cây nhị phân
4.2. Cây tìm kiếm nhị phân
Chương 5. Bảng băm
5.1. Hàm băm
5.2. Xử lý va chạm
Chương 6. Thuật toán sắp xếp
6.1. Sắp xếp nhanh
6.2. Sắp xếp trộn
4. PHƯƠNG PHÁP ĐÁNH GIÁ
"""
    units = [
        {"title": line, "evidence": line}
        for line in example.splitlines() if line.startswith("Chương ")
    ]
    chapters = parse_chapter_details(example, units)
    assert len(chapters) == 6
    assert chapters[1]["topics"] == [
        "2.1. Danh sách liên kết đơn", "2.2. Danh sách liên kết đôi"
    ]
    assert chapters[-1]["topics"] == ["6.1. Sắp xếp nhanh", "6.2. Sắp xếp trộn"]
    try:
        parse_chapter_details(example, [{"title": "Chương 99", "evidence": "Chương 99"}])
        assert False, "Unanchored chapter accepted"
    except ValueError:
        pass
    assert match_course_materials(chapters[1], [
        {"id": 1, "name": "slide.doc", "kind": "personal", "text": "Không có từ liên quan"}
    ]) == []

    old_db, old_dir = project.DB_PATH, project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as folder:
        project.DB_PATH = Path(folder) / "study.db"
        project.UPLOAD_DIR = Path(folder) / "uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn = project.db()
            student = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?)
            """, ("Sinh viên 1", "s1@step2.test", "hash", "student", project.now())).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES(?,?,?,?,?)
            """, ("Sinh viên 2", "s2@step2.test", "hash", "student", project.now())).lastrowid
            course = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Cấu trúc dữ liệu", "CTDL_STEP2", project.now())).lastrowid
            other_course = conn.execute("""
                INSERT INTO subjects(user_id,name,code,created_at)
                VALUES(?,?,?,?)
            """, (student, "Lập trình hướng đối tượng", "OOP_STEP2", project.now())).lastrowid
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (student, course, "Slide Danh sách liên kết", "slide1.txt",
                  "Danh sách liên kết đơn. Danh sách liên kết đôi. Thao tác thêm xóa nút.",
                  project.now()))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (student, other_course, "OOP không được trộn", "slide2.txt",
                  "Danh sách liên kết đơn và danh sách liên kết đôi.",
                  project.now()))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (other, None, "Riêng của người khác", "slide3.txt",
                  "Danh sách liên kết đơn và danh sách liên kết đôi.",
                  project.now()))
            conn.commit()
            conn.close()

            client = project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"] = student
            page = client.get(f"/subjects/{course}/learning-path")
            assert page.status_code == 200, page.get_data(as_text=True)[:400]
            with client.session_transaction() as sess:
                csrf = sess["syllabus_csrf_token"]
            not_ready = client.post(f"/subjects/{course}/learning-path",
                                    data={"csrf_token": csrf, "action": "generate"})
            assert not_ready.status_code == 303
            assert client.post(f"/subjects/{course}/learning-path",
                               data={"action": "generate"}).status_code == 403

            conn = project.db()
            from syllabus_routes import ensure_syllabus_schema
            ensure_syllabus_schema(conn)
            docid = conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                      extracted_text,created_at)
                VALUES(?,?,?,?,?,?)
            """, (student, course, "Đề cương", "syllabus.txt", example,
                  project.now())).lastrowid
            conn.execute("UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                         (docid, course))
            from syllabus_learning import syllabus_hash
            conn.execute("""
                INSERT INTO syllabus_reviews(user_id,subject_id,source_hash,source_kind,units_json,status,updated_at)
                VALUES(?,?,?,?,?,'confirmed',?)
            """, (student, course, syllabus_hash(example.strip()), "personal",
                  json.dumps(units, ensure_ascii=False), project.now()))
            conn.commit()
            conn.close()

            result = client.post(f"/subjects/{course}/learning-path",
                                 data={"csrf_token": csrf, "action": "generate"})
            assert result.status_code == 303
            conn = project.db()
            plan = conn.execute(
                "SELECT * FROM course_roadmaps WHERE user_id=? AND subject_id=?",
                (student, course)).fetchone()
            if plan is None:
                from syllabus_routes import _source
                extracted = _source(project, conn, student, course)
                source_row = conn.execute("SELECT status,source_hash,units_json FROM syllabus_reviews WHERE user_id=? AND subject_id=?", (student, course)).fetchone()
                raise AssertionError(f"No plan: redirect={result.headers.get('Location')}, source={extracted[0]}, length={len(extracted[1])}, hash={syllabus_hash(extracted[1])}, saved={dict(source_row) if source_row else None}")
            sessions = json.loads(plan["sessions_json"])
            assert len(sessions) == 6, len(sessions)
            assert [x["unit_id"] for x in sessions] == list(range(1, 7))
            assert sessions[1]["topics"][0] == "2.1. Danh sách liên kết đơn"
            assert sessions[1]["quiz"]["available"] is False
            assert any(x["name"] == "Slide Danh sách liên kết"
                       for x in sessions[1]["materials"]), sessions[1]["materials"]
            assert not any(x["name"] == "OOP không được trộn"
                           for item in sessions for x in item["materials"])
            assert not any(x["name"] == "Riêng của người khác"
                           for item in sessions for x in item["materials"])
            assert conn.execute("SELECT count(*) FROM study_tasks").fetchone()[0] == 0
            conn.close()
            loaded = client.get(f"/subjects/{course}/learning-path")
            assert loaded.status_code == 200 and "6 buổi học" in loaded.get_data(as_text=True)

            outsider = project.app.test_client()
            with outsider.session_transaction() as sess:
                sess["user_id"] = other
            assert outsider.get(f"/subjects/{course}/learning-path").status_code == 404

            conn = project.db()
            conn.execute("UPDATE documents SET extracted_text=extracted_text || ? WHERE id=?",
                         ("\nChương 7. Đồ thị", docid))
            conn.commit()
            conn.close()
            stale = client.get(f"/subjects/{course}/learning-path").get_data(as_text=True)
            assert "không còn hợp lệ" in stale
            print("Step 2: source-bound units, course isolation, persistence, CSRF, staleness OK")
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_db, old_dir


if __name__ == "__main__":
    check()
