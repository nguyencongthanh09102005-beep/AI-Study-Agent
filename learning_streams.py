"""Separate syllabus-bound assessment from optional private self-study.

A quiz is academic only when linked to a verified course session or its
adaptive-review baseline. Generic, uploaded-document, and manual-room quizzes
belong to private practice, even when they share a subject_id.
"""
def ensure_private_weakness_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS self_study_weaknesses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            topic_key TEXT NOT NULL,
            topic TEXT NOT NULL,
            chapter TEXT NOT NULL DEFAULT '',
            miss_count INTEGER NOT NULL DEFAULT 0,
            correct_count INTEGER NOT NULL DEFAULT 0,
            last_seen_at TEXT NOT NULL,
            UNIQUE(user_id, subject_id, topic_key),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)


def academic_quiz(conn, user_id, quiz_id):
    for table in ("quiz_session_links", "quiz_review_baselines"):
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)
        ).fetchone()
        if exists and conn.execute(
            f"SELECT 1 FROM {table} WHERE user_id=? AND quiz_id=? LIMIT 1",
            (user_id, quiz_id)
        ).fetchone():
            return True
    return False
