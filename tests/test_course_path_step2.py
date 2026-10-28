"""Regression checks for Step 2: syllabus-bound, course-owned study sessions."""
import json
import sys
import tempfile
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import parse_chapter_details, match_course_materials, build_course_roadmap, PLAN_VERSION, normalized_lines


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
    # Regression: real pypdf extraction has bullet-prefixed numbered subtopics and
    # standalone section headings; an earlier parser created empty generic chapters.
    pdf_style = """4. NỘI DUNG CHI TIẾT HỌC PHẦN
Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán
Thời lượng: 6 tiết | Phân bổ: Tuần 1-2 | Liên kết chuẩn đầu ra: CLO1, CLO4.
Mục tiêu sau chương
Trình bày được cấu trúc dữ liệu, kiểu dữ liệu trừu tượng (ADT).
Nội dung kiến thức
• 1.1. Khái niệm cấu trúc dữ liệu, dữ liệu và thuật toán
• 1.2. Kiểu dữ liệu trừu tượng (ADT) và các phép toán
AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP
• 1.3. Phân biệt độ phức tạp thời gian và không gian
• 1.4. Ký hiệu O lớn (Big O)
• 1.5. Đọc mã giả và phân tích vòng lặp
Học liệu tham chiếu
SL01 – Slide Tổng quan (tài liệu giả định).
AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP
Hoạt động học tập đề xuất
Đọc SL01 và phân tích 3 đoạn mã có vòng lặp.
Bài tập
BT01: Viết giải thích Big O cho 5 đoạn mã.
Tự kiểm tra theo chương
Quiz Chương 1: 8 câu; chủ đề ADT, Big O.
Tiêu chí gợi ý để chuyển tiếp
Gợi ý kiểm tra đạt 70% và giải thích được bài phân tích.
AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP
Chương 2. Mảng và danh sách liên kết
Thời lượng: 9 tiết | Phân bổ: Tuần 3-5 | Liên kết chuẩn đầu ra: CLO2, CLO4.
Mục tiêu sau chương
Phân biệt mảng và danh sách liên kết.
Nội dung kiến thức
• 2.1. Mảng một chiều
• 2.2. Danh sách liên kết đơn
Bài tập
BT02: Cài đặt danh sách liên kết đơn.
Tự kiểm tra theo chương
Quiz Chương 2: 10 câu lý thuyết.
5. KẾ HOẠCH GIẢNG DẠY 15 TUẦN
• 2.3. Đây không phải tiểu mục của chương 2
"""
    pdf_units = [
        {"title": "Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán",
         "evidence": "Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán"},
        {"title": "Chương 2. Mảng và danh sách liên kết",
         "evidence": "Chương 2. Mảng và danh sách liên kết"},
    ]
    detailed = parse_chapter_details(pdf_style, pdf_units)
    assert len(detailed) == 2
    # pypdf can append repeated page header to a meaningful content line.
    inline_pdf = ("2.5. So sánh mảng và linked list; "
                  "AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP\n"
                  "Đạt 70%; AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP\n"
                  "AI STUDY AGENT / ĐỀ CƯƠNG CHI TIẾT GIẢ LẬP\n")
    assert normalized_lines(inline_pdf) == [
        "2.5. So sánh mảng và linked list", "Đạt 70%"
    ]
    assert len(detailed[0]["topics"]) == 5, detailed[0]["topics"]
    assert detailed[0]["topics"][0].startswith("1.1.")
    assert "kiểu dữ liệu trừu tượng" in detailed[0]["objectives"][0]
    assert detailed[0]["exercises"] == ["BT01: Viết giải thích Big O cho 5 đoạn mã."]
    assert detailed[0]["resource_hints"][0].startswith("SL01")
    assert detailed[0]["clo_refs"] == ["CLO1", "CLO4"]
    assert detailed[0]["quiz_count_from_syllabus"] == 8
    assert detailed[0]["passing_percent_from_syllabus"] == 70
    assert detailed[0]["teaching_periods"] == 6
    for chapter in detailed:
        for field in ("topics", "objectives", "exercises", "resource_hints", "quiz", "criteria", "activities"):
            assert not any("AI STUDY AGENT /" in item for item in (chapter["quiz_description"] if field == "quiz" else chapter["passing_criteria"] if field == "criteria" else chapter["class_activities"] if field == "activities" else chapter[field])), (field, chapter)

    assert detailed[1]["topics"] == ["2.1. Mảng một chiều", "2.2. Danh sách liên kết đơn"]
    plan45 = build_course_roadmap(detailed, [], {
        "goal": "Đạt 8 điểm", "daily_minutes": 45, "preferred_time": "19:00"
    }, start_date=date(2026, 10, 28))
    plan90 = build_course_roadmap(detailed, [], {
        "goal": "Đạt 8 điểm", "daily_minutes": 90, "preferred_time": "19:00"
    }, start_date=date(2026, 10, 28))
    assert len(plan45) == 4, len(plan45)  # 3 for chapter 1, 1 for chapter 2.
    assert len(plan90) == 3, len(plan90)  # Larger learning sessions cover 3 items each.
    assert plan45[0]["planner_version"] == PLAN_VERSION
    assert plan45[2]["quiz"]["recommended_questions"] == 8
    assert plan45[2]["quiz"]["question_count_from_syllabus"] is True
    assert any("BT01" in a for a in plan45[2]["activities"])
    assert plan45[2]["materials"] == []  # No uploaded slide: do not invent one.
    assert plan45[0]["topics"][0].startswith("1.1.")

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
            # The same complete syllabus may be uploaded several times.
            # Copies must never be mistaken for slide/article references.
            for idx in range(3):
                conn.execute("""
                    INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                          extracted_text,created_at)
                    VALUES(?,?,?,?,?,?)
                """, (student, course, "DeCuongChiTiet_CTDL_TEST_GiaLap.pdf",
                      f"copy_{idx}.pdf", example, project.now()))

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
            assert len(sessions) == 7, len(sessions)
            assert [x["unit_id"] for x in sessions] == [1, 2, 3, 3, 4, 5, 6]
            assert [x["topics"] for x in sessions if x["unit_id"] == 3] == [
                ["3.1. Ngăn xếp Stack", "3.2. Hàng đợi Queue"],
                ["3.3. Thao tác push pop"],
            ]
            assert sessions[1]["topics"][0] == "2.1. Danh sách liên kết đơn"
            assert sessions[1]["quiz"]["available"] is False
            # Student-owned notes may be suggested privately without Admin review.
            # They must NEVER be mislabeled as approved shared course materials.
            assert any(x["name"] == "Slide Danh sách liên kết"
                       and x["kind"] == "personal"
                       for x in sessions[1]["materials"]), sessions[1]["materials"]
            assert not any(x["kind"] == "shared" for x in sessions[1]["materials"])
            assert not any("DeCuongChiTiet_CTDL_TEST_GiaLap.pdf" == x["name"]
                           for item in sessions for x in item["materials"])
            assert not any(x["name"] == "OOP không được trộn"
                           for item in sessions for x in item["materials"])
            assert not any(x["name"] == "Riêng của người khác"
                           for item in sessions for x in item["materials"])
            assert conn.execute("SELECT count(*) FROM study_tasks").fetchone()[0] == 0
            conn.close()
            # Even an older cached plan containing a syllabus copy should be
            # sanitized at render time rather than permanently shown.
            conn = project.db()
            cached = json.loads(plan["sessions_json"])
            cached[0]["materials"].append({
                "id": docid+1, "name": "DeCuongChiTiet_CTDL_TEST_GiaLap.pdf",
                "kind": "personal"
            })
            conn.execute("UPDATE course_roadmaps SET sessions_json=? WHERE user_id=? AND subject_id=?",
                         (json.dumps(cached, ensure_ascii=False), student, course))
            conn.commit()
            conn.close()
            loaded = client.get(f"/subjects/{course}/learning-path")
            assert loaded.status_code == 200 and "7 buổi học" in loaded.get_data(as_text=True)
            assert "DeCuongChiTiet_CTDL_TEST_GiaLap.pdf" not in loaded.get_data(as_text=True)
            # Regression: parser updates must invalidate previously saved roadmaps
            # even when the source syllabus and approved chapters are identical.
            conn = project.db()
            obsolete = json.loads(plan["sessions_json"])
            obsolete[0]["planner_version"] = PLAN_VERSION - 1
            conn.execute("UPDATE course_roadmaps SET sessions_json=? WHERE user_id=? AND subject_id=?",
                         (json.dumps(obsolete, ensure_ascii=False), student, course))
            conn.commit()
            conn.close()
            outdated = client.get(f"/subjects/{course}/learning-path").get_data(as_text=True)
            assert "không còn hợp lệ" in outdated
            assert "7 buổi học" not in outdated
            updated = client.post(f"/subjects/{course}/learning-path",
                                  data={"csrf_token": csrf, "action": "generate"})
            assert updated.status_code == 303
            assert "7 buổi học" in client.get(
                f"/subjects/{course}/learning-path").get_data(as_text=True)

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
