"""Release gate: ensure critical cross-platform academic controls stay wired.

This complements, not replaces, Flask test-client integration tests and Expo
iOS export. Never interpret static contract PASS as a real-device test.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def run():
    app = read("app.py")
    mobile = read("mobile/App.js")
    room = read("mobile/src/StudyRoom.js")
    api = read("mobile/src/api.js")
    bubble = read("mobile/src/FloatingStudyChat.js")
    runtime = read("study_session_quiz_runtime.py")
    mobile_routes = read("mobile_learning_routes.py")
    docs = read("docs/FINAL_RELEASE_QA_2026-11-01.md")
    ci = read(".github/workflows/ci.yml")

    # Same Flask backend, not a duplicate client-side AI or database.
    assert 'app.register_blueprint(mobile_learning_bp)' in app
    assert "api.studyRoom(taskId)" in room
    assert "api.studyChat" in bubble and "api.chatHistory" in bubble
    assert "quiz_csrf" in mobile_routes and "secrets.compare_digest" in mobile_routes
    assert "api.sessionQuizStatus(taskId)" in room
    assert "api.sessionQuizStart(taskId,quizCsrf.current)" in room
    assert "sessionQuiz?.is_final?'Buổi tổng hợp · 60 câu'" in room
    assert "api.quizReview(id)" in mobile
    assert "api.quizSubmit(quiz.quiz_id,answers,submitKey.current)" in mobile
    assert "quiz.questions?.slice(currentQuestion,currentQuestion+1)" in mobile
    assert "Vui lòng trả lời đủ" in mobile
    assert "Xác nhận nộp Quiz" in mobile
    assert "return quiz_access(conn, project, uid, quiz_id, at)" in runtime
    assert "if at >= start:" in runtime
    assert 'datetime.fromisoformat(grant["started_at"]) <= at' in runtime
    assert "review_unlocked" in runtime

    # No access to answer keys until server verifies a stored submission.
    assert 'Chỉ được xem đáp án sau khi nộp bài.' in mobile_routes
    assert "correct_answers" not in api
    assert "quiz_submission_receipts" in app
    assert "quiz_session_links" in runtime

    # Four meaningful tabs; per-course Chat and 15/60 Quiz remain nested.
    for key in ('home', 'subjects', 'plan', 'profile'):
        assert f"['{key}'," in mobile
    assert 'MÔN ĐANG HỎI' in bubble and 'Đổi môn học trong Chat AI' in bubble
    assert "Tạo Quiz ôn điểm yếu" in mobile
    assert "findTaskConflicts" in mobile
    assert "Cài đặt kết nối" in mobile

    # No claim that CI proves real-device usability or independently verified AI.
    assert "CI PASS **không phải**" in docs
    assert "Không đánh dấu những ô này tự động" in docs
    assert "cần người kiểm tra" in docs
    for automated in (
        "tests/test_study_session_quiz_step7234.py",
        "tests/test_mobile_session_quiz_ui.js",
        "tests/test_mobile_study_room.py",
        "tests/test_final_integrity_audit.py",
        "tests/test_chat_grounding.py",
        "tests/test_evaluation_harness_c5.py",
    ):
        assert automated in ci, f"Missing CI regression suite: {automated}"
    print("Final release contract PASS: Web/Mobile, source, permanently-open Quiz, privacy, honest QA")


if __name__ == "__main__":
    run()
