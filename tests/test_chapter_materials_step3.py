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
    # Whole-chapter evidence retrieval must reach relevant text even when it
    # appears past the first several thousand characters of an approved file.
    from chapter_tutor import prepared_sources
    long_document = (
        ("Giới thiệu kiến thức mảng và truy cập theo chỉ số. " * 300)
        + "\\nGiải thích node, head và con trỏ next trong danh sách liên kết. "
        + "Mỗi node gồm dữ liệu và tham chiếu tới node kế tiếp."
    )
    extracted = prepared_sources([{
        "id": 900, "original_name": "chuong2.txt",
        "extracted_text": long_document
    }], question="node head next")
    assert extracted and any(
        "Mỗi node gồm dữ liệu" in source["excerpt"]
        for source in extracted
    ), "Relevant chapter text after the file prefix was not retrieved."

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
            # Existing Chat AI is the ONLY tutor entrypoint. Link from chapter
            # selects this same per-course conversation with a scoped context.
            assert "Học cùng AI trong Chat AI" in html
            assert 'name="chapter_number" value="2"' in html
            assert student.post(f"/subjects/{course}/chapters/2").status_code == 405

            # UI stage 1: remove duplicated greeting, expose the new scoped
            # stylesheet, and show human-readable subject names in Chat AI.
            chat_view = student.get("/chat")
            assert chat_view.status_code == 200
            chat_html = chat_view.get_data(as_text=True)
            assert "css/chat_stage1.css" in chat_html
            assert "Xin chào! 👋" not in chat_html
            assert "Thoát chế độ chương" not in chat_html
            assert "chat-welcome-strip" not in chat_html
            css_text = (Path(__file__).resolve().parents[1] /
                        "static/css/chat_stage1.css").read_text(encoding="utf-8")
            assert "max-width: min(100%, 1100px)" in css_text
            assert "max-height: none !important" in css_text
            assert "overflow-y: auto !important" in css_text
            # UI stage 2: single sidebar course list and exact 30/70 split.
            # Do not reintroduce a redundant chat-history column.
            assert "css/chat_stage2.css" in chat_html
            assert 'class="sidebar-course-list"' in chat_html
            assert chat_html.count('class="chat-history-list"') == 1
            assert 'class="soft-card chat-history-panel"' not in chat_html
            assert 'id="chatMobileSubject"' in chat_html
            ui_css = (Path(__file__).resolve().parents[1] /
                      "static/css/chat_stage2.css").read_text(encoding="utf-8")
            assert "grid-template-columns: 30% minmax(0,70%)" in ui_css
            assert "width: 30% !important" in ui_css
            assert "grid-template-columns: minmax(0,1fr)" in ui_css
            assert "prefers-reduced-motion: reduce" in ui_css
            js_code = (Path(__file__).resolve().parents[1] /
                       "static/js/chat.js").read_text(encoding="utf-8")
            assert "rememberSelectedSubject(chat.subject_id)" in js_code
            assert "if (Number(currentChatId) !== Number(chatId)) return;" in js_code
            assert "mobileSubjectPicker" in js_code
            # Stage 3+: 2 modes and real course/chapter selector, no
            # duplicate chatbot or fake syllabus values in the UI.
            assert "css/chat_stage3.css" in chat_html
            assert "js/chat_format.js" in chat_html
            assert "id=\"chatModeFree\"" in chat_html
            assert "id=\"chatModeChapter\"" in chat_html
            assert "id=\"chatCourseSelect\"" in chat_html
            assert "id=\"chatChapterSelect\"" in chat_html
            assert "id=\"chatTopicSelect\"" not in chat_html
            assert "chat-mode-panel" in chat_html
            # Layout refinement: account/logout live at sidebar bottom,
            # the redundant V2 card is gone, and Chat can occupy viewport top.
            assert "sidebar-account-card" in chat_html
            assert "Study Agent V2" not in chat_html
            assert 'class="user-chip"' not in chat_html
            assert "css/sidebar_account.css" in chat_html
            assert 'id="chatLessonSummary"' in chat_html
            assert 'id="chatChangeChapter"' in chat_html
            assert "chat-mobile-logout" in chat_html
            stage3_css = (Path(__file__).resolve().parents[1] /
                          "static/css/chat_stage3.css").read_text(encoding="utf-8")
            assert "body.page-chat .topbar" in stage3_css
            assert "display: none !important" in stage3_css
            assert "height: 100vh !important" in stage3_css
            assert "chat-lesson-summary[hidden]" in stage3_css
            assert "chatLessonSummaryTitle" in js_code
            assert "chapterEditorOpen" in js_code
            account_css = (Path(__file__).resolve().parents[1] /
                           "static/css/sidebar_account.css").read_text(encoding="utf-8")
            assert ".sidebar-account-card" in account_css

            assert "window.ChatMarkdown?.render(message.content)" in js_code
            assert "api/chat/course-outline" in js_code
            assert "topicSelector" not in js_code
            assert "topic_index: lessonMode.topic_index" not in js_code

            outline_url = f"/api/chat/course-outline?subject_id={course}"
            outline_resp = student.get(outline_url)
            assert outline_resp.status_code == 200, outline_resp.get_data(as_text=True)
            outline = outline_resp.get_json()
            assert outline["subject_name"] == "Cấu trúc dữ liệu"
            assert len(outline["chapters"]) == 2
            assert outline["chapters"][0]["available"] is True
            assert outline["chapters"][1]["available"] is True
            assert "2.1. Danh sách liên kết đơn" in outline["chapters"][1]["topics"]
            assert outline["chapters"][1]["source_names"] == ["chapter2.txt"]
            assert peer.get(outline_url).status_code == 404
            assert student.get(
                f"/api/chat/course-outline?subject_id={other_course}"
            ).status_code == 404
            assert student.get("/api/chat/course-outline?subject_id=abc").status_code == 400

            chats = student.get("/api/chats").get_json()
            convo = next(item for item in chats if item["subject_id"] == course)
            assert convo["title"] == "Cấu trúc dữ liệu"
            assert convo["title"] != "CTDL999"
            assert convo["id"]
            lookup = (f"/api/chat/lesson-context?subject_id={course}"
                      "&chapter_number=2&topic_index=0")
            verified = student.get(lookup)
            assert verified.status_code == 200, verified.get_data(as_text=True)[:600]
            metadata = verified.get_json()
            assert metadata["chapter_number"] == 2
            assert "2.1. Danh sách liên kết đơn" in metadata["topic"]
            # No chosen topic -> full chapter scope, with all syllabus topics.
            chapter_only_lookup = (
                f"/api/chat/lesson-context?subject_id={course}&chapter_number=2"
            )
            chapter_only = student.get(chapter_only_lookup)
            assert chapter_only.status_code == 200
            chapter_meta = chapter_only.get_json()
            assert chapter_meta["topic_index"] is None
            assert chapter_meta["chapter"] == "Chương 2. Danh sách liên kết"
            assert len(chapter_meta["topics"]) == 2
            assert chapter_meta["source_names"] == ["chapter2.txt"]
            assert metadata["source_names"] == ["chapter2.txt"]
            assert peer.get(lookup).status_code == 404
            assert student.get(
                f"/api/chat/lesson-context?subject_id={course}"
                "&chapter_number=99&topic_index=0"
            ).status_code == 400

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
            payload = {
                "conversation_id": convo["id"],
                "question": "Giải thích về node.",
                "lesson": {"chapter_number": 2, "topic_index": 0},
            }
            try:
                project.gemini_generate = fake_tutor
                overlong = student.post("/api/chat", json={
                    **payload, "question": "x" * 501
                })
                assert overlong.status_code == 400
                assert "500 ký tự" in overlong.get_json()["error"]
                tutored = student.post("/api/chat", json=payload)
                assert tutored.status_code == 200, tutored.get_data(as_text=True)[:700]
                response = tutored.get_json()
                assert response["source_mode"] == "chapter"
                assert "chapter2.txt" in response["sources"]
                assert source_quote in response["answer"]
                assert response["lesson"]["chapter_number"] == 2
                assert "2.1. Danh sách liên kết đơn" in tutor_prompts[-1]
                assert "wrong_course.txt" not in tutor_prompts[-1]
                assert "Giải thích về node." in tutor_prompts[-1]

                # Follow-up uses the SAME chat conversation and its history.
                followup = student.post("/api/chat", json={
                    **payload, "question": "Còn phần next thì sao?"
                })
                assert followup.status_code == 200
                assert "Giải thích về node." in tutor_prompts[-1]
                history = student.get(
                    f'/api/chats/{convo["id"]}/messages'
                ).get_json()
                assert len(history) == 4
                assert history[-1]["role"] == "assistant"

                # Stage 4: switching chapters does NOT feed the previous
                # chapter's conversation turns to the AI as source context.
                chapter_one = student.post("/api/chat", json={
                    **payload,
                    "question": "Chương một chỉ tập trung Big O",
                    "lesson": {"chapter_number": 1, "topic_index": 0},
                })
                assert chapter_one.status_code == 200
                assert "Chương 1. Tổng quan" in tutor_prompts[-1]
                assert "Giải thích về node." not in tutor_prompts[-1]

                back_to_two = student.post("/api/chat", json={
                    **payload, "question": "Quay lại liên kết đơn"
                })
                assert back_to_two.status_code == 200
                assert "Giải thích về node." in tutor_prompts[-1]
                assert "Chương một chỉ tập trung Big O" not in tutor_prompts[-1]

                # Free mode remains in the SAME thread but cannot become a
                # source for the chapter-scoped AI prompt.
                original_free_backend = project.gemini_subject_answer
                free_histories = []
                def fake_free_backend(name, question, personal, personal_files,
                                      history, shared, profile, shared_files):
                    free_histories.append(history)
                    return "Trả lời tự do", [], "general"
                try:
                    project.gemini_subject_answer = fake_free_backend
                    normal = student.post("/api/chat", json={
                        "conversation_id": convo["id"],
                        "question": "Hỏi đáp tự do về môn học."
                    })
                    assert normal.status_code == 200
                    assert normal.get_json()["source_mode"] == "general"
                    assert "Chương một chỉ tập trung Big O" not in free_histories[-1]
                    assert "Giải thích về node." not in free_histories[-1]
                finally:
                    project.gemini_subject_answer = original_free_backend

                after_free = student.post("/api/chat", json={
                    **payload, "question": "Tiếp tục phần danh sách liên kết."
                })
                assert after_free.status_code == 200
                assert "Giải thích về node." in tutor_prompts[-1]
                assert "Hỏi đáp tự do về môn học." not in tutor_prompts[-1]
                history = student.get(
                    f'/api/chats/{convo["id"]}/messages'
                ).get_json()
                assert len(history) == 12
                conn = project.db()
                from chat_lesson_memory import (
                    history_for_mode, approved_source_signature,
                )
                contexts = conn.execute("""
                    SELECT mode,chapter_number,topic_index,source_signature
                    FROM chat_message_contexts
                    WHERE user_id=? AND conversation_id=? ORDER BY message_id
                """, (first, convo["id"])).fetchall()
                assert len(contexts) == 12
                assert {x["mode"] for x in contexts} == {"chapter", "free"}
                from chapter_chat_context import resolve_lesson_context
                active = resolve_lesson_context(project, conn, first, course, 2, 0)
                assert len(history_for_mode(
                    conn, first, convo["id"], active
                )) == 8
                changed = dict(active)
                changed["source_signature"] = approved_source_signature(
                    "different-source-version",
                    active["sources"]
                )
                assert not history_for_mode(conn, first, convo["id"], changed)
                # A chapter-only request must naturally cover both 2.1
                # and 2.2, without requiring the UI to choose a subtopic.
                question_mang = "Giải thích thao tác trên mảng trong chương 2."
                whole_lesson = {"chapter_number": 2}
                chapter_answer = student.post("/api/chat", json={
                    "conversation_id": convo["id"], "question": question_mang,
                    "lesson": whole_lesson,
                })
                assert chapter_answer.status_code == 200
                assert chapter_answer.get_json()["lesson"]["topic_index"] is None
                assert "2.1. Danh sách liên kết đơn" in tutor_prompts[-1]
                assert "2.2. Thêm xóa node" in tutor_prompts[-1]
                assert "Chương một chỉ tập trung Big O" not in tutor_prompts[-1]
                assert "Giải thích về node." not in tutor_prompts[-1]
                chapter_followup = student.post("/api/chat", json={
                    "conversation_id": convo["id"],
                    "question": "Còn node và next trong chương này?",
                    "lesson": whole_lesson,
                })
                assert chapter_followup.status_code == 200
                assert question_mang in tutor_prompts[-1]
                assert chapter_followup.get_json()["lesson"]["topic_index"] is None

                conn = project.db()
                chapter_a = resolve_lesson_context(
                    project, conn, first, course, 2, question="mảng"
                )
                chapter_b = resolve_lesson_context(
                    project, conn, first, course, 2, question="next"
                )
                assert chapter_a["source_signature"] == chapter_b["source_signature"]
                assert chapter_a["topic_index"] is None
                assert len(history_for_mode(
                    conn, first, convo["id"], chapter_b
                )) == 4
                # Topic-scoped legacy data must stay visible, but not silently
                # become chapter-only prompt memory.
                assert question_mang not in "\n".join(
                    row["content"] for row in history_for_mode(
                        conn, first, convo["id"], active
                    )
                )
                conn.close()
                assert len(student.get(
                    f'/api/chats/{convo["id"]}/messages'
                ).get_json()) == 16

                assert student.post("/api/chat", json={
                    **payload, "lesson": {"chapter_number": 2, "topic_index": 99}
                }).status_code == 400
                assert peer.post("/api/chat", json=payload).status_code == 404

                def fabricated_tutor(prompt):
                    return (json.dumps({
                        "explanation": "Một kiến thức không có trong bài.",
                        "citations": [{"source_key": "T1",
                                       "quote": "Trích dẫn này hoàn toàn do AI tự bịa."}],
                        "practice": "Một bài tập bịa đặt.",
                    }, ensure_ascii=False), None)
                project.gemini_generate = fabricated_tutor
                unsupported = student.post("/api/chat", json=payload)
                assert unsupported.status_code == 502
                assert "Một kiến thức không có trong bài" not in str(
                    unsupported.get_json()
                )
                assert len(student.get(
                    f'/api/chats/{convo["id"]}/messages'
                ).get_json()) == 16

                # Admin can revoke an approved file while AI is generating.
                # The answer must not be shown or saved if that happens.
                def revoke_during_ai(prompt):
                    db_conn = project.db()
                    db_conn.execute(
                        "DELETE FROM shared_document_chapters WHERE document_id=?",
                        (doc_id,)
                    )
                    db_conn.commit()
                    db_conn.close()
                    return (json.dumps({
                        "explanation": "Bài giảng bị thu hồi trước khi lưu.",
                        "citations": [{"source_key": "T1", "quote": source_quote}],
                        "practice": "Không được gửi."
                    }, ensure_ascii=False), None)
                project.gemini_generate = revoke_during_ai
                stale_answer = student.post("/api/chat", json=payload)
                assert stale_answer.status_code == 409
                assert "thay đổi" in stale_answer.get_json()["error"]
                assert len(student.get(
                    f'/api/chats/{convo["id"]}/messages'
                ).get_json()) == 16
                # Restore approval for the remaining existing regression cases.
                assert administrator.post(
                    f"/admin/documents/{doc_id}/chapters",
                    data={"csrf_token": admin_token, "chapters": ["1", "2"]},
                ).status_code == 303
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
            # Revoked files must disappear from Chat AI's chapter context.
            unavailable = student.get(lookup)
            assert unavailable.status_code == 409
            blocked = student.post("/api/chat", json=payload)
            assert blocked.status_code == 409
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
            assert student.get(lookup).status_code == 409

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
