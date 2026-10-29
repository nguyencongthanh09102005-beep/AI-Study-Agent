"""Phase 7.5.4: honest pre/post comparison for targeted weakness quizzes.

The baseline is captured before the review Quiz is created and never
recomputed from future attempts. Compare only questions with a topic that
matches a pre-review weakness; never infer mastery for unrelated topics.
"""
import json
import re


def topic_key(chapter, topic):
    # Match the same chapter identity used by 7.5.2 report. E.g.
    # "CHƯƠNG 01: full title" and "Chương 1" are the same chapter.
    # Do not collapse similarly named topics from different chapters.
    from quiz_learning_analysis import _chapter_identity, _topic_identity
    key, _title, number = _chapter_identity(chapter)
    short_topic = _topic_identity(topic, chapter, number)
    normalized = re.sub(
        r"\s+", " ", re.sub(r"[^\wÀ-ỹ]+", " ", short_topic.lower())
    ).strip()
    return (key + "|" + normalized)[:320]


def ensure_review_baseline_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_review_baselines (
            quiz_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)


def save_review_baseline(conn, uid, subject_id, quiz_id, created_at):
    """Own the Quiz and snapshot current active weak topics at generation."""
    ensure_review_baseline_schema(conn)
    quiz = conn.execute(
        "SELECT id FROM quizzes WHERE id=? AND user_id=? AND subject_id=?",
        (quiz_id, uid, subject_id)
    ).fetchone()
    if not quiz:
        raise ValueError("Quiz không thuộc môn học hoặc sinh viên.")
    rows = conn.execute("""
        SELECT topic_key,topic,chapter,miss_count,correct_count
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=? AND miss_count>correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC,last_seen_at DESC
        LIMIT 8
    """, (uid, subject_id)).fetchall()
    if not rows:
        return
    baseline = [
        {"key": topic_key(row["chapter"], row["topic"]), "topic": row["topic"],
         "chapter": row["chapter"], "wrong": row["miss_count"],
         "correct": row["correct_count"]}
        for row in rows
    ]
    conn.execute("""
        INSERT INTO quiz_review_baselines(
            quiz_id,user_id,subject_id,snapshot_json,created_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(quiz_id) DO NOTHING
    """, (quiz_id,uid,subject_id,
          json.dumps(baseline,ensure_ascii=False),created_at))


def compare_review_attempt(conn, uid, quiz_id, questions, answers):
    ensure_review_baseline_schema(conn)
    row = conn.execute("""
        SELECT b.snapshot_json FROM quiz_review_baselines b
        JOIN quizzes q ON q.id=b.quiz_id AND q.user_id=b.user_id
                     AND q.subject_id=b.subject_id
        WHERE b.quiz_id=? AND b.user_id=?
    """, (quiz_id,uid)).fetchone()
    if not row:
        return None
    try:
        baseline = json.loads(row["snapshot_json"])
    except (ValueError, TypeError):
        return None
    if not isinstance(baseline,list) or not isinstance(questions,list):
        return None
    baseline_by_key = {item.get("key"):item for item in baseline
                       if isinstance(item,dict) and item.get("key")}
    matched = {}
    for index,q in enumerate(questions):
        if not isinstance(q,dict) or index>=len(answers):
            continue
        try:
            expected=int(q["answer"])
            given=int(answers[index])
        except (ValueError,TypeError,KeyError):
            continue
        if expected not in range(4) or given not in range(4):
            continue
        key=topic_key(q.get("chapter"),q.get("topic"))
        base=baseline_by_key.get(key)
        if not base:
            continue
        item=matched.setdefault(key,{
            "chapter":base["chapter"],"topic":base["topic"],
            "before_correct":int(base["correct"]),
            "before_wrong":int(base["wrong"]),
            "after_correct":0,"after_total":0,
        })
        item["after_total"]+=1
        item["after_correct"]+=int(expected==given)
    rows=[]
    for item in matched.values():
        prev=item["before_correct"]+item["before_wrong"]
        if not prev:
            continue
        before=round(100*item["before_correct"]/prev,1)
        after=round(100*item["after_correct"]/item["after_total"],1)
        rows.append({
            "chapter":item["chapter"],"topic":item["topic"],
            "before_percent":before,"after_percent":after,
            "delta_percent":round(after-before,1),
            "before_questions":prev,
            "review_questions":item["after_total"]
        })
    return {
        "comparable_topics":len(rows),
        "topics":rows,
        "note":("So sánh độ đúng lịch sử trước khi tạo Quiz với lượt kiểm tra ôn "
                "hiện tại trên những chủ đề trùng khớp. Một vài câu đúng chưa "
                "chứng minh đã thành thạo hoàn toàn.")
    }
