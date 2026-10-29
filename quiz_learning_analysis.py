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


def _chapter_identity(raw):
    """Unify 'CHƯƠNG 1', 'Chương 1: title', and 'Chương 01 · title'.

    This is ONLY a display/aggregation key, never a rewrite of stored Quiz
    questions or the long-term adaptive learning signals.
    """
    original = _label(raw, "Chưa xác định chương", 240)
    match = re.match(r"^chương\s*0*(\d+)(?!\d)", original, re.IGNORECASE)
    if match:
        number = int(match.group(1))
        return f"chapter:{number}", f"Chương {number}", number
    return original.casefold(), original, None


def _topic_identity(raw, full_chapter, chapter_number):
    """Remove redundant chapter headings, preserving the actual topic name."""
    topic = _label(raw, "Chưa xác định chủ đề", 300)
    chapter = _label(full_chapter, "", 240)
    if chapter and topic.casefold().startswith(chapter.casefold()):
        suffix = topic[len(chapter):].strip(" :;·—–-|.")
        if suffix:
            topic = suffix
    elif chapter_number is not None:
        # 'CHƯƠNG 1 · Thắng lợi ...' => 'Thắng lợi ...'
        prefix = re.match(
            rf"^chương\s*0*{chapter_number}(?!\d)\s*[:;·—–|.\-]+\s*",
            topic, re.IGNORECASE
        )
        if prefix:
            remainder = topic[prefix.end():].strip()
            if remainder:
                topic = remainder
    return topic[:180]


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
        chapter_key, chapter, chapter_number = _chapter_identity(
            question.get("chapter"))
        topic = _topic_identity(question.get("topic"),
                                question.get("chapter"), chapter_number)
        for bucket, key, label in (
            (chapters, chapter_key, chapter),
            (topics, (chapter_key, topic.casefold()), topic),
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
        "quiz_title": quiz["title"], "subject_id": quiz["subject_id"],
        "score": float(attempt["score"]),
        "correct_count": attempt["correct_count"],
        "total_questions": attempt["total_questions"],
        "created_at": attempt["created_at"],
        "analysis": details,
    }



def ensure_quiz_submission_receipts(conn):
    """Additive idempotency ledger: one request key cannot count weaknesses twice."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_submission_receipts(
            user_id INTEGER NOT NULL,
            quiz_id INTEGER NOT NULL,
            request_id TEXT NOT NULL,
            attempt_id INTEGER NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id,quiz_id,request_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
            FOREIGN KEY(attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE
        )
    """)
