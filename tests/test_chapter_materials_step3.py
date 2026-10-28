"""End-to-end chapter study materials: admin review, student scope, stale syllabus."""
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chapter_material_routes import evidence_excerpt


def check():
    syllabus = """ĐỀ CƯƠNG HỌC PHẦN
Chương 1. Tổng quan và giải thuật
Thời lượng: 6 tiết | CLO1
Mục tiêu sau chương
Giải thích độ phức tạp.
Nội dung kiến thức
• 1.1. Độ phức tạp thuật toán
• 1.2. Ký hiệu Big O
Bài tập
BT01: Giải thích Big O.
Chương 2. Danh sách liên kết
Thời lượng: 6 tiết | CLO2
Mục tiêu sau chương
Làm việc với node, head và next.
Nội dung kiến thức
• 2.1. Danh sách liên kết đơn
• 2.2. Thêm xóa node
Bài tập
BT02: Cài đặt danh sách liên kết.
"""
    slide_text = """Slide danh sách liên kết.
Chương 2. Danh sách liên kết: node head next.
2.1. Danh sách liên kết đơn chứa node và con trỏ next.
2.2. Thêm xóa node trên linked list và duyệt danh sách.
Thuật toán độ phức tạp Big O cũng có thể áp dụng cho linked list.
"""
    old_db, old_dir = project.DB_PATH, project.UPLOAD_DIR
    with tempfile.TemporaryDirectory() as folder:
        project.DB_PATH = Path(folder) / "db.sqlite"
        project.UPLOAD_DIR = Path(folder) / "uploads"
        project.UPLOAD_DIR.mkdir()
        try:
            project.init_db()
            conn = project.db()
            admin = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Admin", "admin@chapter.test", "hash", "admin", project.now()),
            ).lastrowid
            first = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Student 1", "s1@chapter.test", "hash", "student", project.now()),
            ).lastrowid
            second = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                ("Student 2", "s2@chapter.test", "hash", "student", project.now()),
            ).lastrowid
            course = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (first, "Cấu trúc dữ liệu", "CTDL999", project.now()),
            ).lastrowid
            same_course = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (second, "Cấu trúc dữ liệu", "CTDL999", project.now()),
            ).lastrowid
            other_course = conn.execute(
                "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
                (second, "Lập trình OOP", "OOP999", project.now()),
            ).lastrowid
            conn.commit()
            conn.close()

            def client_for(uid):
                client = project.app.test_client()
                with client.session_transaction() as sess:
                    sess["user_id"] = uid
                return client

            administrator = client_for(admin)
            student = client_for(first)
            peer = client_for(second)

            dashboard = administrator.get("/admin/documents")
            assert dashboard.status_code == 200
            with administrator.session_transaction() as sess:
                admin_token = sess["admin_csrf_token"]

            def admin_upload(filename, text, syllabus_flag=False, subject_id=None):
                if subject_id is None:
                    subject_id = shared_id
                return administrator.post(
                    "/admin/documents",
                    data={"csrf_token": admin_token,
                          "shared_subject_id": str(subject_id),
                          "is_syllabus": "1" if syllabus_flag else "0",
                          "file": (io.BytesIO(text.encode("utf-8")), filename)},
                    content_type="multipart/form-data",
                )

            conn = project.db()
            shared_id = conn.execute("""
                INSERT INTO shared_subjects(subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?,'',1,?,?)
            """, (project._normalize_subject_key("CTDL999", "Cấu trúc dữ liệu"),
                  "CTDL999", "Cấu trúc dữ liệu", project.now(), project.now())).lastrowid
            wrong_shared_id = conn.execute("""
                INSERT INTO shared_subjects(subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?,'',1,?,?)
            """, (project._normalize_subject_key("OOP999", "Lập trình OOP"),
                  "OOP999", "Lập trình OOP", project.now(), project.now())).lastrowid
            conn.commit()
            conn.close()

            assert admin_upload("official.txt", syllabus, True).status_code in (302, 303)
            # Accidental "official syllabus" checkbox on a chapter-only slide
            # must never replace an already accepted full-course outline.
            blocked = admin_upload("wrongly_marked_syllabus.txt", slide_text, True)
            assert blocked.status_code in (302, 303)
            assert "chưa có ít nhất 2" in administrator.get(
                blocked.headers["Location"]).get_data(as_text=True)
            conn = project.db()
            official = conn.execute(
                "SELECT original_name FROM shared_documents WHERE shared_subject_id=? AND is_syllabus=1",
                (shared_id,),
            ).fetchone()
            assert official["original_name"] == "official.txt"
            assert conn.execute(
                "SELECT COUNT(*) FROM shared_documents WHERE original_name=?",
                ("wrongly_marked_syllabus.txt",),
            ).fetchone()[0] == 0
            conn.close()
            assert admin_upload("chapter2.txt", slide_text).status_code in (302, 303)
            assert admin_upload("wrong_course.txt", slide_text, subject_id=wrong_shared_id).status_code in (302, 303)
            conn = project.db()
            doc = conn.execute(
                "SELECT * FROM shared_documents WHERE original_name='chapter2.txt'",
            ).fetchone()
            wrong_doc = conn.execute(
                "SELECT * FROM shared_documents WHERE original_name='wrong_course.txt'",
            ).fetchone()
            assert doc and wrong_doc
            doc_id = doc["id"]
            conn.close()

            admin_view = administrator.get(f"/admin/documents/{doc_id}/chapters")
            assert admin_view.status_code == 200
            page = admin_view.get_data(as_text=True)
            assert "Chương 2. Danh sách liên kết" in page
            assert "Phân tích bằng AI" in page
            assert "So khớp từ khóa" in page  # Lexical fallback is not AI.
            # Mock the existing external AI call; tests must never spend tokens
            # or require an actual API key. Invalid and fabricated quotes are dropped.
            original_ai_backend = project.gemini_generate
            ai_called = []
            def fake_ai_response(prompt):
                ai_called.append(prompt)
                return (json.dumps({"suggestions": [
                    {"chapter_key": "2", "evidence":
                     "2.1. Danh sách liên kết đơn chứa node và con trỏ next."},
                    {"chapter_key": "1", "evidence": "Không có câu này trong file."},
                    {"chapter_key": "99", "evidence":
                     "2.1. Danh sách liên kết đơn chứa node và con trỏ next."}
                ]}, ensure_ascii=False), None)
            try:
                project.gemini_generate = fake_ai_response
                analyzed = administrator.post(
                    f"/admin/documents/{doc_id}/chapters",
                    data={"csrf_token": admin_token, "action": "analyze_ai"},
                )
                assert analyzed.status_code == 303
            finally:
                project.gemini_generate = original_ai_backend
            assert ai_called and "Danh sách liên kết" in ai_called[0]
            ai_html = administrator.get(
                f"/admin/documents/{doc_id}/chapters").get_data(as_text=True)
            assert "AI đề xuất từ nội dung tài liệu" in ai_html
            assert "Bằng chứng AI trích từ file" in ai_html
            assert "Không có câu này trong file" not in ai_html
            conn = project.db()
            stored_ai = conn.execute(
                "SELECT suggestions_json FROM shared_document_ai_suggestions WHERE document_id=?",
                (doc_id,),
            ).fetchone()
            assert stored_ai and len(json.loads(stored_ai["suggestions_json"])) == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM shared_document_chapters",
            ).fetchone()[0] == 0  # AI must not approve automatically.
            conn.close()
            assert student.get(f"/admin/documents/{doc_id}/chapters").status_code == 403
            assert administrator.post(
                f"/admin/documents/{doc_id}/chapters",
                data={"chapters": ["2"]},
            ).status_code == 403
            assert administrator.post(
                f"/admin/documents/{doc_id}/chapters",
                data={"csrf_token": admin_token, "chapters": ["99"]},
            ).status_code == 400

            # No approved documents before an explicit Admin confirmation.
            conn = project.db()
            assert conn.execute(
                "SELECT COUNT(*) FROM shared_document_chapters",
            ).fetchone()[0] == 0
            conn.close()

            assert administrator.post(
                f"/admin/documents/{doc_id}/chapters",
                data={"csrf_token": admin_token, "chapters": ["1", "2"]},
            ).status_code == 303
            conn = project.db()
            mappings = conn.execute(
                "SELECT chapter_key FROM shared_document_chapters WHERE document_id=? ORDER BY chapter_key",
                (doc_id,),
            ).fetchall()
            assert [x["chapter_key"] for x in mappings] == ["1", "2"]
            conn.close()

            # Student must confirm official syllabus before chapter is available.
            cannot_study = student.get(f"/subjects/{course}/chapters/2")
            assert cannot_study.status_code == 303
            page = student.get(f"/subjects/{course}/syllabus")
            assert page.status_code == 200
            with student.session_transaction() as sess:
                student_token = sess["syllabus_csrf_token"]
            assert student.post(
                f"/subjects/{course}/syllabus",
                data={"csrf_token": student_token, "action": "analyze"},
            ).status_code == 303
            assert student.post(
                f"/subjects/{course}/syllabus",
                data={"csrf_token": student_token, "action": "confirm",
                      "include_0": "1", "title_0": "Chương 1. Tổng quan và giải thuật",
                      "include_1": "1", "title_1": "Chương 2. Danh sách liên kết"},
            ).status_code == 303
            chapter = student.get(f"/subjects/{course}/chapters/2")
            assert chapter.status_code == 200, chapter.get_data(as_text=True)[:500]
            html = chapter.get_data(as_text=True)
            assert "chapter2.txt" in html and "Đọc tài liệu gốc" in html
            assert "2.1. Danh sách liên kết đơn" in html
            assert "BT02:" in html
            assert "wrong_course.txt" not in html
            assert f"/shared-documents/{wrong_doc['id']}/file" not in html
            # A roadmap generated BEFORE an Admin's later approval still shows
            # approved files dynamically without mixing other-course documents.
            plan_post = student.post(
                f"/subjects/{course}/learning-path",
                data={"csrf_token": student_token, "action": "generate"},
            )
            assert plan_post.status_code == 303
            roadmap = student.get(f"/subjects/{course}/learning-path")
            assert roadmap.status_code == 200
            roadmap_html = roadmap.get_data(as_text=True)
            assert "chapter2.txt" in roadmap_html
            assert "Admin đã duyệt" in roadmap_html
            assert "wrong_course.txt" not in roadmap_html
            # Chapter-specific AI tutor: a real source quote is required;
            # invalid citation or another course's document cannot be used.
            source_quote = "2.1. Danh sách liên kết đơn chứa node và con trỏ next."
            original_ai_backend = project.gemini_generate
            tutor_prompts = []
            def fake_tutor(prompt):
                tutor_prompts.append(prompt)
                return (json.dumps({
                    "explanation": "Danh sách liên kết đơn gồm các node nối nhau qua next.",
                    "citations": [{"source_key": "T1", "quote": source_quote}],
                    "practice": "Hãy mô tả quá trình chèn node vào đầu danh sách.",
                }, ensure_ascii=False), None)
            try:
                project.gemini_generate = fake_tutor
                lesson = student.post(
                    f"/subjects/{course}/chapters/2",
                    data={"csrf_token": student_token, "action": "teach",
                          "topic_index": "0", "question": "Giải thích về node."},
                )
                assert lesson.status_code == 200, lesson.get_data(as_text=True)[:500]
                lesson_html = lesson.get_data(as_text=True)
                assert "Bài giảng AI" in lesson_html and source_quote in lesson_html
                assert "chapter2.txt" in lesson_html
                assert "wrong_course.txt" not in tutor_prompts[-1]
                assert "2.1. Danh sách liên kết đơn" in tutor_prompts[-1]
                assert "Giải thích về node." in tutor_prompts[-1]
                assert student.post(
                    f"/subjects/{course}/chapters/2",
                    data={"action": "teach", "topic_index": "0"},
                ).status_code == 403
                assert student.post(
                    f"/subjects/{course}/chapters/2",
                    data={"csrf_token": student_token, "action": "teach",
                          "topic_index": "99"},
                ).status_code == 400
                assert peer.post(
                    f"/subjects/{course}/chapters/2",
                    data={"csrf_token": student_token, "action": "teach",
                          "topic_index": "0"},
                ).status_code == 404

                def fabricated_tutor(prompt):
                    return (json.dumps({
                        "explanation": "Một kiến thức không có trong bài.",
                        "citations": [{"source_key": "T1",
                                       "quote": "Trích dẫn này hoàn toàn do AI tự bịa."}],
                        "practice": "Một bài tập bịa đặt.",
                    }, ensure_ascii=False), None)
                project.gemini_generate = fabricated_tutor
                unsupported = student.post(
                    f"/subjects/{course}/chapters/2",
                    data={"csrf_token": student_token, "action": "teach",
                          "topic_index": "0"},
                ).get_data(as_text=True)
                assert "chưa trả được bài giảng có dẫn chứng" in unsupported
                assert "Một kiến thức không có trong bài" not in unsupported
            finally:
                project.gemini_generate = original_ai_backend
            assert student.get(f"/subjects/{course}/chapters/3").status_code == 404
            assert peer.get(f"/subjects/{course}/chapters/2").status_code == 404
            assert administrator.get(f"/subjects/{course}/chapters/2").status_code == 403

            # Same shared course for another student, but each confirms own syllabus.
            peer.get(f"/subjects/{same_course}/syllabus")
            with peer.session_transaction() as sess:
                peer_token = sess["syllabus_csrf_token"]
            peer.post(f"/subjects/{same_course}/syllabus",
                      data={"csrf_token": peer_token, "action": "analyze"})
            peer.post(f"/subjects/{same_course}/syllabus",
                      data={"csrf_token": peer_token, "action": "confirm",
                            "include_0": "1", "title_0": "Chương 1. Tổng quan và giải thuật",
                            "include_1": "1", "title_1": "Chương 2. Danh sách liên kết"})
            assert "chapter2.txt" in peer.get(
                f"/subjects/{same_course}/chapters/2").get_data(as_text=True)
            assert peer.get(f"/subjects/{other_course}/chapters/2").status_code == 303

            # Removing the approval instantly stops student access to chapter mapping
            # without deleting the actual shared document.
            assert administrator.post(
                f"/admin/documents/{doc_id}/chapters",
                data={"csrf_token": admin_token, "chapters": []},
            ).status_code == 303
            html = student.get(f"/subjects/{course}/chapters/2").get_data(as_text=True)
            assert "chưa có học liệu chung" in html.lower()
            assert "chapter2.txt" not in html
            # Revoked files are unavailable to the tutor on subsequent requests.
            before_tutor = student.post(
                f"/subjects/{course}/chapters/2",
                data={"csrf_token": student_token, "action": "teach", "topic_index": "0"},
            ).get_data(as_text=True)
            assert "chưa có học liệu chung" in before_tutor.lower() or "chưa có học liệu chung" in html.lower()
            assert "AI chưa thể giảng bài" in before_tutor
            # Revoked approval must disappear from an already persisted roadmap.
            roadmap_after_revocation = student.get(
                f"/subjects/{course}/learning-path").get_data(as_text=True)
            assert "chapter2.txt" not in roadmap_after_revocation

            # Approving and then changing the official syllabus invalidates approval.
            assert administrator.post(
                f"/admin/documents/{doc_id}/chapters",
                data={"csrf_token": admin_token, "chapters": ["2"]},
            ).status_code == 303
            conn = project.db()
            conn.execute(
                "UPDATE shared_documents SET extracted_text=extracted_text || ? WHERE shared_subject_id=? AND is_syllabus=1",
                ("\nChương 3. Cây", shared_id),
            )
            conn.commit()
            conn.close()
            assert student.get(f"/subjects/{course}/chapters/2").status_code == 303

            # Confirming new syllabus still must NOT automatically restore approvals
            # created against the old hash.
            student.post(f"/subjects/{course}/syllabus",
                         data={"csrf_token": student_token, "action": "analyze"})
            student.post(f"/subjects/{course}/syllabus",
                         data={"csrf_token": student_token, "action": "confirm",
                               "include_0": "1", "title_0": "Chương 1. Tổng quan và giải thuật",
                               "include_1": "1", "title_1": "Chương 2. Danh sách liên kết"})
            html = student.get(f"/subjects/{course}/chapters/2").get_data(as_text=True)
            assert "chapter2.txt" not in html

            excerpts = evidence_excerpt(slide_text, {
                "chapter": "Chương 2. Danh sách liên kết",
                "topics": ["2.1. Danh sách liên kết đơn", "2.2. Thêm xóa node"]
            })
            assert excerpts and all(line in slide_text for line in excerpts)
            print("Chapter materials: Admin review, multi-mapping, student isolation, stale source OK")
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_db, old_dir


if __name__ == "__main__":
    check()
