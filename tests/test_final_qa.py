"""Final-demo regression checks; run after SQLite init in CI."""
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory
import app as project


def check_quiz_generation():
    original = project.gemini_generate
    try:
        # An unavailable model must not produce unrelated fill-in-the-blank quizzes.
        project.gemini_generate = lambda prompt: (None, "offline test")
        assert project.build_quiz("Đám mây hỗ trợ cung cấp tài nguyên điện toán.", 10) == []

        def fake_ai(prompt):
            n = int(re.search(r"Tạo đúng (\d+) câu", prompt).group(1))
            questions = [
                {
                    "question": f"Kiểm tra QA {i}?",
                    "topic": "Điện toán đám mây",
                    "chapter": "Chương 1",
                    "options": [f"Đúng {i}", "Sai một", "Sai hai", "Sai ba"],
                    "answer": 0,
                }
                for i in range(n)
            ]
            return json.dumps(questions, ensure_ascii=False), None

        project.gemini_generate = fake_ai
        questions = project.build_quiz("Kiến thức điện toán đám mây.", 10)
        assert len(questions) == 10
        for i, q in enumerate(questions):
            assert q["options"][q["answer"]] == f"Đúng {i}"
            assert len(set(q["options"])) == 4
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
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db_path, old_upload_dir
    print("Final QA checks passed")
