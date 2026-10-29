"""Phase 8.1: explainable next-study decision from persisted, scoped evidence.

Read-only. A Quiz score is not a diagnosis of mastery; persistent weaknesses
take priority, and no improvement is claimed without comparable review data.
No Gemini calls or schedule mutations happen here.
"""
import re
from datetime import datetime, timedelta

from adaptive_review_schedule import local_now


def decide_next_learning_step(conn, user_id, subject_id, current=None):
    subject = conn.execute(
        "SELECT id,name,progress FROM subjects WHERE id=? AND user_id=?",
        (subject_id, user_id)
    ).fetchone()
    if not subject:
        return None

    weaknesses = conn.execute("""
        SELECT topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=? AND miss_count>correct_count
        ORDER BY (miss_count-correct_count*0.5) DESC,last_seen_at DESC
        LIMIT 8
    """, (user_id, subject_id)).fetchall()
    latest = conn.execute("""
        SELECT qa.id,qa.correct_count,qa.total_questions,qa.created_at
        FROM quiz_attempts qa
        JOIN quizzes q ON q.id=qa.quiz_id AND q.user_id=qa.user_id
        WHERE qa.user_id=? AND q.user_id=? AND q.subject_id=?
        ORDER BY qa.id DESC LIMIT 1
    """, (user_id, user_id, subject_id)).fetchone()
    next_task = conn.execute("""
        SELECT id,title,study_at,duration FROM study_tasks
        WHERE user_id=? AND subject_id=? AND source='roadmap' AND done=0
        ORDER BY study_at,id LIMIT 1
    """, (user_id, subject_id)).fetchone()
    review_task = conn.execute("""
        SELECT id,title,study_at,duration FROM study_tasks
        WHERE user_id=? AND subject_id=? AND source='adaptive' AND done=0
        ORDER BY study_at,id LIMIT 1
    """, (user_id, subject_id)).fetchone()
    current = current or local_now()
    deadline = None
    for row in conn.execute("""
        SELECT due_at FROM reminders
        WHERE user_id=? AND subject_id=? AND done=0 AND due_at!=''
        ORDER BY due_at LIMIT 8
    """, (user_id, subject_id)):
        try:
            due = datetime.fromisoformat(row["due_at"])
        except (TypeError, ValueError):
            continue
        if due.tzinfo is None and due <= current + timedelta(days=2):
            deadline = due
            break

    evidence = [f"Tiến độ môn hiện tại: {int(subject['progress'] or 0)}%"]
    material_chapter = None
    if latest and int(latest["total_questions"] or 0) > 0:
        count = int(latest["total_questions"])
        right = max(0, min(count, int(latest["correct_count"] or 0)))
        score = round(100 * right / count)
        evidence.append(f"Quiz gần nhất: {right}/{count} câu đúng ({score}%)")
    else:
        score = None
        evidence.append("Chưa có kết quả Quiz hợp lệ trong môn này")

    if weaknesses:
        top = weaknesses[0]
        miss, correct = int(top["miss_count"]), int(top["correct_count"])
        label = f"{top['chapter']} · {top['topic']}" if top["chapter"] else top["topic"]
        chapter_match = re.match(r"^\s*chương\s*0*(\d+)", str(top["chapter"] or ""), re.I)
        if chapter_match:
            chapter_number = int(chapter_match.group(1))
            if 1 <= chapter_number <= 80:
                material_chapter = chapter_number
        evidence.append(f"Chủ đề cần theo dõi: {label} · sai {miss}, đúng {correct}")
        evidence.append(f"Còn {len(weaknesses)} chủ đề ưu tiên trong mẫu 8 chủ đề")
        if miss >= 2:
            kind, title = "review", "Ưu tiên ôn trước khi học tiếp"
            reason = ("Chủ đề này có nhiều lần trả lời sai hơn đúng. "
                      "Agent đề xuất sử dụng lịch ôn thích nghi và làm Quiz ôn điểm yếu; "
                      "không kết luận đã thành thạo chỉ từ một lượt làm bài.")
        else:
            kind, title = "verify", "Kiểm tra thêm chủ đề vừa làm sai"
            reason = ("Mới ghi nhận tín hiệu làm sai nên chưa đủ cơ sở kết luận "
                      "bạn yếu lâu dài. Hãy ôn ngắn và kiểm tra lại đúng chủ đề.")
    elif score is None:
        kind, title = "collect", "Làm Quiz để Agent có dữ liệu cá nhân"
        reason = ("Chưa có kết quả kiểm tra phù hợp để đánh giá mức độ nắm bài. "
                  "Agent chưa tự suy đoán điểm yếu hoặc mức độ thành thạo.")
    elif score >= 75 and int(latest["total_questions"]) >= 5:
        kind, title = "continue", "Có thể tiếp tục lộ trình"
        reason = ("Quiz gần nhất đạt ngưỡng tham khảo và hiện không còn chủ đề "
                  "có số lần sai lớn hơn số lần đúng. Đây là gợi ý học tiếp, "
                  "không phải xác nhận bạn đã thành thạo tất cả nội dung.")
    else:
        kind, title = "practice", "Luyện tập bổ sung rồi đánh giá lại"
        reason = ("Kết quả Quiz chưa đủ vững để ưu tiên chuyển nội dung chỉ dựa "
                  "vào điểm số. Agent đề xuất luyện tập và kiểm tra lại; "
                  "không tự tạo điểm yếu khi thiếu tín hiệu theo chủ đề.")

    if deadline:
        evidence.append(f"Deadline môn: {deadline.strftime('%d/%m/%Y %H:%M')}")
        if kind == "continue":
            reason += " Có deadline gần nên cần theo dõi tiến độ sát hơn."
    if review_task:
        evidence.append(f"Lịch ôn đang có: {review_task['study_at'][:16].replace('T',' ')}")
    if next_task:
        evidence.append(f"Buổi theo lộ trình tiếp: {next_task['title']}")

    return {
        "kind": kind, "title": title, "reason": reason,
        "evidence": evidence, "subject_id": subject_id,
        "subject_name": subject["name"], "weakness_count": len(weaknesses),
        "latest_score": score, "next_task": dict(next_task) if next_task else None,
        "review_task": dict(review_task) if review_task else None,
        "deadline_urgent": bool(deadline),
        "material_chapter": material_chapter,
    }
