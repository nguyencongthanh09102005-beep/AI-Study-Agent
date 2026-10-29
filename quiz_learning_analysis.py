"""Phase 7.5.1/7.5.2: deterministic, attempt-scoped Quiz learning analytics.

Scores and breakdowns derive ONLY from persisted question keys and selected
answers; no model call, private document access or guessed chapter/topic.
"""
import json
import re


def _label(value, fallback, limit=120):
    if not isinstance(value, str):
        return fallback
    clean = re.sub(r"\s+", " ", value).strip()
    return clean[:limit] if clean else fallback


def _valid_key(question):
    if not isinstance(question, dict):
        return None
    key = question.get("answer")
    if type(key) is int and 0 <= key <= 3:
        return key
    # Legacy Quiz payloads occasionally store the index as an ASCII digit.
    if isinstance(key, str) and key in ("0", "1", "2", "3"):
        return int(key)
    return None


def summarize_quiz_attempt(questions, answers, max_topics=12):
    """Return safe aggregates without question text, answer keys or choices.

    Invalid keys count as unverifiable, not as a false diagnosis of weakness.
    The stored score is authoritative for historical records.
    """
    if not isinstance(questions, list) or not isinstance(answers, list):
        return {"total": 0, "correct": 0, "incorrect": 0, "unverifiable": 0,
                "chapters": [], "topics": [], "needs_review": []}
    chapters, topics = {}, {}
    correct = incorrect = unverifiable = 0
    for index, question in enumerate(questions):
        expected = _valid_key(question)
        selected = answers[index] if index < len(answers) else None
        if expected is None or type(selected) is not int or selected not in range(4):
            unverifiable += 1
            continue
        is_correct = selected == expected
        correct += int(is_correct)
        incorrect += int(not is_correct)
        chapter = _label(question.get("chapter"), "Chưa xác định chương")
        topic = _label(question.get("topic"), "Chưa xác định chủ đề", 180)
        for bucket, key, label in (
            (chapters, chapter.casefold(), chapter),
            (topics, (chapter.casefold(), topic.casefold()), topic),
        ):
            if key not in bucket:
                bucket[key] = {"name": label, "correct": 0, "incorrect": 0}
                if bucket is topics:
                    bucket[key]["chapter"] = chapter
            bucket[key]["correct"] += int(is_correct)
            bucket[key]["incorrect"] += int(not is_correct)

    def finish(bucket):
        result = []
        for entry in bucket.values():
            count = entry["correct"] + entry["incorrect"]
            result.append({**entry, "total": count,
                           "percent": round(100 * entry["correct"] / count, 1)})
        return result

    chapters_view = finish(chapters)
    topic_view = finish(topics)
    topic_view.sort(key=lambda t: (
        -t["incorrect"], t["percent"], t["chapter"].casefold(), t["name"].casefold()
    ))
    needs_review = [
        {"chapter": t["chapter"], "topic": t["name"],
         "incorrect": t["incorrect"], "total": t["total"]}
        for t in topic_view if t["incorrect"] > 0
    ]
    return {
        "total": len(questions),
        "correct": correct, "incorrect": incorrect,
        "unverifiable": unverifiable,
        "chapters": chapters_view,
        "topics": topic_view[:max_topics],
        "needs_review": needs_review[:8],
    }


def analysis_for_saved_attempt(conn, uid, quiz_id, attempt_id=None):
    """Owner-only read of scored learning aggregates; no answer-key leakage."""
    quiz = conn.execute("""
        SELECT id,payload,subject_id,title FROM quizzes
        WHERE id=? AND user_id=?
    """, (quiz_id, uid)).fetchone()
    if not quiz:
        return None
    where = "AND qa.id=?" if attempt_id is not None else ""
    params = (quiz_id, uid, attempt_id) if attempt_id is not None else (quiz_id, uid)
    attempt = conn.execute(f"""
        SELECT qa.id,qa.score,qa.correct_count,qa.total_questions,
               qa.answers_json,qa.created_at
        FROM quiz_attempts qa
        WHERE qa.quiz_id=? AND qa.user_id=? {where}
        ORDER BY qa.id DESC LIMIT 1
    """, params).fetchone()
    if not attempt:
        return None
    try:
        questions = json.loads(quiz["payload"])
        answers = json.loads(attempt["answers_json"])
    except (ValueError, TypeError):
        questions, answers = [], []
    details = summarize_quiz_attempt(questions, answers)
    return {
        "quiz_id": quiz_id, "attempt_id": attempt["id"],
        "quiz_title": quiz["title"],
        "score": float(attempt["score"]),
        "correct_count": attempt["correct_count"],
        "total_questions": attempt["total_questions"],
        "created_at": attempt["created_at"],
        "analysis": details,
    }
