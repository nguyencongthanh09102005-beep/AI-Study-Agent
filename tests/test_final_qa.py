"""Final-demo regression checks; run after SQLite init in CI."""
import json
import re
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

# Dùng được cả 'python -m tests...' lẫn chạy trực tiếp file tests/...
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def check_quiz_generation():
    original = project.gemini_generate
    try:
        # An unavailable model must not produce unrelated fill-in-the-blank quizzes.
        project.gemini_generate = lambda prompt: (None, "offline test")
        assert project.build_quiz("Đám mây hỗ trợ cung cấp tài nguyên điện toán.", 10) == []

        def fake_ai(prompt):
            count_match = re.search(r"Tạo đúng (\d+) câu", prompt)
            group_match = re.search(r"cho NHÓM (\d+)", prompt)
            assert count_match and group_match, "Quiz prompt format changed"
            n = int(count_match.group(1))
            group = int(group_match.group(1))
            questions = [
                {
                    "question": f"CI question group {group}, item {i}?",
                    "topic": "Điện toán đám mây",
                    "chapter": "Chương 1",
                    "options": [f"Đúng {group}-{i}", "Sai một", "Sai hai", "Sai ba"],
                    "answer": 0,
                }
                for i in range(n)
            ]
            return json.dumps(questions, ensure_ascii=False), None

        project.gemini_generate = fake_ai
        for count in (10, 20, 30):
            questions = project.build_quiz("Kiến thức điện toán đám mây.", count)
            assert len(questions) == count, f"Wrong count: {count}"
            assert len({q["question"] for q in questions}) == count
            for i, q in enumerate(questions):
                group = i // 10 + 1
                position = i % 10
                assert q["options"][q["answer"]] == f"Đúng {group}-{position}"
                assert len({option.casefold() for option in q["options"]}) == 4
                assert 0 <= q["answer"] < 4

        # Gemini trả đáp án trùng nhau hoặc thiếu câu: tuyệt đối không lưu quiz giả.
        project.gemini_generate = lambda prompt: (json.dumps([{
            "question": "Câu thiếu chất lượng?",
            "topic": "Kiến thức nền", "chapter": "Chương 1",
            "options": ["Trùng", "Trùng", "Sai 2", "Sai 3"],
            "answer": 0,
        }]), None)
        assert project.build_quiz("Kiến thức điện toán đám mây.", 10) == []
    finally:
        project.gemini_generate = original


