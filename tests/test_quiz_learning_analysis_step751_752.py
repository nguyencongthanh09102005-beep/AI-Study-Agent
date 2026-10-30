"""Phase 7.5.1/7.5.2 regression: score, weakness, idempotency, analysis, ACL.

Uses one isolated temporary database and no Gemini calls.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from quiz_learning_analysis import summarize_quiz_attempt


def login(client, uid):
    with client.session_transaction() as sess:
        sess.clear()
        sess["user_id"] = uid


def check():
    questions = [
        {"question": "Câu đầu tiên: cơ sở 1?", "chapter": "Chương 1",
         "topic": "Khái niệm", "answer": 0,
         "options": ["A", "B", "C", "D"]},
        {"question": "Câu thứ hai: cơ sở 2?", "chapter": "Chương 1",
         "topic": "Khái niệm", "answer": 1,
         "options": ["A", "B", "C", "D"]},
        {"question": "Câu thứ ba: phân tích?", "chapter": "Chương 1",
         "topic": "Vận dụng", "answer": 2,
         "options": ["A", "B", "C", "D"]},
        {"question": "Câu thứ tư: so sánh?", "chapter": "Chương 2",
         "topic": "So sánh", "answer": 3,
         "options": ["A", "B", "C", "D"]},
    ]
    analysis = summarize_quiz_attempt(questions, [0, 0, 0, 3])
    assert (analysis["total"], analysis["correct"], analysis["incorrect"]) == (4, 2, 2)
    assert analysis["unverifiable"] == 0
    assert [(row["name"], row["correct"], row["incorrect"])
            for row in analysis["chapters"]] == [
                ("Chương 1", 1, 2), ("Chương 2", 1, 0)]
    by_topic = {row["name"]: row for row in analysis["topics"]}
    assert by_topic["Khái niệm"]["total"] == 2
    assert by_topic["Khái niệm"]["percent"] == 50
    assert by_topic["Vận dụng"]["percent"] == 0
    assert by_topic["So sánh"]["percent"] == 100
    assert len(analysis["needs_review"]) == 2
    assert "correct_answers" not in analysis
    assert "Câu đầu tiên" not in json.dumps(analysis, ensure_ascii=False)

    # Real-life screenshot regression: one physical chapter is spelled two
    # ways in 15 AI questions. It must produce one chapter bar of 3/15=20%.
    verbose = "CHƯƠNG 1: SỰ RA ĐỜI CỦA ĐẢNG & PHONG TRÀO ĐẤU TRANH GIÀNH CHÍNH QUYỀN (1858 - 1945)"
    screenshot_questions = [
        {
            "question": f"Câu lịch sử thứ {index}?",
            "chapter": verbose if index < 10 else "CHƯƠNG 1",
            "topic": (verbose + " · Chuyển biến xã hội Việt Nam"
                      if index < 6 else
                      "CHƯƠNG 1 · Lực lượng cách mạng"
                      if index < 10 else
                      "Nguyên nhân thất bại phong trào"),
            "answer": 0,
        }
        for index in range(15)
    ]
    screenshot_answers = [0] * 3 + [1] * 12
    screenshot = summarize_quiz_attempt(screenshot_questions,
                                        screenshot_answers)
    assert (screenshot["correct"], screenshot["incorrect"]) == (3, 12)
    assert len(screenshot["chapters"]) == 1, screenshot["chapters"]
    assert screenshot["chapters"][0] == {
        "name": "Chương 1", "correct": 3, "incorrect": 12,
        "total": 15, "percent": 20.0
    }
    assert {x["name"] for x in screenshot["topics"]} == {
        "Chuyển biến xã hội Việt Nam", "Lực lượng cách mạng",
        "Nguyên nhân thất bại phong trào",
    }
    assert all(x["chapter"] == "Chương 1" for x in screenshot["topics"])
    # Distinct numbered chapters are never folded together (1 != 10).
    different = summarize_quiz_attempt(
        [{"chapter": "Chương 1", "topic": "A", "answer": 0},
         {"chapter": "Chương 10", "topic": "B", "answer": 0}],
        [0, 0])
    assert len(different["chapters"]) == 2

    # A broken old answer key is unknown, not a diagnosed incorrect answer.
    legacy = summarize_quiz_attempt(
        [{"question": "?"}, {"chapter": "Chương 1", "topic": "T", "answer": "1"}],
        [0, 1])
    assert legacy["unverifiable"] == 1
    assert legacy["correct"] == 1 and legacy["incorrect"] == 0

    final_questions = [
        {"chapter": "Chương 1", "topic": "Lý thuyết", "answer": 0}
        for _ in range(20)
    ] + [
        {"chapter": "Chương 2", "topic": "Vận dụng", "answer": 1}
        for _ in range(40)
    ]
    final_answers = [0] * 20 + [0] * 20 + [1] * 20
    final_analysis = summarize_quiz_attempt(final_questions, final_answers)
    assert final_analysis["total"] == 60
    assert final_analysis["correct"] == 40
    assert final_analysis["incorrect"] == 20
    assert [r["percent"] for r in final_analysis["chapters"]] == [100, 50]

    with TemporaryDirectory() as folder:
        before_db, before_upload = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(folder) / "quiz75.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            def create_user(name):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """, (name, name + "@quiz75.test", "hash", "student",
                      project.now())).lastrowid
            student = create_user("student75")
            other = create_user("other75")
            course = conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,?,?,?,?)
            """, (student, "Giải thuật", "ALG-75", 3, project.now())).lastrowid
            quiz = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,?,?,?)
            """, (student, course, "Quiz thử nghiệm",
                  json.dumps(questions, ensure_ascii=False),
                  project.now())).lastrowid
            # This scenario checks academic/adaptive weakness analytics.
            # Explicitly tag synthetic Quiz fixtures as course review evidence.
            # Generic uploaded-document quizzes now belong to private practice.
            from quiz_review_progress import ensure_review_baseline_schema
            ensure_review_baseline_schema(conn)
            conn.execute("""
                INSERT INTO quiz_review_baselines(
                    quiz_id,user_id,subject_id,snapshot_json,created_at)
                VALUES(?,?,?,'[]',?)
            """,(quiz,student,course,project.now()))
            conn.commit()
            conn.close()

            client = project.app.test_client()
            login(client, other)
            assert client.get(f"/api/quiz/{quiz}/analysis").status_code == 404
            assert client.post("/api/quiz/submit", json={
                "quiz_id": quiz, "answers": [0, 0, 0, 3],
                "request_id": "request75wronguser"
            }).status_code == 404

            login(client, student)
            assert client.get(f"/api/quiz/{quiz}/analysis").status_code == 404
            assert client.post("/api/quiz/submit", json={
                "quiz_id": quiz, "answers": [0, 0, 0, 3],
                "request_id": "bad"
            }).status_code == 400

            first = client.post("/api/quiz/submit", json={
                "quiz_id": quiz, "answers": [0, 0, 0, 3],
                "request_id": "request75first"
            })
            assert first.status_code == 200, first.get_data(as_text=True)[:1000]
            data = first.get_json()
            assert data["correct_count"] == 2 and data["score"] == 50
            assert data["analysis"] == analysis
            assert data["attempt_count"] == 1
            assert data["weakness_count"] == 2
            assert data["adaptive_task"] is not None

            # Retry with the same request key (even if client sends changed
            # answers) returns the original result without another signal.
            repeated = client.post("/api/quiz/submit", json={
                "quiz_id": quiz, "answers": [0, 1, 2, 3],
                "request_id": "request75first"
            })
            assert repeated.status_code == 200
            assert repeated.get_json() == data
            conn = project.db()
            assert conn.execute("""
                SELECT COUNT(*) FROM quiz_attempts WHERE user_id=? AND quiz_id=?
            """, (student, quiz)).fetchone()[0] == 1
            weakness = conn.execute("""
                SELECT topic,miss_count,correct_count FROM learning_weaknesses
                WHERE user_id=? AND subject_id=? ORDER BY topic
            """, (student, course)).fetchall()
            assert len(weakness) == 2
            assert all(w["miss_count"] == 1 for w in weakness)
            conn.close()

            stored = client.get(f"/api/quiz/{quiz}/analysis")
            assert stored.status_code == 200
            stored_obj = stored.get_json()
            assert stored_obj["attempt_id"] == data["attempt_id"]
            assert stored_obj["analysis"] == analysis
            assert "answers_json" not in stored_obj
            assert "correct_answers" not in stored_obj
            assert "Câu thứ hai" not in stored.get_data(as_text=True)
            assert client.get(f"/api/quiz/{quiz}/analysis?attempt_id=9999").status_code == 404

            # New retry key is a genuine independent second attempt.
            second = client.post("/api/mobile/quiz/submit", json={
                "quiz_id": quiz, "answers": [0, 1, 2, 3],
                "request_id": "request75second"
            })
            assert second.status_code == 200, second.get_data(as_text=True)[:800]
            improved = second.get_json()
            assert improved["score"] == 100
            assert improved["weakness_count"] == 0
            assert len(improved["resolved_topics"]) == 2
            assert improved["attempt_count"] == 2
            assert client.get(f"/api/quiz/{quiz}/analysis").get_json()["score"] == 100
            earlier = client.get(
                f"/api/quiz/{quiz}/analysis?attempt_id={data['attempt_id']}")
            assert earlier.status_code == 200
            assert earlier.get_json()["analysis"] == analysis

            # UI is attached to the existing Quiz, without duplicating Quiz.
            html = client.get("/quiz").get_data(as_text=True)
            assert "quiz-learning-analysis" in html
            assert "Xem phân tích lần làm gần nhất" in html
            assert "quiz_learning_analytics.js" in html

            conn = project.db()
            assert conn.execute("""
                SELECT COUNT(*) FROM quiz_attempts WHERE quiz_id=?
            """, (quiz,)).fetchone()[0] == 2
            assert conn.execute("""
                SELECT COUNT(*) FROM study_tasks
                WHERE user_id=? AND subject_id=? AND source='adaptive' AND done=0
            """, (student, course)).fetchone()[0] == 0
            # Nine distinct weak topics: the preview lists at most eight,
            # while the TOTAL weakness count must still be nine.
            nine = [
                {"question": f"Giải thuật ví dụ {i}?", "chapter": "Chương 3",
                 "topic": f"Chủ đề kiểm thử {i}", "answer": 0,
                 "options": ["Đúng", "Sai 1", "Sai 2", "Sai 3"]}
                for i in range(9)
            ]
            quiz_nine = conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,?,?,?)
            """, (student, course, "Kiểm thử 9 điểm yếu",
                  json.dumps(nine, ensure_ascii=False), project.now())).lastrowid
            conn.execute("""
                INSERT INTO quiz_review_baselines(
                    quiz_id,user_id,subject_id,snapshot_json,created_at)
                VALUES(?,?,?,'[]',?)
            """,(quiz_nine,student,course,project.now()))
            conn.commit()
            conn.close()
            many = client.post("/api/quiz/submit", json={
                "quiz_id": quiz_nine, "answers": [1] * 9,
                "request_id": "request75nine"
            })
            assert many.status_code == 200, many.get_data(as_text=True)[:800]
            assert many.get_json()["weakness_count"] == 9
            assert len(many.get_json()["weaknesses"]) == 8
            login(client, other)
            assert client.get(
                f"/api/quiz/{quiz}/analysis?attempt_id={data['attempt_id']}"
            ).status_code == 404
        finally:
            project.DB_PATH, project.UPLOAD_DIR = before_db, before_upload
    print("Phase 7.5.1/7.5.2 grade/weakness/idempotency/chapter-topic/ACL OK")


if __name__ == "__main__":
    check()
