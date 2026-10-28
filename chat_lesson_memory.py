"""Mode- and syllabus-scoped Chat AI memory.

The UI shows one conversation per student/subject. Only relevant previous
turns are sent back to the model. Unscoped legacy turns are treated as
free-chat, not as validated chapter study material.
"""

import hashlib
import json


def ensure_chat_memory_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_message_contexts (
            message_id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK(mode IN ('free', 'chapter')),
            chapter_number INTEGER,
            topic_index INTEGER,
            source_signature TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(message_id) REFERENCES chat_messages(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_message_contexts_conversation
        ON chat_message_contexts(user_id, conversation_id, mode,
                                 chapter_number, topic_index)
    """)


def approved_source_signature(syllabus_fingerprint, sources):
    """A deterministic signature that changes after edits/revocations."""
    payload = {
        "syllabus": str(syllabus_fingerprint or ""),
        "sources": [
            {
                "id": src["id"],
                "name": src["name"],
                "text_hash": hashlib.sha256(
                    src["excerpt"].encode("utf-8")
                ).hexdigest(),
            }
            for src in sources
        ],
    }
    serial = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serial.encode("utf-8")).hexdigest()


def history_for_mode(conn, user_id, conversation_id, lesson=None, limit=10):
    """Return only on-topic history, never from another mode or source version."""
    ensure_chat_memory_schema(conn)
    if lesson:
        if lesson["topic_index"] is None:
            clause = """ctx.mode='chapter' AND ctx.chapter_number=?
                    AND ctx.topic_index IS NULL AND ctx.source_signature=?"""
            params = (
                user_id, conversation_id, lesson["chapter_number"],
                lesson["source_signature"], limit,
            )
        else:
            # Older chapter links can still opt into a concrete topic.
            clause = """ctx.mode='chapter' AND ctx.chapter_number=?
                    AND ctx.topic_index=? AND ctx.source_signature=?"""
            params = (
                user_id, conversation_id, lesson["chapter_number"],
                lesson["topic_index"], lesson["source_signature"], limit,
            )
    else:
        # Legacy chat rows have no context record and belong to Free mode.
        clause = "(ctx.mode='free' OR ctx.message_id IS NULL)"
        params = (user_id, conversation_id, limit)

    rows = conn.execute(f"""
        SELECT m.role, m.content
        FROM chat_messages AS m
        LEFT JOIN chat_message_contexts AS ctx
          ON ctx.message_id=m.id
         AND ctx.user_id=m.user_id
         AND ctx.conversation_id=m.conversation_id
        WHERE m.user_id=? AND m.conversation_id=? AND {clause}
        ORDER BY m.id DESC
        LIMIT ?
    """, params).fetchall()
    return list(reversed(rows))


def save_message_context(conn, message_id, user_id, conversation_id, lesson=None):
    """Tag one committed message with its active learning context."""
    ensure_chat_memory_schema(conn)
    conn.execute("""
        INSERT INTO chat_message_contexts(
            message_id,user_id,conversation_id,mode,chapter_number,
            topic_index,source_signature
        ) VALUES(?,?,?,?,?,?,?)
    """, (
        message_id, user_id, conversation_id,
        "chapter" if lesson else "free",
        lesson["chapter_number"] if lesson else None,
        lesson["topic_index"] if lesson else None,
        lesson["source_signature"] if lesson else "",
    ))
