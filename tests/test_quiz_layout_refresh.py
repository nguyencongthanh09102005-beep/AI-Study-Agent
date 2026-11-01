"""Quiz UI refresh: real Flask/Jinja rendering without touching real student data."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def test():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "quiz-layout.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            now = project.now()
            user_id = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Quiz UI','quiz-ui@local.test','hash','student',?)",
                (now,)
            ).lastrowid
            other_id = conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) "
                "VALUES('Other UI','other-quiz@local.test','hash','student',?)",
                (now,)
            ).lastrowid
            subject_id = conn.execute(
                "INSERT INTO subjects(user_id,name,code,credits,created_at) "
                "VALUES(?,'Lịch sử Đảng','HIS',3,?)",
                (user_id, now)
            ).lastrowid
            question = {
                "question": "Đảng Cộng sản Việt Nam được thành lập năm nào?",
                "options": ["1925", "1930", "1945", "1954"],
                "answer": 1,
                "topic": "Lịch sử",
                "chapter": "Chương 1",
            }
            quiz_ids = []
            for name in ("Ôn điểm yếu – Lịch sử Đảng",
                         "Kiểm tra Chương 1 – Lịch sử Đảng"):
                quiz_ids.append(conn.execute(
                    """INSERT INTO quizzes(user_id,subject_id,document_id,title,
                                           payload,created_at)
                       VALUES(?,?,NULL,?,?,?)""",
                    (user_id, subject_id, name,
                     json.dumps([question, question], ensure_ascii=False), now)
                ).lastrowid)
            conn.execute(
                """INSERT INTO quiz_attempts(user_id,quiz_id,score,correct_count,
                                              total_questions,created_at)
                   VALUES(?,?,100,2,2,?)""",
                (user_id, quiz_ids[0], now)
            )
            conn.commit()
            conn.close()

            student = project.app.test_client()
            with student.session_transaction() as sess:
                sess["user_id"] = user_id
            other = project.app.test_client()
            with other.session_transaction() as sess:
                sess["user_id"] = other_id

            html = student.get("/quiz").get_data(as_text=True)
            assert "quiz_layout_refresh.css" in html
            assert 'id="quizCreateBody"' in html
            assert 'id="quizCreateToggle"' in html
            assert 'aria-expanded="false"' in html
            assert 'id="quizCreateBody" class="quiz-create-collapsible-body" hidden' in html
            assert 'class="quiz-compact-stats"' in html
            assert "Điểm cao nhất" in html and "100%" in html
            assert "quiz-new-layout" in html
            assert "Câu 1/2" in html
            assert "Đã trả lời 0/2" in html
            assert html.count('class="quiz-history-details"') == 2
            assert html.index('class="quiz-actions"') < html.index('class="quiz-history-details"')
            assert "Xem phân tích lần làm gần nhất" in html
            assert 'class="quiz-learning-analysis"' in html
            assert 'name="quiz_mode" value="subject"' in html
            assert 'name="quiz_mode" value="document"' in html
            assert 'name="quiz_mode" value="weakness"' in html
            assert "Câu tiếp theo" in html and "Nộp bài" in html
            assert "Quiz được tạo theo đúng ngữ cảnh học tập" not in html
            assert "Đáp án" not in html or "1930" in html
            # A genuine deep link to create by document keeps the hub open.
            linked = student.get("/quiz?mode=document").get_data(as_text=True)
            assert 'aria-expanded="true"' in linked
            assert 'id="quizCreateBody" class="quiz-create-collapsible-body" >' in linked
            # New students can still create their first Quiz.
            fresh = other.get("/quiz").get_data(as_text=True)
            assert 'aria-expanded="true"' in fresh
            assert "Chưa có Quiz" in fresh
            assert "Ôn điểm yếu – Lịch sử Đảng" not in fresh
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Quiz layout PASS: compact creator, context deep link, stats, private quizzes, analysis at bottom")


if __name__ == "__main__":
    test()