def check_adaptive_delete():
    client = project.app.test_client()
    assert client.get("/api/mobile/session").status_code == 401
    response = client.post("/api/mobile/register", json={
        "name": "Final QA User",
        "email": "finalqa-20261024@study.local",
        "password": "ci-sample-password",
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    assert client.get("/api/mobile/session").status_code == 200

    response = client.post("/api/mobile/subjects", json={
        "name": "CI QA Cloud", "code": "CI-FINAL-QA", "credits": 3,
        "target_score": 8,
    })
    assert response.status_code == 201, response.get_data(as_text=True)
    subject_id = response.get_json()["subject"]["id"]
    user_id = client.get("/api/mobile/session").get_json()["user"]["id"]
    conn = project.db()
    quiz_id = conn.execute(
        """INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
           VALUES(?,?,?,?,?,?)""",
        (user_id, subject_id, None, "Final QA Quiz",
         json.dumps([{
             "question": "Mô hình nào đúng?",
             "topic": "Cloud Security",
             "chapter": "Chương 2",
             "options": ["Đúng", "Sai 1", "Sai 2", "Sai 3"],
             "answer": 0,
         }]), project.now()),
    ).lastrowid
    conn.commit()
    conn.close()

    question = client.get(f"/api/mobile/quizzes/{quiz_id}").get_json()["questions"][0]
    assert "answer" not in question
    wrong = client.post("/api/mobile/quiz/submit", json={
        "quiz_id": quiz_id, "answers": [1],
    })
    assert wrong.status_code == 200, wrong.get_data(as_text=True)
    assert wrong.get_json()["weakness_count"] == 1
    assert wrong.get_json()["adaptive_task"] is not None

    deleted = client.post(f"/quiz/{quiz_id}/delete")
    assert deleted.status_code in (302, 303)
    conn = project.db()
    assert conn.execute(
        "SELECT COUNT(*) FROM learning_weaknesses WHERE user_id=? AND subject_id=?",
        (user_id, subject_id),
    ).fetchone()[0] == 0
    assert conn.execute(
        """SELECT COUNT(*) FROM study_tasks
           WHERE user_id=? AND subject_id=? AND source='adaptive' AND done=0""",
        (user_id, subject_id),
    ).fetchone()[0] == 0
    conn.close()


def check_upload_limit():
    """Ensure oversized uploads show a human-readable Web error and JSON for mobile."""
    client = project.app.test_client()
    registered = client.post("/api/mobile/register", json={
        "name": "Upload Size QA",
        "email": "upload-limit-qa@study.local",
        "password": "ci-sample-password",
    })
    assert registered.status_code == 201

    original_limit = project.app.config["MAX_CONTENT_LENGTH"]
    try:
        project.app.config["MAX_CONTENT_LENGTH"] = 1024
        web_response = client.post(
            "/documents",
            data={"file": (BytesIO(b"x" * 2048), "oversized.txt")},
            content_type="multipart/form-data",
        )
        assert web_response.status_code == 303
        assert "upload_error=too_large" in web_response.headers["Location"]

        mobile_response = client.post(
            "/api/mobile/documents",
            data={"file": (BytesIO(b"x" * 2048), "oversized.txt")},
            content_type="multipart/form-data",
        )
        assert mobile_response.status_code == 413
        payload = mobile_response.get_json()
        assert payload and "max_upload_mb" in payload
        assert "error" in payload
    finally:
        project.app.config["MAX_CONTENT_LENGTH"] = original_limit

    # Neither failed request must persist a document.
    docs = client.get("/api/mobile/documents")
    assert docs.status_code == 200
    assert docs.get_json()["documents"] == []
    page = client.get("/documents?upload_error=too_large")
    assert page.status_code == 200
    assert "Tệp vừa chọn vượt giới hạn" in page.get_data(as_text=True)


def check_web_auth_forms():
    """Three reveal controls render; login and registration continue to work."""
    client = project.app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "auth-password.css" in html
    assert "auth-password.js" in html
    assert html.count('class="auth-password-field"') == 3
    assert html.count('class="password-toggle"') == 3

    for field_id in ("loginPassword", "signupPassword", "confirmPassword"):
        assert html.count(f'id="{field_id}"') == 1
        assert f'<label for="{field_id}">' in html
        assert f'data-target="{field_id}"' in html
        assert f'aria-controls="{field_id}"' in html
    assert "eye-icon-show" in html and "eye-icon-hide" in html

    email = "ci-auth-password-qa@study.local"
    mismatch = client.post("/register", data={
        "name": "Test Account",
        "email": email,
        "password": "test-password-123",
        "confirm_password": "does-not-match",
    })
    assert mismatch.status_code in (302, 303)
    assert "tab=signup" in mismatch.headers["Location"]
    conn = project.db()
    assert conn.execute(
        "SELECT id FROM users WHERE email=?", (email,)
    ).fetchone() is None
    conn.close()

    registered = client.post("/register", data={
        "name": "Test Account",
        "email": email,
        "password": "test-password-123",
        "confirm_password": "test-password-123",
    })
    assert registered.status_code in (302, 303)
    assert "/dashboard" in registered.headers["Location"]
    assert client.get("/dashboard").status_code == 200
    client.get("/logout")

    failed_login = client.post("/login", data={
        "email": email, "password": "not-the-password",
    })
    assert failed_login.status_code == 200
    assert "Email hoặc mật khẩu không đúng" in failed_login.get_data(as_text=True)

    login = client.post("/login", data={
        "email": email, "password": "test-password-123",
    })
    assert login.status_code in (302, 303)
    assert "/dashboard" in login.headers["Location"]


if __name__ == "__main__":
    # Isolated temporary DB: safe to run repeatedly without altering real learner data.
    old_db_path, old_upload_dir = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as directory:
            project.DB_PATH = Path(directory) / "final_qa.db"
            project.UPLOAD_DIR = Path(directory) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            check_quiz_generation()
            check_adaptive_delete()
            check_upload_limit()
            check_web_auth_forms()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db_path, old_upload_dir
    print("Final QA checks passed")
