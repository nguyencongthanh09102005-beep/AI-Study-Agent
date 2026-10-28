"""Detach subject-scoped learning records without losing the student's history.

Old installs of Phase 6.4 / 7.1 created subject FKs with the default RESTRICT
behavior. The Web/Mobile 'delete subject' contract instead keeps documents,
Quiz scores, planner tasks and completed study time as unclassified. Migrate
only these two newly introduced tables to nullable subject references, in
the same transaction, then detach them before deleting the subject.
"""
from study_session_tracking import ensure_tracking_schema
from study_session_quiz_runtime import ensure_quiz_runtime_schema


_LINK_COLUMNS = (
    "quiz_id", "task_id", "user_id", "subject_id", "chapter_number",
    "session_title", "session_signature", "source_signature",
    "source_ids_json", "created_at",
)
_TRACK_COLUMNS = (
    "task_id", "user_id", "subject_id", "status", "started_at",
    "last_heartbeat_at", "elapsed_seconds", "completed_at", "updated_at",
)


def _upgrade_nullable_subject(conn, table, columns, schema):
    """SQLite cannot ALTER an existing FK in place. Copy all rows atomically."""
    info = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not info:
        return
    fks = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    subject = next((r for r in info if r["name"] == "subject_id"), None)
    fk = next((r for r in fks if r["from"] == "subject_id"
               and r["table"] == "subjects"), None)
    if subject and not subject["notnull"] and fk and fk["on_delete"] == "SET NULL":
        return
    # These tables have no incoming foreign keys; their own quiz/task FKs
    # remain identical. A transaction rollback restores the original if any
    # step fails. Never rename the old table (SQLite can rewrite FK targets).
    next_table = table + "_subject_nullable_migration"
    conn.execute(f"DROP TABLE IF EXISTS {next_table}")
    conn.execute(schema.format(table=next_table))
    names = ",".join(columns)
    conn.execute(
        f"INSERT INTO {next_table}({names}) SELECT {names} FROM {table}"
    )
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {next_table} RENAME TO {table}")
    # Original indexes are dropped with the original table.
    if table == "quiz_session_links":
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_quiz_session_owner
            ON quiz_session_links(user_id,subject_id,task_id)
        """)
    else:
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_study_session_tracking_owner
            ON study_session_tracking(user_id,subject_id)
        """)


def detach_subject_learning_records(conn, user_id, subject_id):
    """Run before legacy subject removal, within its existing transaction.

    Preserve unclassified quizzes + attempts, their locked source signatures,
    study tasks and actual elapsed time; clear only unfinished, transient AI
    pre-generation work and timed access grants. Do not touch other users.
    """
    ensure_tracking_schema(conn)
    ensure_quiz_runtime_schema(conn)
    _upgrade_nullable_subject(conn, "quiz_session_links", _LINK_COLUMNS, """
        CREATE TABLE {table}(
            quiz_id INTEGER PRIMARY KEY,
            task_id INTEGER,
            user_id INTEGER NOT NULL,
            subject_id INTEGER,
            chapter_number INTEGER NOT NULL CHECK(chapter_number >= 1),
            session_title TEXT NOT NULL,
            session_signature TEXT NOT NULL,
            source_signature TEXT NOT NULL,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
            FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE SET NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        )
    """)
    _upgrade_nullable_subject(conn, "study_session_tracking", _TRACK_COLUMNS, """
        CREATE TABLE {table}(
            task_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            subject_id INTEGER,
            status TEXT NOT NULL DEFAULT 'paused'
                CHECK(status IN ('running','paused','completed')),
            started_at TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            elapsed_seconds INTEGER NOT NULL DEFAULT 0
                CHECK(elapsed_seconds >= 0),
            completed_at TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        )
    """)

    # A deleted course cannot keep a pending Gemini job or exam unlock.
    conn.execute("""
        DELETE FROM quiz_preparation_parts
        WHERE user_id=? AND task_id IN (
            SELECT id FROM study_tasks WHERE user_id=? AND subject_id=?
        )
    """, (user_id, user_id, subject_id))
    conn.execute("""
        DELETE FROM quiz_preparation_claims
        WHERE user_id=? AND task_id IN (
            SELECT id FROM study_tasks WHERE user_id=? AND subject_id=?
        )
    """, (user_id, user_id, subject_id))
    conn.execute("""
        DELETE FROM quiz_session_grants
        WHERE user_id=? AND quiz_id IN (
            SELECT quiz_id FROM quiz_session_links
            WHERE user_id=? AND subject_id=?
        )
    """, (user_id, user_id, subject_id))
    conn.execute("""
        UPDATE quiz_session_links SET subject_id=NULL
        WHERE subject_id=? AND user_id=?
    """, (subject_id, user_id))
    conn.execute("""
        UPDATE study_session_tracking SET subject_id=NULL
        WHERE subject_id=? AND user_id=?
    """, (subject_id, user_id))
