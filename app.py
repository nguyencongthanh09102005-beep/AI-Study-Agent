import os
import sqlite3
import json
import re
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import requests
except Exception:
    requests = None
load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "data" / "study_agent.db"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-this-secret-before-deploy")
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Bật kiểm tra khóa ngoại cho mọi kết nối SQLite.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS subjects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        code TEXT DEFAULT '',
        description TEXT DEFAULT '',
        credits INTEGER DEFAULT 0,
        target_score REAL DEFAULT 0,
        progress INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        extracted_text TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        due_at TEXT DEFAULT '',
        done INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS study_tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER,
        title TEXT NOT NULL,
        study_at TEXT NOT NULL,
        duration INTEGER DEFAULT 45,
        note TEXT DEFAULT '',
        done INTEGER DEFAULT 0,
        source TEXT DEFAULT 'manual',
        completed_at TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS chat_conversations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER,
        title TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
        pinned INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS chat_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        conversation_id INTEGER,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS quizzes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER,
        document_id INTEGER,
        title TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL,
        FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS quiz_attempts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        quiz_id INTEGER NOT NULL,
        score REAL DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        total_questions INTEGER DEFAULT 0,
        answers_json TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
    );

    -- =================================================
    -- STUDY AGENT V2: KIẾN THỨC CHUNG + DỮ LIỆU CÁ NHÂN
    -- =================================================
    CREATE TABLE IF NOT EXISTS shared_subjects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        subject_key TEXT UNIQUE NOT NULL,
        code TEXT DEFAULT '',
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        syllabus_text TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS shared_knowledge(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shared_subject_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        source_type TEXT DEFAULT 'note',
        created_by_user_id INTEGER,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(shared_subject_id) REFERENCES shared_subjects(id) ON DELETE CASCADE,
        FOREIGN KEY(created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS learning_profiles(
        user_id INTEGER PRIMARY KEY,
        learning_style TEXT DEFAULT 'balanced',
        preferred_study_time TEXT DEFAULT '19:00',
        daily_minutes INTEGER DEFAULT 45,
        goals TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS learning_weaknesses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        topic_key TEXT NOT NULL,
        topic TEXT NOT NULL,
        miss_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        last_seen_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        UNIQUE(user_id, subject_id, topic_key)
    );
    """)

    conn.commit()

    # =====================================================
    # CẬP NHẬT DATABASE CŨ - SUBJECTS
    # =====================================================

    subject_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(subjects)"
        ).fetchall()
    }

    if "code" not in subject_columns:
        conn.execute(
            "ALTER TABLE subjects ADD COLUMN code TEXT DEFAULT ''"
        )

    if "credits" not in subject_columns:
        conn.execute(
            "ALTER TABLE subjects ADD COLUMN credits INTEGER DEFAULT 0"
        )

    if "target_score" not in subject_columns:
        conn.execute(
            "ALTER TABLE subjects ADD COLUMN target_score REAL DEFAULT 0"
        )

    if "shared_subject_id" not in subject_columns:
        conn.execute(
            "ALTER TABLE subjects ADD COLUMN shared_subject_id INTEGER"
        )

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_subjects_shared_subject "
        "ON subjects(shared_subject_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_shared_knowledge_subject "
        "ON shared_knowledge(shared_subject_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_learning_weaknesses_user_subject "
        "ON learning_weaknesses(user_id, subject_id, miss_count)"
    )

    conn.commit()

    # =====================================================
    # CẬP NHẬT DATABASE CŨ - STUDY TASKS
    # Lưu thời điểm THỰC TẾ người dùng bấm hoàn thành
    # =====================================================
    task_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(study_tasks)"
        ).fetchall()
    }

    if "completed_at" not in task_columns:
        conn.execute(
            "ALTER TABLE study_tasks ADD COLUMN completed_at TEXT DEFAULT ''"
        )

    # Không tự đoán thời điểm hoàn thành cho dữ liệu cũ.
    # Chỉ các task được người dùng bấm "Hoàn thành" từ phiên bản này
    # trở đi mới có completed_at thật.
    #
    # Dọn một lần dữ liệu completed_at đã từng được migration cũ tự sinh,
    # để tránh dồn nhiều giờ học vào ngày hiện tại.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_meta(
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        )
    """)

    cleanup_done = conn.execute(
        "SELECT value FROM app_meta WHERE key=?",
        ("completed_at_cleanup_v2",)
    ).fetchone()

    if not cleanup_done:
        conn.execute(
            """
            UPDATE study_tasks
            SET completed_at=''
            WHERE done=1
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO app_meta(key, value)
            VALUES(?, ?)
            """,
            ("completed_at_cleanup_v2", now())
        )

    conn.commit()

    # =====================================================
    # CẬP NHẬT DATABASE CŨ - THÊM document_id CHO QUIZ
    # =====================================================
    quiz_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(quizzes)").fetchall()
    }

    if "document_id" not in quiz_columns:
        conn.execute("ALTER TABLE quizzes ADD COLUMN document_id INTEGER")
        conn.commit()

    # Gắn lại tài liệu cho các quiz cũ nếu tài liệu vẫn còn.
    conn.execute("""
        UPDATE quizzes
        SET document_id = (
            SELECT d.id
            FROM documents d
            WHERE d.user_id = quizzes.user_id
              AND quizzes.title = 'Quiz từ ' || d.original_name
            ORDER BY d.id DESC
            LIMIT 1
        )
        WHERE document_id IS NULL
    """)

    # Xóa quiz mồ côi của những tài liệu đã bị xóa trước đây.
    conn.execute("""
        DELETE FROM quizzes
        WHERE document_id IS NULL
          AND title LIKE 'Quiz từ %'
          AND NOT EXISTS (
              SELECT 1
              FROM documents d
              WHERE d.user_id = quizzes.user_id
                AND quizzes.title = 'Quiz từ ' || d.original_name
          )
    """)
    conn.commit()

    # =====================================================
    # CẬP NHẬT DATABASE CŨ - CHAT THEO MÔN HỌC
    # =====================================================
    chat_message_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(chat_messages)"
        ).fetchall()
    }

    if "conversation_id" not in chat_message_columns:
        conn.execute(
            "ALTER TABLE chat_messages ADD COLUMN conversation_id INTEGER"
        )

    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_conversations(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subject_id INTEGER,
            title TEXT NOT NULL DEFAULT 'Cuộc trò chuyện mới',
            pinned INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)

    conversation_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(chat_conversations)"
        ).fetchall()
    }

    # SQLite cho phép thêm cột nhưng không thêm FK vào bảng cũ.
    # Vì vậy với database cũ ta quản lý xóa đồng bộ bằng code.
    if "subject_id" not in conversation_columns:
        conn.execute(
            "ALTER TABLE chat_conversations ADD COLUMN subject_id INTEGER"
        )

    # Mỗi môn học có đúng một không gian Chat AI.
    subject_rows_for_chat = conn.execute("""
        SELECT id, user_id, name, created_at
        FROM subjects
        ORDER BY id ASC
    """).fetchall()

    for subject_row in subject_rows_for_chat:
        existing_chat = conn.execute(
            """
            SELECT id
            FROM chat_conversations
            WHERE user_id=? AND subject_id=?
            ORDER BY id ASC
            LIMIT 1
            """,
            (subject_row["user_id"], subject_row["id"])
        ).fetchone()

        if existing_chat:
            conn.execute(
                """
                UPDATE chat_conversations
                SET title=?
                WHERE id=? AND user_id=?
                """,
                (
                    subject_row["name"],
                    existing_chat["id"],
                    subject_row["user_id"]
                )
            )
        else:
            created_at = subject_row["created_at"] or now()
            conn.execute(
                """
                INSERT INTO chat_conversations(
                    user_id,subject_id,title,pinned,created_at,updated_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (
                    subject_row["user_id"],
                    subject_row["id"],
                    subject_row["name"],
                    0,
                    created_at,
                    created_at
                )
            )

    # Dọn các chat kiểu cũ không gắn với môn học
    # (ví dụ: "Cuộc trò chuyện mới", các tên chat thủ công trước đây).
    conn.execute("""
        DELETE FROM chat_messages
        WHERE conversation_id IN (
            SELECT id
            FROM chat_conversations
            WHERE subject_id IS NULL
        )
    """)

    conn.execute("""
        DELETE FROM chat_conversations
        WHERE subject_id IS NULL
    """)

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_subject_unique "
        "ON chat_conversations(user_id, subject_id) WHERE subject_id IS NOT NULL"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_conversations_user "
        "ON chat_conversations(user_id, updated_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation "
        "ON chat_messages(conversation_id, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_quiz_attempts_quiz "
        "ON quiz_attempts(quiz_id, user_id)"
    )

    conn.commit()

    # =====================================================
    # DỌN LIÊN KẾT DỮ LIỆU CŨ BỊ MỒ CÔI
    # =====================================================
    # Môn đã xóa -> tài liệu / lịch học trở thành "Chưa phân loại".
    conn.execute("""
        UPDATE documents
        SET subject_id=NULL
        WHERE subject_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM subjects s
              WHERE s.id=documents.subject_id
                AND s.user_id=documents.user_id
          )
    """)

    conn.execute("""
        UPDATE study_tasks
        SET subject_id=NULL
        WHERE subject_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM subjects s
              WHERE s.id=study_tasks.subject_id
                AND s.user_id=study_tasks.user_id
          )
    """)

    # Quiz luôn đi theo môn của tài liệu gốc nếu tài liệu vẫn còn.
    conn.execute("""
        UPDATE quizzes
        SET subject_id=(
            SELECT d.subject_id
            FROM documents d
            WHERE d.id=quizzes.document_id
              AND d.user_id=quizzes.user_id
        )
        WHERE document_id IS NOT NULL
          AND EXISTS (
              SELECT 1
              FROM documents d
              WHERE d.id=quizzes.document_id
                AND d.user_id=quizzes.user_id
          )
    """)

    conn.execute("""
        UPDATE quizzes
        SET subject_id=NULL
        WHERE subject_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM subjects s
              WHERE s.id=quizzes.subject_id
                AND s.user_id=quizzes.user_id
          )
    """)

    # Xóa attempt mồ côi trước khi xóa quiz không còn tài liệu gốc.
    conn.execute("""
        DELETE FROM quiz_attempts
        WHERE NOT EXISTS (
            SELECT 1
            FROM quizzes q
            WHERE q.id=quiz_attempts.quiz_id
              AND q.user_id=quiz_attempts.user_id
        )
    """)

    orphan_quiz_ids = conn.execute("""
        SELECT q.id
        FROM quizzes q
        WHERE q.document_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM documents d
              WHERE d.id=q.document_id
                AND d.user_id=q.user_id
          )
    """).fetchall()

    for orphan in orphan_quiz_ids:
        conn.execute(
            "DELETE FROM quiz_attempts WHERE quiz_id=?",
            (orphan["id"],)
        )
        conn.execute(
            "DELETE FROM quizzes WHERE id=?",
            (orphan["id"],)
        )

    conn.commit()

    demo = conn.execute("SELECT id FROM users WHERE email=?", ("demo@study.local",)).fetchone()
    if not demo:
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
            ("Nguyễn Công Thành", "demo@study.local", generate_password_hash("123456"), now())
        )
        uid = cur.lastrowid
        subjects = [
            ("Trí tuệ nhân tạo", "Kiến thức nền tảng về AI, tìm kiếm và học máy", 75),
            ("Cơ sở dữ liệu", "SQL, mô hình quan hệ và thiết kế dữ liệu", 60),
            ("Lập trình Web", "Frontend, backend và triển khai web", 45),
        ]
        for s in subjects:
            conn.execute(
                "INSERT INTO subjects(user_id,name,description,progress,created_at) VALUES(?,?,?,?,?)",
                (uid, s[0], s[1], s[2], now())
            )
        reminders = [
            ("Ôn tập chương 3 - Trí tuệ nhân tạo", "2026-08-01T09:00"),
            ("Làm quiz chương 2", "2026-08-01T14:00"),
            ("Nộp bài tập lớn - Lập trình Web", "2026-08-02T23:59"),
        ]
        for title, due_at in reminders:
            conn.execute(
                "INSERT INTO reminders(user_id,title,due_at,created_at) VALUES(?,?,?,?)",
                (uid, title, due_at, now())
            )
        conn.commit()
    conn.close()

def now():
    return datetime.now().isoformat(timespec="seconds")


# =====================================================
# TỰ ĐỘNG TÍNH TIẾN ĐỘ MÔN HỌC
# =====================================================
def recalculate_subject_progress(user_id, subject_id, conn):
    """
    Công thức:
    - Có cả lịch học + quiz:
        60% mức hoàn thành lịch học
        40% điểm quiz trung bình (lấy điểm cao nhất của mỗi quiz)
    - Chỉ có lịch học: dùng % hoàn thành lịch học
    - Chỉ có quiz: dùng điểm quiz trung bình
    - Chưa có dữ liệu: 0%
    """

    if not subject_id:
        return 0

    subject = conn.execute(
        """
        SELECT id
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, user_id)
    ).fetchone()

    if not subject:
        return 0

    # -----------------------------------------------
    # % hoàn thành các buổi học của môn
    # -----------------------------------------------
    task_stats = conn.execute(
        """
        SELECT
            COUNT(*) AS total_tasks,
            COALESCE(
                SUM(CASE WHEN done=1 THEN 1 ELSE 0 END),
                0
            ) AS completed_tasks
        FROM study_tasks
        WHERE user_id=? AND subject_id=?
        """,
        (user_id, subject_id)
    ).fetchone()

    total_tasks = int(task_stats["total_tasks"] or 0)
    completed_tasks = int(task_stats["completed_tasks"] or 0)

    task_progress = (
        (completed_tasks / total_tasks) * 100
        if total_tasks > 0
        else None
    )

    # -----------------------------------------------
    # Điểm quiz:
    # mỗi quiz chỉ lấy lần làm có điểm cao nhất
    # -----------------------------------------------
    quiz_stats = conn.execute(
        """
        SELECT
            COUNT(*) AS quiz_count,
            AVG(best_score) AS avg_quiz_score
        FROM (
            SELECT
                qa.quiz_id,
                MAX(qa.score) AS best_score
            FROM quiz_attempts qa
            JOIN quizzes q
                ON q.id = qa.quiz_id
            WHERE qa.user_id=?
              AND q.user_id=?
              AND q.subject_id=?
            GROUP BY qa.quiz_id
        )
        """,
        (user_id, user_id, subject_id)
    ).fetchone()

    quiz_count = int(quiz_stats["quiz_count"] or 0)
    quiz_progress = (
        float(quiz_stats["avg_quiz_score"] or 0)
        if quiz_count > 0
        else None
    )

    # -----------------------------------------------
    # Ghép hai thành phần thành tiến độ cuối cùng
    # -----------------------------------------------
    if task_progress is not None and quiz_progress is not None:
        progress = round(
            task_progress * 0.60
            + quiz_progress * 0.40
        )
    elif task_progress is not None:
        progress = round(task_progress)
    elif quiz_progress is not None:
        progress = round(quiz_progress)
    else:
        progress = 0

    progress = max(0, min(100, progress))

    conn.execute(
        """
        UPDATE subjects
        SET progress=?
        WHERE id=? AND user_id=?
        """,
        (progress, subject_id, user_id)
    )

    return progress


def recalculate_all_subject_progress(user_id, conn):
    subject_rows = conn.execute(
        """
        SELECT id
        FROM subjects
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchall()

    for row in subject_rows:
        recalculate_subject_progress(
            user_id,
            row["id"],
            conn
        )

    conn.commit()

def owned_subject_id(conn, user_id, value):
    """Trả về subject_id nếu môn thuộc đúng user, ngược lại trả None."""
    if value in (None, ""):
        return None

    try:
        subject_id = int(value)
    except (TypeError, ValueError):
        return None

    row = conn.execute(
        "SELECT id FROM subjects WHERE id=? AND user_id=?",
        (subject_id, user_id)
    ).fetchone()

    return row["id"] if row else None


def ensure_subject_chats(user_id, conn):
    """Đảm bảo mỗi môn của user có đúng một Chat AI riêng."""
    subjects = conn.execute(
        """
        SELECT id, name, created_at
        FROM subjects
        WHERE user_id=?
        ORDER BY id ASC
        """,
        (user_id,)
    ).fetchall()

    for subject in subjects:
        chat = conn.execute(
            """
            SELECT id, title
            FROM chat_conversations
            WHERE user_id=? AND subject_id=?
            ORDER BY id ASC
            LIMIT 1
            """,
            (user_id, subject["id"])
        ).fetchone()

        if chat:
            if chat["title"] != subject["name"]:
                conn.execute(
                    """
                    UPDATE chat_conversations
                    SET title=?
                    WHERE id=? AND user_id=?
                    """,
                    (subject["name"], chat["id"], user_id)
                )
            continue

        created_at = subject["created_at"] or now()
        conn.execute(
            """
            INSERT INTO chat_conversations(
                user_id,subject_id,title,pinned,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                user_id,
                subject["id"],
                subject["name"],
                0,
                created_at,
                created_at
            )
        )

    conn.commit()



# =====================================================
# STUDY AGENT V2 - KIẾN THỨC CHUNG + CÁ NHÂN HÓA
# =====================================================
def _normalize_subject_key(code, name):
    """Khóa ổn định để nhiều sinh viên cùng môn dùng chung tri thức."""
    code_value = re.sub(r"\s+", "", (code or "").strip().lower())
    if code_value:
        return f"code:{code_value}"

    name_value = re.sub(
        r"[^\wÀ-ỹ]+",
        "-",
        (name or "").strip().lower(),
        flags=re.UNICODE
    ).strip("-")
    return f"name:{name_value or 'unknown'}"


def ensure_shared_subject_for_user_subject(conn, user_id, subject_id):
    """
    Liên kết môn cá nhân với một shared_subject.
    Các user có cùng mã môn (ưu tiên) hoặc cùng tên môn sẽ dùng chung kho tri thức.
    """
    subject = conn.execute(
        """
        SELECT id, user_id, name, code, description, shared_subject_id
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, user_id)
    ).fetchone()

    if not subject:
        return None

    if subject["shared_subject_id"]:
        shared = conn.execute(
            "SELECT * FROM shared_subjects WHERE id=?",
            (subject["shared_subject_id"],)
        ).fetchone()
        if shared:
            return shared

    subject_key = _normalize_subject_key(subject["code"], subject["name"])
    shared = conn.execute(
        "SELECT * FROM shared_subjects WHERE subject_key=?",
        (subject_key,)
    ).fetchone()

    if not shared:
        created_at = now()
        cur = conn.execute(
            """
            INSERT INTO shared_subjects(
                subject_key,code,name,description,syllabus_text,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                subject_key,
                subject["code"] or "",
                subject["name"],
                subject["description"] or "",
                "",
                created_at,
                created_at
            )
        )
        shared_id = cur.lastrowid
        shared = conn.execute(
            "SELECT * FROM shared_subjects WHERE id=?",
            (shared_id,)
        ).fetchone()

    conn.execute(
        """
        UPDATE subjects
        SET shared_subject_id=?
        WHERE id=? AND user_id=?
        """,
        (shared["id"], subject_id, user_id)
    )
    conn.commit()
    return shared


def ensure_learning_profile(conn, user_id):
    profile = conn.execute(
        "SELECT * FROM learning_profiles WHERE user_id=?",
        (user_id,)
    ).fetchone()

    if profile:
        return profile

    created_at = now()
    conn.execute(
        """
        INSERT INTO learning_profiles(
            user_id,learning_style,preferred_study_time,daily_minutes,
            goals,notes,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            user_id,
            "balanced",
            "19:00",
            45,
            "",
            "",
            created_at,
            created_at
        )
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM learning_profiles WHERE user_id=?",
        (user_id,)
    ).fetchone()


def get_shared_subject_context(user_id, subject_id, query="", max_chars=5500):
    """Ngữ cảnh dùng chung của môn: đề cương + ghi chú/tài liệu chung."""
    conn = db()
    shared = ensure_shared_subject_for_user_subject(
        conn,
        user_id,
        subject_id
    )

    if not shared:
        conn.close()
        return "", []

    parts = []
    source_labels = []
    total = 0

    syllabus_text = (shared["syllabus_text"] or "").strip()
    if syllabus_text:
        clipped = syllabus_text[:max_chars]
        parts.append(f"ĐỀ CƯƠNG MÔN HỌC:\n{clipped}")
        source_labels.append("Đề cương môn học")
        total += len(clipped)

    rows = conn.execute(
        """
        SELECT title, content, source_type
        FROM shared_knowledge
        WHERE shared_subject_id=?
        ORDER BY id DESC
        LIMIT 12
        """,
        (shared["id"],)
    ).fetchall()
    conn.close()

    query_terms = {
        token.lower()
        for token in re.findall(r"[\wÀ-ỹ]+", query or "", flags=re.UNICODE)
        if len(token) >= 2
    }

    scored = []
    for row in rows:
        content = (row["content"] or "").strip()
        if not content:
            continue
        lowered = content.lower()
        score = sum(lowered.count(term) for term in query_terms)
        scored.append((score, row["title"], row["source_type"], content))

    scored.sort(key=lambda item: item[0], reverse=True)

    for _, title, source_type, content in scored[:6]:
        remaining = max_chars - total
        if remaining <= 0:
            break
        clipped = content[:remaining]
        parts.append(
            f"KIẾN THỨC CHUNG - {title} ({source_type or 'note'}):\n{clipped}"
        )
        source_labels.append(title)
        total += len(clipped)

    return "\n\n".join(parts), source_labels


def get_personal_learning_context(user_id, subject_id, max_weaknesses=5):
    """Tóm tắt dữ liệu riêng của sinh viên để Agent cá nhân hóa câu trả lời."""
    conn = db()
    profile = ensure_learning_profile(conn, user_id)

    subject = conn.execute(
        """
        SELECT name,code,target_score,progress
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, user_id)
    ).fetchone()

    weaknesses = conn.execute(
        """
        SELECT topic,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
        ORDER BY (miss_count - correct_count * 0.5) DESC, last_seen_at DESC
        LIMIT ?
        """,
        (user_id, subject_id, max_weaknesses)
    ).fetchall()

    quiz_summary = conn.execute(
        """
        SELECT
            COUNT(DISTINCT qa.quiz_id) AS quiz_count,
            ROUND(AVG(qa.score), 1) AS avg_score
        FROM quiz_attempts qa
        JOIN quizzes q ON q.id=qa.quiz_id
        WHERE qa.user_id=? AND q.user_id=? AND q.subject_id=?
        """,
        (user_id, user_id, subject_id)
    ).fetchone()

    upcoming_tasks = conn.execute(
        """
        SELECT title,study_at,duration,done
        FROM study_tasks
        WHERE user_id=? AND subject_id=? AND done=0
        ORDER BY study_at ASC
        LIMIT 4
        """,
        (user_id, subject_id)
    ).fetchall()
    conn.close()

    lines = []
    if subject:
        lines.append(
            f"Môn: {subject['name']} ({subject['code'] or 'chưa có mã'}); "
            f"mục tiêu điểm: {subject['target_score'] or 0}; "
            f"tiến độ hiện tại: {subject['progress'] or 0}%."
        )

    lines.append(
        "Hồ sơ học tập: "
        f"phong cách={profile['learning_style'] or 'balanced'}, "
        f"giờ ưu tiên={profile['preferred_study_time'] or '19:00'}, "
        f"thời lượng/buổi={profile['daily_minutes'] or 45} phút."
    )

    if (profile["goals"] or "").strip():
        lines.append(f"Mục tiêu cá nhân: {profile['goals'].strip()}")

    if quiz_summary and int(quiz_summary["quiz_count"] or 0) > 0:
        lines.append(
            f"Quiz đã làm: {int(quiz_summary['quiz_count'] or 0)}; "
            f"điểm trung bình các lần làm: {quiz_summary['avg_score'] or 0}%."
        )

    if weaknesses:
        weak_text = "; ".join(
            f"{row['topic']} (sai {row['miss_count']}, đúng {row['correct_count']})"
            for row in weaknesses
        )
        lines.append(f"Phần kiến thức cần chú ý: {weak_text}")

    if upcoming_tasks:
        task_text = "; ".join(
            f"{row['title']} lúc {row['study_at']} ({row['duration']} phút)"
            for row in upcoming_tasks
        )
        lines.append(f"Nhiệm vụ sắp tới: {task_text}")

    return "\n".join(lines)


def _quiz_topic_key(question_text):
    normalized = re.sub(
        r"[^\wÀ-ỹ]+",
        " ",
        (question_text or "").strip().lower(),
        flags=re.UNICODE
    )
    return re.sub(r"\s+", " ", normalized).strip()[:180]


def record_quiz_learning_signal(
    conn,
    user_id,
    subject_id,
    question_text,
    is_correct
):
    """Ghi nhận câu sai/đúng để Agent biết phần sinh viên đang yếu."""
    if not subject_id:
        return

    topic = re.sub(r"\s+", " ", (question_text or "").strip())[:220]
    topic_key = _quiz_topic_key(topic)
    if not topic_key:
        return

    row = conn.execute(
        """
        SELECT id,miss_count,correct_count
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=? AND topic_key=?
        """,
        (user_id, subject_id, topic_key)
    ).fetchone()

    if row:
        conn.execute(
            """
            UPDATE learning_weaknesses
            SET miss_count=?,
                correct_count=?,
                topic=?,
                last_seen_at=?
            WHERE id=?
            """,
            (
                int(row["miss_count"] or 0) + (0 if is_correct else 1),
                int(row["correct_count"] or 0) + (1 if is_correct else 0),
                topic,
                now(),
                row["id"]
            )
        )
    else:
        conn.execute(
            """
            INSERT INTO learning_weaknesses(
                user_id,subject_id,topic_key,topic,
                miss_count,correct_count,last_seen_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                user_id,
                subject_id,
                topic_key,
                topic,
                0 if is_correct else 1,
                1 if is_correct else 0,
                now()
            )
        )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text(path: Path):
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")[:100000]
    if ext == ".pdf" and PdfReader:
        try:
            reader = PdfReader(str(path))
            chunks = []
            for page in reader.pages[:80]:
                chunks.append(page.extract_text() or "")
            return "\n".join(chunks)[:100000]
        except Exception:
            return ""
    return ""

def get_subject_context(user_id, subject_id, query, max_chars=10000):
    """
    Lấy ngữ cảnh CHỈ từ tài liệu của môn đang chat.
    Trả về (context, source_names).
    """
    if not subject_id:
        return "", []

    conn = db()
    rows = conn.execute(
        """
        SELECT original_name, extracted_text
        FROM documents
        WHERE user_id=? AND subject_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id, subject_id)
    ).fetchall()
    conn.close()

    rows = [row for row in rows if (row["extracted_text"] or "").strip()]
    if not rows:
        return "", []

    stop_words = {
        "là", "gì", "có", "và", "của", "cho", "với", "trong", "một",
        "những", "các", "này", "đó", "được", "về", "theo", "tại", "khi",
        "ai", "em", "tui", "mình", "hãy", "giúp", "cho", "biết"
    }

    terms = {
        token.lower()
        for token in re.findall(r"[\wÀ-ỹ]+", query, flags=re.UNICODE)
        if len(token) >= 2 and token.lower() not in stop_words
    }

    query_lower = (query or "").lower()
    document_intent = any(
        phrase in query_lower
        for phrase in (
            "tóm tắt", "tài liệu", "file", "nội dung", "bài giảng",
            "chương", "đã tải", "đã up", "trong bài"
        )
    )

    scored_docs = []

    for row in rows:
        text_value = row["extracted_text"] or ""
        lowered = text_value.lower()
        score = sum(lowered.count(term) for term in terms)

        if document_intent:
            score += 1

        paragraphs = [
            p.strip()
            for p in re.split(r"\n{2,}|(?<=[.!?])\s+", text_value)
            if len(p.strip()) >= 30
        ]

        paragraph_scores = []
        for paragraph in paragraphs:
            p_lower = paragraph.lower()
            p_score = sum(p_lower.count(term) for term in terms)
            if p_score > 0:
                paragraph_scores.append((p_score, paragraph))

        paragraph_scores.sort(key=lambda item: item[0], reverse=True)

        if paragraph_scores:
            snippet_parts = []
            snippet_length = 0
            for _, paragraph in paragraph_scores[:5]:
                if snippet_length + len(paragraph) > 2600:
                    break
                snippet_parts.append(paragraph)
                snippet_length += len(paragraph)
            snippet = "\n".join(snippet_parts)
        else:
            snippet = text_value[:1800]

        scored_docs.append((score, row["original_name"], snippet))

    scored_docs.sort(key=lambda item: item[0], reverse=True)

    # Nếu có tài liệu, vẫn đưa một lượng ngữ cảnh nhỏ cho Gemini.
    # Gemini sẽ tự quyết định ngữ cảnh có đủ để trả lời hay phải dùng kiến thức chung.
    selected = scored_docs[:4]
    context_parts = []
    source_names = []
    total = 0

    for _, name, snippet in selected:
        if not snippet:
            continue

        remaining = max_chars - total
        if remaining <= 0:
            break

        clipped = snippet[:remaining]
        context_parts.append(f"FILE: {name}\n{clipped}")
        source_names.append(name)
        total += len(clipped)

    return "\n\n".join(context_parts), source_names

def local_ai_answer(question, context, source_names=None):
    source_names = source_names or []

    if context:
        keywords = [
            w.lower()
            for w in re.findall(r"[\wÀ-ỹ]+", question, flags=re.UNICODE)
            if len(w) > 2
        ]
        best = ""
        best_score = -1

        for para in re.split(r"\n{2,}", context):
            score = sum(para.lower().count(k) for k in keywords)
            if score > best_score and len(para.strip()) > 40:
                best, best_score = para.strip(), score

        if best:
            if len(source_names) == 1:
                source_line = f'Dựa trên tài liệu "{source_names[0]}":'
            else:
                joined = ", ".join(f'"{name}"' for name in source_names)
                source_line = f"Dựa trên các tài liệu {joined}:"

            return (
                source_line
                + "\n\n"
                + best[:1500]
                + "\n\nĐây là phản hồi dự phòng cục bộ vì Gemini chưa khả dụng."
            )

    return (
        "Gemini hiện chưa khả dụng nên hệ thống chưa thể trả lời bằng kiến thức chung. "
        "Hãy kiểm tra GEMINI_API_KEY hoặc kết nối mạng rồi thử lại."
    )

def gemini_generate(prompt):
    """Gửi một prompt tới Gemini và trả về (text, error)."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return None, "Chưa cấu hình GEMINI_API_KEY trong file .env."

    if requests is None:
        return None, "Thiếu thư viện requests."

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite"

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model}:generateContent"
    )

    try:
        res = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json={
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt}
                        ],
                    }
                ]
            },
            timeout=45,
        )

        if res.status_code == 429:
            return None, (
                "Gemini đang vượt giới hạn sử dụng (HTTP 429). "
                "Hãy đợi một lúc rồi thử lại hoặc kiểm tra quota."
            )

        if not res.ok:
            detail = ""
            try:
                error_data = res.json()
                detail = (
                    error_data.get("error", {}).get("message", "")
                    if isinstance(error_data, dict)
                    else ""
                )
            except ValueError:
                detail = res.text[:300]

            message = f"Gemini API lỗi HTTP {res.status_code}"
            if detail:
                message += f": {detail}"
            return None, message

        data = res.json()
        candidates = data.get("candidates") or []

        if not candidates:
            return None, "Gemini không trả về candidate nào."

        content = candidates[0].get("content") or {}
        parts = content.get("parts") or []

        answer_parts = [
            str(part.get("text", "")).strip()
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ]

        answer = "\n".join(part for part in answer_parts if part).strip()

        if not answer:
            return None, "Gemini trả về phản hồi rỗng."

        return answer, None

    except requests.RequestException as exc:
        return None, f"Lỗi kết nối Gemini: {exc}"

    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return None, f"Không đọc được phản hồi Gemini: {exc}"


def gemini_subject_answer(
    subject_name,
    question,
    context,
    source_names,
    conversation_history="",
    shared_context="",
    personal_context=""
):
    """
    Trả lời theo môn học:
    - Có tài liệu phù hợp: ưu tiên tài liệu và ghi rõ tên file.
    - Tài liệu không đủ / không liên quan: dùng kiến thức chung, không gắn nguồn file.
    - Không có tài liệu: dùng kiến thức chung, không gắn nguồn file.
    """
    source_names = source_names or []
    sources_text = ", ".join(source_names) if source_names else "Không có"

    prompt = f"""
Bạn là AI Study Agent đang hỗ trợ môn học: {subject_name}.

MỤC TIÊU:
Trả lời câu hỏi của sinh viên bằng tiếng Việt, rõ ràng, dễ học và chính xác.
Nếu có HỒ SƠ HỌC TẬP CÁ NHÂN, hãy điều chỉnh cách giải thích theo mục tiêu,
tiến độ và những phần sinh viên thường sai. Không nhắc lại dữ liệu cá nhân
một cách máy móc nếu không cần thiết.

QUY TẮC NGUỒN RẤT QUAN TRỌNG:
1. Nếu NGỮ CẢNH TÀI LIỆU bên dưới thực sự chứa đủ thông tin để hỗ trợ câu trả lời,
   hãy đặt mode = "document" và chỉ liệt kê những file thực sự dùng trong sources.
2. Nếu tài liệu không có, không liên quan hoặc không đủ để trả lời,
   hãy đặt mode = "general" và trả lời bằng kiến thức chung của mô hình.
3. Khi mode = "general", sources phải là mảng rỗng.
4. Không được giả vờ rằng thông tin nằm trong tài liệu nếu tài liệu không hỗ trợ.
5. Nếu vừa dùng tài liệu vừa cần bổ sung một phần nhỏ bằng kiến thức chung,
   vẫn có thể dùng mode = "document", nhưng phải phân biệt rõ phần nào là bổ sung nếu điều đó quan trọng.
6. Không sao chép nguyên văn dài từ tài liệu.

CÁC FILE ĐƯỢC CUNG CẤP TRONG NGỮ CẢNH:
{sources_text}

NGỮ CẢNH TÀI LIỆU CÁ NHÂN:
{context[:9000] if context else "Không có tài liệu cá nhân của môn học này trong ngữ cảnh."}

KIẾN THỨC CHUNG THEO MÔN:
{shared_context[:5500] if shared_context else "Chưa có kiến thức dùng chung cho môn này."}

HỒ SƠ HỌC TẬP CÁ NHÂN:
{personal_context[:3500] if personal_context else "Chưa có dữ liệu cá nhân hóa."}

LỊCH SỬ TRÒ CHUYỆN GẦN ĐÂY:
{conversation_history[:3500] if conversation_history else "Chưa có nội dung trước đó."}

CÂU HỎI HIỆN TẠI:
{question}

CHỈ trả về JSON hợp lệ, không markdown, theo đúng cấu trúc:
{{
  "mode": "document" hoặc "general",
  "sources": ["ten_file_1.pdf"],
  "answer": "Nội dung trả lời"
}}
""".strip()

    raw, error = gemini_generate(prompt)

    if raw:
        try:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                raise ValueError("Không tìm thấy JSON object")

            data = json.loads(match.group(0))
            answer = str(data.get("answer") or "").strip()
            mode = str(data.get("mode") or "general").strip().lower()
            requested_sources = data.get("sources") or []

            allowed = {name: name for name in source_names}
            used_sources = []

            if isinstance(requested_sources, list):
                for item in requested_sources:
                    name = str(item or "").strip()
                    if name in allowed and name not in used_sources:
                        used_sources.append(name)

            if not answer:
                raise ValueError("Gemini trả về answer rỗng")

            if mode == "document" and used_sources:
                if len(used_sources) == 1:
                    source_line = f'Dựa trên tài liệu "{used_sources[0]}":'
                else:
                    joined = ", ".join(f'"{name}"' for name in used_sources)
                    source_line = f"Dựa trên các tài liệu {joined}:"

                return source_line + "\n\n" + answer, used_sources, "document"

            # Không có nguồn hợp lệ -> coi là kiến thức chung để tránh gắn nguồn sai.
            return answer, [], "general"

        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            print("Không đọc được JSON Chat từ Gemini:", exc)
            # Không gắn tên file khi không xác định chắc chắn mode nguồn.
            cleaned = raw.strip()
            return cleaned, [], "general"

    if not os.getenv("GEMINI_API_KEY", "").strip() or requests is None:
        fallback = local_ai_answer(question, context, source_names)
        return fallback, source_names if context else [], "document" if context else "general"

    return (
        "Không thể kết nối Gemini lúc này. " + (error or "Bạn thử lại sau nhé."),
        [],
        "general"
    )


def build_quiz(text, question_count=10):
    """
    Tạo quiz 10 / 20 / 30 câu bằng Gemini.

    Để tránh Gemini trả thiếu câu khi yêu cầu quá dài,
    hệ thống tạo theo từng nhóm tối đa 10 câu rồi ghép lại.
    """

    # =====================================================
    # CHỈ CHO PHÉP 10 / 20 / 30
    # =====================================================
    try:
        question_count = int(question_count)
    except (TypeError, ValueError):
        question_count = 10

    if question_count not in (10, 20, 30):
        question_count = 10

    clean_text = (text or "").strip()


    # =====================================================
    # FALLBACK CỤC BỘ
    # =====================================================
    def fallback_quiz(limit):
        sentences = [
            s.strip()
            for s in re.split(
                r"(?<=[.!?])\s+",
                clean_text
            )
            if 35 <= len(s.strip()) <= 500
        ]

        questions = []
        used_questions = set()

        for sentence in sentences:
            if len(questions) >= limit:
                break

            words = [
                w
                for w in re.findall(
                    r"\b[\wÀ-ỹ]+\b",
                    sentence
                )
                if len(w) >= 5
            ]

            if not words:
                continue

            answer = max(words, key=len)

            masked = re.sub(
                re.escape(answer),
                "______",
                sentence,
                count=1,
                flags=re.IGNORECASE
            )

            question_text = f"Điền từ phù hợp: {masked}"
            normalized = question_text.casefold()

            if normalized in used_questions:
                continue

            used_questions.add(normalized)

            questions.append({
                "question": question_text,
                "options": [
                    answer,
                    "Dữ liệu",
                    "Hệ thống",
                    "Thuật toán"
                ],
                "answer": 0
            })

        if not questions:
            questions = [
                {
                    "question": "AI Study Agent có mục tiêu chính là gì?",
                    "options": [
                        "Hỗ trợ sinh viên học tập",
                        "Bán sản phẩm",
                        "Quản lý giao thông",
                        "Chỉnh sửa hình ảnh"
                    ],
                    "answer": 0
                }
            ]

        return questions[:limit]


    if not clean_text:
        return fallback_quiz(question_count)


    # =====================================================
    # VALIDATE 1 CÂU HỎI GEMINI
    # =====================================================
    def normalize_question(item):
        if not isinstance(item, dict):
            return None

        question = str(
            item.get("question", "")
        ).strip()

        options = item.get(
            "options",
            []
        )

        answer = item.get(
            "answer"
        )

        if not question:
            return None

        if (
            not isinstance(options, list)
            or len(options) != 4
        ):
            return None

        options = [
            str(option).strip()
            for option in options
        ]

        if any(
            not option
            for option in options
        ):
            return None

        if len({
            option.casefold()
            for option in options
        }) != 4:
            return None

        try:
            answer = int(answer)
        except (TypeError, ValueError):
            return None

        if answer not in (0, 1, 2, 3):
            return None

        return {
            "question": question,
            "options": options,
            "answer": answer
        }


    # =====================================================
    # GỌI GEMINI CHO 1 NHÓM NHỎ
    # =====================================================
    def generate_batch(batch_size, existing_questions, batch_number):
        # Giới hạn context để request ổn định.
        document_content = clean_text[:16000]

        avoid_text = ""

        if existing_questions:
            # Chỉ gửi phần câu hỏi để Gemini tránh lặp,
            # không cần gửi lại options/answer.
            avoid_lines = [
                f"- {q['question']}"
                for q in existing_questions[-25:]
            ]

            avoid_text = (
                "\\nCÁC CÂU ĐÃ TẠO - KHÔNG ĐƯỢC LẶP LẠI:\\n"
                + "\\n".join(avoid_lines)
            )

        prompt = f"""
Bạn là AI Study Agent.

Nhiệm vụ:
Tạo đúng {batch_size} câu hỏi trắc nghiệm bằng tiếng Việt
cho NHÓM {batch_number}, dựa CHỈ trên nội dung tài liệu.

TÀI LIỆU:
{document_content}
{avoid_text}

YÊU CẦU BẮT BUỘC:
- Phải trả về đúng {batch_size} câu hợp lệ.
- Mỗi câu có đúng 4 đáp án.
- Chỉ có 1 đáp án đúng.
- Các đáp án sai phải hợp lý và cùng chủ đề.
- Không lặp câu hỏi đã tạo trước đó.
- Không tạo câu hỏi vô nghĩa kiểu xóa một từ ngẫu nhiên.
- Không hỏi thông tin không có trong tài liệu.
- Ưu tiên phủ nhiều phần kiến thức khác nhau trong tài liệu.
- answer là vị trí đáp án đúng: 0=A, 1=B, 2=C, 3=D.

CHỈ trả về JSON array.
Không markdown.
Không ```json.
Không giải thích thêm.

Cấu trúc:
[
  {{
    "question": "Nội dung câu hỏi",
    "options": [
      "Đáp án A",
      "Đáp án B",
      "Đáp án C",
      "Đáp án D"
    ],
    "answer": 0
  }}
]
""".strip()

        raw, error = gemini_generate(prompt)

        if not raw:
            print(
                f"Gemini tạo Quiz nhóm {batch_number} thất bại:",
                error
            )
            return []

        try:
            match = re.search(
                r"\[[\s\S]*\]",
                raw
            )

            if not match:
                return []

            data = json.loads(
                match.group(0)
            )

            if not isinstance(data, list):
                return []

            result = []

            for item in data:
                normalized = normalize_question(item)

                if normalized:
                    result.append(normalized)

                if len(result) >= batch_size:
                    break

            return result

        except (
            ValueError,
            TypeError,
            json.JSONDecodeError
        ) as exc:
            print(
                f"Lỗi đọc Quiz nhóm {batch_number}:",
                exc
            )
            return []


    # =====================================================
    # TẠO THEO NHÓM TỐI ĐA 10 CÂU
    # 10 -> 1 lần gọi
    # 20 -> 2 lần gọi
    # 30 -> 3 lần gọi
    # =====================================================
    questions = []
    used_question_texts = set()

    remaining = question_count
    batch_number = 1
    attempts = 0

    # Cho phép retry nếu một nhóm trả thiếu câu.
    while remaining > 0 and attempts < 6:
        batch_size = min(10, remaining)

        batch = generate_batch(
            batch_size,
            questions,
            batch_number
        )

        added = 0

        for item in batch:
            normalized_text = re.sub(
                r"\s+",
                " ",
                item["question"].casefold()
            ).strip()

            if normalized_text in used_question_texts:
                continue

            used_question_texts.add(
                normalized_text
            )

            questions.append(item)
            added += 1

            if len(questions) >= question_count:
                break

        remaining = (
            question_count
            - len(questions)
        )

        attempts += 1

        # Chỉ tăng nhóm khi có thêm câu.
        # Nếu Gemini trả thiếu/rỗng, lần retry tiếp theo vẫn yêu cầu phần còn thiếu.
        if added > 0:
            batch_number += 1


    # =====================================================
    # NẾU GEMINI THIẾU MỘT ÍT CÂU -> BÙ BẰNG FALLBACK
    # =====================================================
    if len(questions) < question_count:
        fallback_items = fallback_quiz(
            question_count
        )

        for item in fallback_items:
            normalized_text = re.sub(
                r"\s+",
                " ",
                item["question"].casefold()
            ).strip()

            if normalized_text in used_question_texts:
                continue

            used_question_texts.add(
                normalized_text
            )

            questions.append(item)

            if len(questions) >= question_count:
                break


    if not questions:
        return fallback_quiz(
            question_count
        )


    return questions[:question_count]

def _safe_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _fallback_study_plan(subject_name, goal, deadline_dt, daily_minutes, preferred_time):
    """Tạo kế hoạch cục bộ khi Gemini chưa cấu hình hoặc API gặp lỗi."""
    today = datetime.now().date()
    end_date = max(today, deadline_dt.date())
    span_days = max(0, (end_date - today).days)

    if span_days == 0:
        session_count = 1
    elif span_days <= 3:
        session_count = span_days + 1
    else:
        session_count = min(8, max(4, (span_days + 1) // 2))

    templates = [
        ("Xác định nội dung cần hoàn thành", "Xem mục tiêu và chia phần kiến thức cần học."),
        ("Đọc tài liệu và ghi chú ý chính", "Tập trung vào khái niệm, ví dụ và phần chưa hiểu."),
        ("Ôn phần kiến thức chưa vững", "Đọc lại ghi chú và đánh dấu nội dung cần hỏi thêm."),
        ("Hỏi AI phần chưa hiểu", "Dùng AI Chat để giải thích các ý còn mơ hồ."),
        ("Làm quiz kiểm tra", "Làm quiz để kiểm tra mức độ ghi nhớ."),
        ("Xem lại câu sai", "Ôn nguyên nhân sai và ghi lại kiến thức cần nhớ."),
        ("Ôn tập tổng hợp", "Kết nối các phần kiến thức và làm lại nội dung khó."),
        ("Tổng kết trước deadline", "Rà soát mục tiêu và hoàn thiện phần còn thiếu."),
    ]

    tasks = []
    for i in range(session_count):
        if session_count == 1:
            offset = 0
        else:
            offset = round(i * span_days / (session_count - 1))
        task_date = today + timedelta(days=offset)
        title, note = templates[min(i, len(templates) - 1)]
        if i == 0:
            note = f"Mục tiêu: {goal}. " + note
        tasks.append({
            "date": task_date.isoformat(),
            "time": preferred_time,
            "title": title,
            "duration": daily_minutes,
            "note": note,
        })
    return tasks


def build_study_plan(subject_name, goal, deadline_dt, daily_minutes, preferred_time, context=""):
    """Ưu tiên Gemini; nếu API lỗi sẽ dùng kế hoạch cục bộ."""
    fallback = _fallback_study_plan(
        subject_name,
        goal,
        deadline_dt,
        daily_minutes,
        preferred_time,
    )

    today = datetime.now().date().isoformat()
    deadline_date = deadline_dt.date().isoformat()

    prompt = f"""
Bạn là AI Study Planner cho sinh viên.

Hãy tạo một lịch học thực tế cho:
- Môn học: {subject_name}
- Mục tiêu: {goal}
- Ngày hiện tại: {today}
- Deadline: {deadline_date}
- Thời lượng tối đa mỗi buổi: {daily_minutes} phút
- Giờ học ưu tiên: {preferred_time}

NGỮ CẢNH TÀI LIỆU:
{context[:3500] if context else "Không có tài liệu cho môn học này."}

Yêu cầu:
- Không cố định 7 ngày; số buổi phải phù hợp với thời gian còn lại.
- Tối đa 8 buổi.
- Mọi ngày học phải nằm từ {today} đến {deadline_date}.
- Mỗi buổi phải có công việc rõ ràng, ngắn gọn và thực tế.
- Ưu tiên nội dung có trong tài liệu nếu có.
- Có thể kết hợp đọc tài liệu, ghi chú, hỏi AI Chat, làm Quiz, xem lại câu sai và ôn tổng hợp khi phù hợp.
- Không tạo công việc ngoài phạm vi học tập.
- Chỉ trả về một JSON array, không markdown và không giải thích thêm.
- Mỗi phần tử phải có đúng các trường:
  {{"date":"YYYY-MM-DD","time":"HH:MM","title":"...","duration":45,"note":"..."}}
""".strip()

    raw, error = gemini_generate(prompt)

    if not raw:
        if error:
            print("Study planner Gemini fallback:", error)
        return fallback

    try:
        match = re.search(r"\[[\s\S]*\]", raw)
        if not match:
            return fallback

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, list) or not parsed:
            return fallback

        valid = []
        start_date = datetime.now().date()
        end_date = deadline_dt.date()

        for item in parsed[:8]:
            if not isinstance(item, dict):
                continue

            try:
                date_value = datetime.strptime(
                    str(item.get("date", "")),
                    "%Y-%m-%d"
                ).date()
            except ValueError:
                continue

            if date_value < start_date or date_value > end_date:
                continue

            time_value = str(item.get("time") or preferred_time).strip()
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
                time_value = preferred_time

            title = str(item.get("title") or "Buổi học").strip()[:160]
            note = str(item.get("note") or "").strip()[:500]

            duration = _safe_int(
                item.get("duration"),
                daily_minutes,
                15,
                daily_minutes,
            )

            valid.append({
                "date": date_value.isoformat(),
                "time": time_value,
                "title": title or "Buổi học",
                "duration": duration,
                "note": note,
            })

        return valid or fallback

    except (ValueError, TypeError, KeyError) as exc:
        print("Study planner JSON fallback:", exc)
        return fallback


def _format_weekday(dt):
    labels = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    return labels[dt.weekday()]


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        error = "Email hoặc mật khẩu không đúng."
    return render_template("login.html", error=error)

@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not name or not email or len(password) < 6:
        return redirect(url_for("login"))

    conn = db()
    try:
        cur = conn.execute(
            "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
            (name, email, generate_password_hash(password), now())
        )
        conn.commit()
        session["user_id"] = cur.lastrowid
        session["user_name"] = name
        return redirect(url_for("dashboard"))
    except sqlite3.IntegrityError:
        conn.rollback()
        return redirect(url_for("login"))
    finally:
        conn.close()

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = db()

    # Đồng bộ tiến độ môn học trước khi hiển thị Dashboard
    recalculate_all_subject_progress(uid, conn)

    subjects = conn.execute(
        """
        SELECT *
        FROM subjects
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (uid,)
    ).fetchall()

    documents = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (uid,)
    ).fetchall()

    # Số quiz đã thực sự làm, không phải số quiz đã tạo.
    quiz_count = conn.execute(
        """
        SELECT COUNT(DISTINCT quiz_id) AS c
        FROM quiz_attempts
        WHERE user_id=?
        """,
        (uid,)
    ).fetchone()["c"]

    # =====================================================
    # BIỂU ĐỒ THỜI GIAN HỌC TUẦN NÀY
    # Chỉ tính các study_tasks đã đánh dấu hoàn thành.
    # =====================================================
    now_dt = datetime.now()

    week_start = (
        now_dt
        - timedelta(days=now_dt.weekday())
    ).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    week_end = week_start + timedelta(days=7)
    previous_week_start = week_start - timedelta(days=7)

    completed_task_rows = conn.execute(
        """
        SELECT completed_at, duration
        FROM study_tasks
        WHERE user_id=?
          AND done=1
          AND completed_at IS NOT NULL
          AND completed_at<>''
          AND completed_at>=?
          AND completed_at<?
        ORDER BY completed_at ASC
        """,
        (
            uid,
            previous_week_start.isoformat(timespec="minutes"),
            week_end.isoformat(timespec="minutes")
        )
    ).fetchall()

    weekly_minutes = [0, 0, 0, 0, 0, 0, 0]
    previous_week_minutes = 0

    for row in completed_task_rows:
        try:
            study_dt = datetime.fromisoformat(row["completed_at"])
        except (TypeError, ValueError):
            continue

        duration = _safe_int(
            row["duration"],
            45,
            0,
            1440
        )

        if week_start <= study_dt < week_end:
            weekly_minutes[study_dt.weekday()] += duration

        elif previous_week_start <= study_dt < week_start:
            previous_week_minutes += duration

    weekly_study_hours = [
        round(minutes / 60, 2)
        for minutes in weekly_minutes
    ]

    weekly_total_hours = round(
        sum(weekly_minutes) / 60,
        1
    )

    previous_week_hours = round(
        previous_week_minutes / 60,
        1
    )

    if previous_week_minutes > 0:
        growth = round(
            (
                (
                    sum(weekly_minutes)
                    - previous_week_minutes
                )
                / previous_week_minutes
            ) * 100
        )

        if growth > 0:
            weekly_growth_text = (
                f"↗ +{growth}% so với tuần trước"
            )
            weekly_growth_class = "up"

        elif growth < 0:
            weekly_growth_text = (
                f"↘ {growth}% so với tuần trước"
            )
            weekly_growth_class = "down"

        else:
            weekly_growth_text = (
                "→ Bằng tuần trước"
            )
            weekly_growth_class = "neutral"

    elif sum(weekly_minutes) > 0:
        weekly_growth_text = (
            f"{weekly_total_hours:g} giờ tuần này"
        )
        weekly_growth_class = "neutral"

    else:
        weekly_growth_text = (
            "Chưa có buổi học hoàn thành"
        )
        weekly_growth_class = "neutral"

    # =====================================================
    # NHẮC VIỆC / DEADLINE GẦN NHẤT
    # =====================================================
    reminder_rows = conn.execute(
        """
        SELECT *
        FROM reminders
        WHERE user_id=?
        ORDER BY
            done ASC,
            CASE
                WHEN due_at='' THEN 1
                ELSE 0
            END,
            due_at ASC,
            id DESC
        LIMIT 6
        """,
        (uid,)
    ).fetchall()

    reminders = []

    for row in reminder_rows:
        item = dict(row)

        try:
            due_dt = (
                datetime.fromisoformat(row["due_at"])
                if row["due_at"]
                else None
            )
        except (TypeError, ValueError):
            due_dt = None

        if due_dt:
            item["due_text"] = (
                due_dt.strftime(
                    "%d/%m/%Y • %H:%M"
                )
            )
        else:
            item["due_text"] = (
                "Chưa đặt thời gian"
            )

        if row["done"]:
            item["status_text"] = "Đã xong"
            item["status_class"] = "done"

        elif due_dt and due_dt < now_dt:
            item["status_text"] = "Quá hạn"
            item["status_class"] = "late"

        elif due_dt:
            days_left = (
                due_dt.date()
                - now_dt.date()
            ).days

            if days_left == 0:
                item["status_text"] = "Hôm nay"
                item["status_class"] = "today"
            elif days_left == 1:
                item["status_text"] = "Còn 1 ngày"
                item["status_class"] = "soon"
            elif days_left == 2:
                item["status_text"] = "Còn 2 ngày"
                item["status_class"] = "soon"
            else:
                item["status_text"] = ""
                item["status_class"] = ""
        else:
            item["status_text"] = ""
            item["status_class"] = ""

        reminders.append(item)

    conn.close()

    avg_progress = (
        round(
            sum(
                int(s["progress"] or 0)
                for s in subjects
            ) / len(subjects)
        )
        if subjects
        else 0
    )

    return render_template(
        "dashboard.html",
        page="dashboard",
        subjects=subjects,
        documents=documents,
        reminders=reminders,
        quiz_count=quiz_count,
        avg_progress=avg_progress,
        weekly_study_hours=weekly_study_hours,
        weekly_total_hours=weekly_total_hours,
        previous_week_hours=previous_week_hours,
        weekly_growth_text=weekly_growth_text,
        weekly_growth_class=weekly_growth_class
    )

@app.route("/subjects", methods=["GET", "POST"])
@login_required
def subjects():
    uid = session["user_id"]
    conn = db()

    if request.method == "POST":

        name = (
            request.form.get("name", "").strip()
            or "Môn học mới"
        )

        code = request.form.get(
            "code",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        try:
            credits = int(
                request.form.get(
                    "credits",
                    0
                ) or 0
            )
        except ValueError:
            credits = 0

        try:
            target_score = float(
                request.form.get(
                    "target_score",
                    0
                ) or 0
            )
        except ValueError:
            target_score = 0


        created_at = now()
        cursor = conn.execute(
            """
            INSERT INTO subjects(
                user_id,
                name,
                code,
                description,
                credits,
                target_score,
                progress,
                created_at
            )
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                name,
                code,
                description,
                credits,
                target_score,
                0,
                created_at
            )
        )

        subject_id = cursor.lastrowid

        # Tạo luôn không gian AI Chat cùng tên môn học.
        conn.execute(
            """
            INSERT INTO chat_conversations(
                user_id,subject_id,title,pinned,created_at,updated_at
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                uid,
                subject_id,
                name,
                0,
                created_at,
                created_at
            )
        )

        conn.commit()
        conn.close()

        return redirect(
            url_for("subjects")
        )


    # Tự tính lại % tiến độ từ Study Plan + Quiz
    recalculate_all_subject_progress(uid, conn)

    rows = conn.execute(
        """
        SELECT *
        FROM subjects
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (uid,)
    ).fetchall()

    conn.close()

    return render_template(
        "subjects.html",
        page="subjects",
        subjects=rows
    )

@app.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete_subject(subject_id):
    uid = session["user_id"]
    conn = db()

    subject = conn.execute(
        "SELECT id FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()

    if subject:
        # Chat gắn 1-1 với môn học: xóa môn thì xóa luôn lịch sử Chat của môn.
        chat_rows = conn.execute(
            """
            SELECT id
            FROM chat_conversations
            WHERE subject_id=? AND user_id=?
            """,
            (subject_id, uid)
        ).fetchall()

        for chat_row in chat_rows:
            conn.execute(
                "DELETE FROM chat_messages WHERE conversation_id=? AND user_id=?",
                (chat_row["id"], uid)
            )

        conn.execute(
            "DELETE FROM chat_conversations WHERE subject_id=? AND user_id=?",
            (subject_id, uid)
        )

        # Giữ tài liệu/quiz/lịch học, nhưng chuyển về trạng thái chưa phân loại.
        conn.execute(
            "UPDATE documents SET subject_id=NULL WHERE subject_id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.execute(
            "UPDATE quizzes SET subject_id=NULL WHERE subject_id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.execute(
            "UPDATE study_tasks SET subject_id=NULL WHERE subject_id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.execute(
            "DELETE FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.commit()

    conn.close()
    return redirect(url_for("subjects"))

@app.route("/documents", methods=["GET", "POST"])
@login_required
def documents():
    uid = session["user_id"]
    conn = db()

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename and allowed_file(file.filename):
            original = secure_filename(file.filename)
            stored = f"{uid}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original}"
            target = UPLOAD_DIR / stored
            file.save(target)
            text_content = extract_text(target)
            subject_id = owned_subject_id(
                conn,
                uid,
                request.form.get("subject_id")
            )

            conn.execute(
                """
                INSERT INTO documents(
                    user_id,subject_id,original_name,stored_name,extracted_text,created_at
                ) VALUES(?,?,?,?,?,?)
                """,
                (uid, subject_id, original, stored, text_content, now())
            )
            conn.commit()

        conn.close()
        return redirect(url_for("documents"))

    docs = conn.execute(
        """
        SELECT d.*, s.name AS subject_name
        FROM documents d
        LEFT JOIN subjects s
          ON s.id=d.subject_id AND s.user_id=d.user_id
        WHERE d.user_id=?
        ORDER BY d.id DESC
        """,
        (uid,)
    ).fetchall()

    subs = conn.execute(
        "SELECT * FROM subjects WHERE user_id=? ORDER BY name",
        (uid,)
    ).fetchall()

    conn.close()
    return render_template(
        "documents.html",
        page="documents",
        documents=docs,
        subjects=subs
    )


@app.route("/documents/<int:doc_id>/subject", methods=["POST"])
@login_required
def update_document_subject(doc_id):
    uid = session["user_id"]
    conn = db()

    document = conn.execute(
        "SELECT id, subject_id FROM documents WHERE id=? AND user_id=?",
        (doc_id, uid)
    ).fetchone()

    if document:
        old_subject_id = document["subject_id"]
        new_subject_id = owned_subject_id(
            conn,
            uid,
            request.form.get("subject_id")
        )

        conn.execute(
            "UPDATE documents SET subject_id=? WHERE id=? AND user_id=?",
            (new_subject_id, doc_id, uid)
        )

        # Quiz sinh từ tài liệu phải luôn đi theo môn của tài liệu.
        conn.execute(
            "UPDATE quizzes SET subject_id=? WHERE document_id=? AND user_id=?",
            (new_subject_id, doc_id, uid)
        )

        if old_subject_id:
            recalculate_subject_progress(uid, old_subject_id, conn)
        if new_subject_id:
            recalculate_subject_progress(uid, new_subject_id, conn)

        conn.commit()

    conn.close()
    return redirect(url_for("documents"))

@app.route("/documents/<int:doc_id>/delete", methods=["POST"])
@login_required
def delete_document(doc_id):
    uid = session["user_id"]
    conn = db()

    row = conn.execute(
        "SELECT * FROM documents WHERE id=? AND user_id=?",
        (doc_id, uid)
    ).fetchone()

    if row:
        subject_id = row["subject_id"]

        try:
            (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
        except OSError:
            pass

        quiz_rows = conn.execute(
            """
            SELECT id
            FROM quizzes
            WHERE user_id=?
              AND (
                    document_id=?
                    OR (document_id IS NULL AND title=?)
                  )
            """,
            (uid, doc_id, f"Quiz từ {row['original_name']}")
        ).fetchall()

        for quiz_row in quiz_rows:
            conn.execute(
                "DELETE FROM quiz_attempts WHERE quiz_id=? AND user_id=?",
                (quiz_row["id"], uid)
            )

        conn.execute(
            """
            DELETE FROM quizzes
            WHERE user_id=?
              AND (
                    document_id=?
                    OR (document_id IS NULL AND title=?)
                  )
            """,
            (uid, doc_id, f"Quiz từ {row['original_name']}")
        )

        conn.execute(
            "DELETE FROM documents WHERE id=? AND user_id=?",
            (doc_id, uid)
        )

        if subject_id:
            recalculate_subject_progress(uid, subject_id, conn)

        conn.commit()

    conn.close()
    return redirect(url_for("documents"))

# =====================================================
# STUDY AGENT V2 - API DÙNG CHUNG CHO WEB / MOBILE
# =====================================================
@app.route("/api/learning-profile", methods=["GET", "POST", "PUT"])
@login_required
def api_learning_profile():
    uid = session["user_id"]
    conn = db()
    profile = ensure_learning_profile(conn, uid)

    if request.method == "GET":
        data = dict(profile)
        conn.close()
        return jsonify(data)

    payload = request.get_json(silent=True) or {}
    learning_style = str(
        payload.get("learning_style", profile["learning_style"] or "balanced")
    ).strip()[:40] or "balanced"

    preferred_study_time = str(
        payload.get(
            "preferred_study_time",
            profile["preferred_study_time"] or "19:00"
        )
    ).strip()

    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", preferred_study_time):
        preferred_study_time = profile["preferred_study_time"] or "19:00"

    daily_minutes = _safe_int(
        payload.get("daily_minutes"),
        int(profile["daily_minutes"] or 45),
        15,
        240
    )
    goals = str(payload.get("goals", profile["goals"] or "")).strip()[:1200]
    notes = str(payload.get("notes", profile["notes"] or "")).strip()[:1200]

    conn.execute(
        """
        UPDATE learning_profiles
        SET learning_style=?,
            preferred_study_time=?,
            daily_minutes=?,
            goals=?,
            notes=?,
            updated_at=?
        WHERE user_id=?
        """,
        (
            learning_style,
            preferred_study_time,
            daily_minutes,
            goals,
            notes,
            now(),
            uid
        )
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM learning_profiles WHERE user_id=?",
        (uid,)
    ).fetchone()
    result = dict(updated)
    conn.close()
    return jsonify(result)


@app.route(
    "/api/subjects/<int:subject_id>/shared-knowledge",
    methods=["GET", "POST"]
)
@login_required
def api_subject_shared_knowledge(subject_id):
    uid = session["user_id"]
    conn = db()

    subject = conn.execute(
        "SELECT id,name,code FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not subject:
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404

    shared = ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    if not shared:
        conn.close()
        return jsonify({"error": "Không tạo được kho kiến thức chung."}), 500

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        source_type = str(payload.get("source_type") or "note").strip().lower()[:30]
        title = str(payload.get("title") or "").strip()[:180]
        content = str(payload.get("content") or "").strip()

        if not content:
            conn.close()
            return jsonify({"error": "Nội dung kiến thức đang trống."}), 400

        if source_type == "syllabus":
            conn.execute(
                """
                UPDATE shared_subjects
                SET syllabus_text=?, updated_at=?
                WHERE id=?
                """,
                (content[:50000], now(), shared["id"])
            )
        else:
            if not title:
                title = "Kiến thức chung"
            conn.execute(
                """
                INSERT INTO shared_knowledge(
                    shared_subject_id,title,content,source_type,
                    created_by_user_id,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    shared["id"],
                    title,
                    content[:50000],
                    source_type or "note",
                    uid,
                    now(),
                    now()
                )
            )

        conn.commit()
        shared = conn.execute(
            "SELECT * FROM shared_subjects WHERE id=?",
            (shared["id"],)
        ).fetchone()

    knowledge_rows = conn.execute(
        """
        SELECT id,title,content,source_type,created_at,updated_at
        FROM shared_knowledge
        WHERE shared_subject_id=?
        ORDER BY id DESC
        LIMIT 50
        """,
        (shared["id"],)
    ).fetchall()

    result = {
        "subject": {
            "id": subject["id"],
            "name": subject["name"],
            "code": subject["code"]
        },
        "shared_subject": {
            "id": shared["id"],
            "name": shared["name"],
            "code": shared["code"],
            "syllabus_text": shared["syllabus_text"]
        },
        "knowledge": [dict(row) for row in knowledge_rows]
    }
    conn.close()
    return jsonify(result)


@app.route(
    "/api/subjects/<int:subject_id>/learning-insights",
    methods=["GET"]
)
@login_required
def api_subject_learning_insights(subject_id):
    uid = session["user_id"]
    conn = db()
    subject = conn.execute(
        """
        SELECT id,name,code,target_score,progress
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, uid)
    ).fetchone()

    if not subject:
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404

    profile = ensure_learning_profile(conn, uid)
    weaknesses = conn.execute(
        """
        SELECT id,topic,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
        ORDER BY (miss_count - correct_count * 0.5) DESC, last_seen_at DESC
        LIMIT 12
        """,
        (uid, subject_id)
    ).fetchall()

    quiz_stats = conn.execute(
        """
        SELECT
            COUNT(*) AS attempts,
            ROUND(AVG(qa.score), 1) AS avg_score,
            ROUND(MAX(qa.score), 1) AS best_score
        FROM quiz_attempts qa
        JOIN quizzes q ON q.id=qa.quiz_id
        WHERE qa.user_id=? AND q.user_id=? AND q.subject_id=?
        """,
        (uid, uid, subject_id)
    ).fetchone()
    conn.close()

    return jsonify({
        "subject": dict(subject),
        "profile": {
            "learning_style": profile["learning_style"],
            "preferred_study_time": profile["preferred_study_time"],
            "daily_minutes": profile["daily_minutes"],
            "goals": profile["goals"],
            "notes": profile["notes"]
        },
        "quiz": {
            "attempts": int(quiz_stats["attempts"] or 0),
            "avg_score": float(quiz_stats["avg_score"] or 0),
            "best_score": float(quiz_stats["best_score"] or 0)
        },
        "weaknesses": [dict(row) for row in weaknesses]
    })


@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", page="chat")


@app.route("/api/chats", methods=["GET"])
@login_required
def api_chats():
    uid = session["user_id"]
    conn = db()

    ensure_subject_chats(uid, conn)

    rows = conn.execute(
        """
        SELECT
            c.id,
            c.subject_id,
            s.name AS title,
            c.created_at,
            c.updated_at,
            COUNT(DISTINCT m.id) AS message_count,
            COUNT(DISTINCT d.id) AS document_count
        FROM subjects s
        JOIN chat_conversations c
          ON c.user_id=s.user_id
         AND c.subject_id=s.id
        LEFT JOIN chat_messages m
          ON m.conversation_id=c.id
         AND m.user_id=c.user_id
        LEFT JOIN documents d
          ON d.user_id=s.user_id
         AND d.subject_id=s.id
        WHERE s.user_id=?
        GROUP BY c.id, c.subject_id, s.name, c.created_at, c.updated_at
        ORDER BY s.created_at DESC, s.id DESC
        """,
        (uid,)
    ).fetchall()
    conn.close()

    return jsonify([
        {
            "id": row["id"],
            "subject_id": row["subject_id"],
            "title": row["title"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "message_count": int(row["message_count"] or 0),
            "document_count": int(row["document_count"] or 0)
        }
        for row in rows
    ])


@app.route("/api/chats/<int:conversation_id>/messages", methods=["GET"])
@login_required
def api_chat_messages(conversation_id):
    uid = session["user_id"]
    conn = db()

    conversation = conn.execute(
        """
        SELECT c.id
        FROM chat_conversations c
        JOIN subjects s
          ON s.id=c.subject_id
         AND s.user_id=c.user_id
        WHERE c.id=? AND c.user_id=?
        """,
        (conversation_id, uid)
    ).fetchone()

    if not conversation:
        conn.close()
        return jsonify({"error": "Không tìm thấy Chat của môn học."}), 404

    rows = conn.execute(
        """
        SELECT id, role, content, created_at
        FROM chat_messages
        WHERE user_id=? AND conversation_id=?
        ORDER BY id ASC
        LIMIT 200
        """,
        (uid, conversation_id)
    ).fetchall()
    conn.close()

    return jsonify([
        {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "created_at": row["created_at"]
        }
        for row in rows
    ])


@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    uid = session["user_id"]
    payload = request.get_json(silent=True) or {}
    question = (
        payload.get("question")
        or payload.get("message")
        or ""
    ).strip()

    if not question:
        return jsonify({"error": "Câu hỏi trống"}), 400

    try:
        conversation_id = int(payload.get("conversation_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Hãy chọn một môn học trước khi hỏi AI."}), 400

    conn = db()

    conversation = conn.execute(
        """
        SELECT
            c.id,
            c.subject_id,
            s.name AS subject_name
        FROM chat_conversations c
        JOIN subjects s
          ON s.id=c.subject_id
         AND s.user_id=c.user_id
        WHERE c.id=? AND c.user_id=?
        """,
        (conversation_id, uid)
    ).fetchone()

    if not conversation:
        conn.close()
        return jsonify({"error": "Không tìm thấy Chat của môn học."}), 404

    history_rows = conn.execute(
        """
        SELECT role, content
        FROM chat_messages
        WHERE user_id=? AND conversation_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (uid, conversation_id)
    ).fetchall()

    history_rows = list(reversed(history_rows))
    conversation_history = "\n".join(
        f"{'Bạn' if row['role']=='user' else 'AI'}: {row['content']}"
        for row in history_rows
    )

    subject_id = conversation["subject_id"]
    subject_name = conversation["subject_name"]

    conn.close()

    context, candidate_sources = get_subject_context(
        uid,
        subject_id,
        question
    )
    shared_context, shared_sources = get_shared_subject_context(
        uid,
        subject_id,
        question
    )
    personal_context = get_personal_learning_context(
        uid,
        subject_id
    )

    answer, used_sources, source_mode = gemini_subject_answer(
        subject_name,
        question,
        context,
        candidate_sources,
        conversation_history,
        shared_context,
        personal_context
    )

    conn = db()
    created_at = now()

    conn.execute(
        """
        INSERT INTO chat_messages(
            user_id,conversation_id,role,content,created_at
        ) VALUES(?,?,?,?,?)
        """,
        (uid, conversation_id, "user", question, created_at)
    )
    conn.execute(
        """
        INSERT INTO chat_messages(
            user_id,conversation_id,role,content,created_at
        ) VALUES(?,?,?,?,?)
        """,
        (uid, conversation_id, "assistant", answer, now())
    )

    updated_at = now()
    conn.execute(
        """
        UPDATE chat_conversations
        SET title=?, updated_at=?
        WHERE id=? AND user_id=? AND subject_id=?
        """,
        (
            subject_name,
            updated_at,
            conversation_id,
            uid,
            subject_id
        )
    )
    conn.commit()
    conn.close()

    return jsonify({
        "answer": answer,
        "conversation_id": conversation_id,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "source_mode": source_mode,
        "sources": used_sources,
        "shared_sources": shared_sources,
        "personalized": bool(personal_context),
        "updated_at": updated_at
    })


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    uid = session["user_id"]
    conn = db()

    # =====================================================
    # TẠO QUIZ MỚI
    # =====================================================
    if request.method == "POST":
        doc_id = request.form.get("document_id")

        try:
            question_count = int(
                request.form.get("question_count", 10)
            )
        except (TypeError, ValueError):
            question_count = 10

        if question_count not in (10, 20, 30):
            question_count = 10

        doc = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE id=? AND user_id=?
            """,
            (doc_id, uid)
        ).fetchone()

        if doc:
            questions = build_quiz(
                doc["extracted_text"] or "",
                question_count
            )

            conn.execute(
                """
                INSERT INTO quizzes(
                    user_id,
                    subject_id,
                    document_id,
                    title,
                    payload,
                    created_at
                )
                VALUES(?,?,?,?,?,?)
                """,
                (
                    uid,
                    doc["subject_id"],
                    doc["id"],
                    f"Quiz từ {doc['original_name']}",
                    json.dumps(
                        questions,
                        ensure_ascii=False
                    ),
                    now()
                )
            )

            conn.commit()

        conn.close()

        return redirect(
            url_for("quiz")
        )


    # =====================================================
    # LẤY TÀI LIỆU
    # =====================================================
    docs = conn.execute(
        """
        SELECT *
        FROM documents
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (uid,)
    ).fetchall()


    # =====================================================
    # LẤY QUIZ
    # =====================================================
    quizzes = conn.execute(
        """
        SELECT *
        FROM quizzes
        WHERE user_id=?
        ORDER BY id DESC
        """,
        (uid,)
    ).fetchall()

    conn.close()


    # =====================================================
    # CHUYỂN PAYLOAD JSON THÀNH DANH SÁCH CÂU HỎI
    # =====================================================
    parsed = []

    for q in quizzes:
        item = dict(q)

        try:
            item["questions"] = json.loads(
                q["payload"]
            )
        except (json.JSONDecodeError, TypeError):
            item["questions"] = []

        parsed.append(item)


    return render_template(
        "quiz.html",
        page="quiz",
        documents=docs,
        quizzes=parsed
    )


# =====================================================
# XÓA QUIZ
# =====================================================
@app.route(
    "/quiz/<int:quiz_id>/delete",
    methods=["POST"]
)
@login_required
def delete_quiz(quiz_id):
    uid = session["user_id"]
    conn = db()

    quiz_row = conn.execute(
        "SELECT subject_id FROM quizzes WHERE id=? AND user_id=?",
        (quiz_id, uid)
    ).fetchone()

    conn.execute(
        """
        DELETE FROM quiz_attempts
        WHERE quiz_id=? AND user_id=?
        """,
        (
            quiz_id,
            uid
        )
    )

    conn.execute(
        """
        DELETE FROM quizzes
        WHERE id=? AND user_id=?
        """,
        (
            quiz_id,
            uid
        )
    )

    if quiz_row and quiz_row["subject_id"]:
        recalculate_subject_progress(
            uid,
            quiz_row["subject_id"],
            conn
        )

    conn.commit()
    conn.close()

    return redirect(
        url_for("quiz")
    )


# =====================================================
# LƯU KẾT QUẢ LÀM QUIZ
# =====================================================
@app.route(
    "/api/quiz/submit",
    methods=["POST"]
)
@login_required
def submit_quiz():
    uid = session["user_id"]

    payload = request.get_json(silent=True) or {}
    quiz_id = payload.get("quiz_id")
    answers = payload.get("answers")

    try:
        quiz_id = int(quiz_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "quiz_id không hợp lệ."
        }), 400

    if not isinstance(answers, list):
        return jsonify({
            "error": "Danh sách đáp án không hợp lệ."
        }), 400

    conn = db()

    quiz_row = conn.execute(
        """
        SELECT *
        FROM quizzes
        WHERE id=? AND user_id=?
        """,
        (quiz_id, uid)
    ).fetchone()

    if not quiz_row:
        conn.close()
        return jsonify({
            "error": "Không tìm thấy quiz."
        }), 404

    try:
        questions = json.loads(quiz_row["payload"])
    except (json.JSONDecodeError, TypeError):
        conn.close()
        return jsonify({
            "error": "Dữ liệu quiz bị lỗi."
        }), 500

    if not isinstance(questions, list) or not questions:
        conn.close()
        return jsonify({
            "error": "Quiz không có câu hỏi."
        }), 400

    total_questions = len(questions)
    correct_count = 0
    normalized_answers = []

    for index, question in enumerate(questions):
        selected_answer = (
            answers[index]
            if index < len(answers)
            else None
        )

        if selected_answer is None:
            normalized_answers.append(None)
            continue

        try:
            selected_answer = int(selected_answer)
        except (TypeError, ValueError):
            normalized_answers.append(None)
            continue

        if selected_answer not in (0, 1, 2, 3):
            normalized_answers.append(None)
            continue

        normalized_answers.append(selected_answer)

        try:
            correct_answer = int(question["answer"])
        except (KeyError, TypeError, ValueError):
            continue

        is_correct = selected_answer == correct_answer

        if is_correct:
            correct_count += 1

        record_quiz_learning_signal(
            conn,
            uid,
            quiz_row["subject_id"],
            str(question.get("question") or ""),
            is_correct
        )

    score = round(
        (correct_count / total_questions) * 100,
        2
    )

    cursor = conn.execute(
        """
        INSERT INTO quiz_attempts(
            user_id,
            quiz_id,
            score,
            correct_count,
            total_questions,
            answers_json,
            created_at
        )
        VALUES(?,?,?,?,?,?,?)
        """,
        (
            uid,
            quiz_id,
            score,
            correct_count,
            total_questions,
            json.dumps(normalized_answers, ensure_ascii=False),
            now()
        )
    )

    attempt_id = cursor.lastrowid

    # Nộp quiz xong thì cập nhật tiến độ môn ngay
    recalculate_subject_progress(
        uid,
        quiz_row["subject_id"],
        conn
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "attempt_id": attempt_id,
        "score": score,
        "correct_count": correct_count,
        "total_questions": total_questions
    })


@app.route("/reminders", methods=["GET", "POST"])
@login_required
def reminders():
    # Trang Nhắc việc cũ đã được gộp vào Kế hoạch học.
    # Giữ route này để các link cũ không bị lỗi TemplateNotFound.
    return redirect(url_for("study_plan"))


@app.route("/reminders/<int:reminder_id>/toggle", methods=["POST"])
@login_required
def toggle_reminder(reminder_id):
    conn = db()
    row = conn.execute(
        "SELECT done FROM reminders WHERE id=? AND user_id=?",
        (reminder_id, session["user_id"])
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE reminders SET done=? WHERE id=? AND user_id=?",
            (0 if row["done"] else 1, reminder_id, session["user_id"])
        )
        conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))

@app.route("/study-plan")
@login_required
def study_plan():
    uid = session["user_id"]
    conn = db()

    # Đồng bộ tiến độ sau khi thêm/xóa/đánh dấu buổi học
    recalculate_all_subject_progress(uid, conn)

    subjects = conn.execute(
        "SELECT * FROM subjects WHERE user_id=? ORDER BY progress ASC, name ASC",
        (uid,)
    ).fetchall()

    task_rows = conn.execute(
        """
        SELECT t.*, s.name AS subject_name
        FROM study_tasks t
        LEFT JOIN subjects s ON s.id=t.subject_id
        WHERE t.user_id=?
        ORDER BY t.done ASC, t.study_at ASC, t.id ASC
        """,
        (uid,)
    ).fetchall()

    reminder_rows = conn.execute(
        """
        SELECT * FROM reminders
        WHERE user_id=?
        ORDER BY done ASC,
                 CASE WHEN due_at='' THEN 1 ELSE 0 END,
                 due_at ASC,
                 id DESC
        """,
        (uid,)
    ).fetchall()
    conn.close()

    today = datetime.now().date()
    now_dt = datetime.now()

    tasks = []
    completed_tasks = 0
    overdue_tasks = 0
    for row in task_rows:
        item = dict(row)
        try:
            study_dt = datetime.fromisoformat(row["study_at"])
        except (TypeError, ValueError):
            study_dt = now_dt
        item["weekday"] = _format_weekday(study_dt)
        item["date_text"] = study_dt.strftime("%d/%m")
        item["time_text"] = study_dt.strftime("%H:%M")
        item["study_at_input"] = study_dt.strftime("%Y-%m-%dT%H:%M")
        item["is_today"] = study_dt.date() == today
        item["is_overdue"] = (not row["done"]) and study_dt < now_dt
        completed_tasks += 1 if row["done"] else 0
        overdue_tasks += 1 if item["is_overdue"] else 0
        tasks.append(item)

    reminders = []
    urgent_count = 0
    deadline_week = 0
    reminder_today = 0
    for row in reminder_rows:
        item = dict(row)
        due_dt = None
        try:
            due_dt = datetime.fromisoformat(row["due_at"]) if row["due_at"] else None
        except ValueError:
            due_dt = None

        item["due_at_input"] = due_dt.strftime("%Y-%m-%dT%H:%M") if due_dt else ""
        item["date_text"] = due_dt.strftime("%d/%m/%Y") if due_dt else "Chưa đặt hạn"
        item["time_text"] = due_dt.strftime("%H:%M") if due_dt else ""
        item["days_left"] = None
        item["badge_text"] = "Chưa đặt hạn"
        item["badge_class"] = "neutral"
        item["urgent"] = False

        if due_dt:
            days_left = (due_dt.date() - today).days
            item["days_left"] = days_left
            if row["done"]:
                item["badge_text"] = "Đã xong"
                item["badge_class"] = "done"
            elif due_dt < now_dt:
                item["badge_text"] = "Quá hạn"
                item["badge_class"] = "late"
            elif days_left == 0:
                item["badge_text"] = "Hôm nay"
                item["badge_class"] = "danger"
                item["urgent"] = True
            elif days_left == 1:
                item["badge_text"] = "Còn 1 ngày"
                item["badge_class"] = "danger"
                item["urgent"] = True
            elif days_left == 2:
                item["badge_text"] = "Còn 2 ngày"
                item["badge_class"] = "warning"
                item["urgent"] = True
            else:
                item["badge_text"] = f"Còn {days_left} ngày"
                item["badge_class"] = "info"

            if not row["done"] and 0 <= days_left <= 2:
                urgent_count += 1
            if not row["done"] and 0 <= days_left <= 7:
                deadline_week += 1
            if not row["done"] and days_left == 0:
                reminder_today += 1

        reminders.append(item)

    total_tasks = len(tasks)
    completion = round((completed_tasks / total_tasks) * 100) if total_tasks else 0
    priority_count = sum(1 for s in subjects if int(s["progress"] or 0) < 50)

    if urgent_count:
        agent_tip = (
            f"Bạn có {urgent_count} deadline còn không quá 2 ngày. "
            "Nên hoàn thành các buổi học liên quan trước và giảm bớt việc không cấp thiết."
        )
    elif overdue_tasks:
        agent_tip = (
            f"Có {overdue_tasks} buổi học đã qua thời gian nhưng chưa hoàn thành. "
            "Bạn có thể chỉnh lại lịch để kế hoạch sát thực tế hơn."
        )
    elif tasks:
        agent_tip = (
            "Kế hoạch đang ổn. Sau mỗi buổi học, hãy đánh dấu hoàn thành và dùng Quiz "
            "để kiểm tra lại phần vừa ôn."
        )
    else:
        agent_tip = (
            "Chưa có lịch học. Hãy chọn môn, mục tiêu và deadline để AI tạo kế hoạch đầu tiên."
        )

    return render_template(
        "study_plan.html",
        page="study_plan",
        subjects=subjects,
        tasks=tasks,
        reminders=reminders,
        priority_count=priority_count,
        deadline_week=deadline_week,
        reminder_today=reminder_today,
        completion=completion,
        agent_tip=agent_tip,
        urgent_count=urgent_count,
        today_input=today.isoformat(),
    )


@app.route("/study-plan/generate", methods=["POST"])
@login_required
def generate_study_plan_route():
    uid = session["user_id"]
    subject_id = request.form.get("subject_id", type=int)
    goal = request.form.get("goal", "").strip()
    deadline_raw = request.form.get("deadline", "").strip()
    preferred_time = request.form.get("preferred_time", "19:00").strip() or "19:00"
    daily_minutes = _safe_int(request.form.get("daily_minutes"), 45, 20, 180)

    if not subject_id or not goal or not deadline_raw:
        return redirect(url_for("study_plan"))

    try:
        deadline_dt = datetime.fromisoformat(deadline_raw)
    except ValueError:
        return redirect(url_for("study_plan"))

    if deadline_dt < datetime.now():
        return redirect(url_for("study_plan"))

    conn = db()
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not subject:
        conn.close()
        return redirect(url_for("study_plan"))

    docs = conn.execute(
        """
        SELECT original_name, extracted_text
        FROM documents
        WHERE user_id=? AND subject_id=?
        ORDER BY id DESC
        LIMIT 4
        """,
        (uid, subject_id)
    ).fetchall()
    context_parts = []
    for doc in docs:
        if doc["extracted_text"]:
            context_parts.append(
                f"TÀI LIỆU: {doc['original_name']}\n{doc['extracted_text'][:1200]}"
            )
    context = "\n\n".join(context_parts)

    generated = build_study_plan(
        subject["name"],
        goal,
        deadline_dt,
        daily_minutes,
        preferred_time,
        context,
    )

    # Tránh nhân đôi khi người dùng bấm tạo lại kế hoạch cho cùng môn.
    conn.execute(
        "DELETE FROM study_tasks WHERE user_id=? AND subject_id=? AND source='ai' AND done=0",
        (uid, subject_id)
    )

    for task in generated:
        study_at = f"{task['date']}T{task['time']}"
        conn.execute(
            """
            INSERT INTO study_tasks(
                user_id, subject_id, title, study_at,
                duration, note, done, source, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                subject_id,
                task["title"],
                study_at,
                task["duration"],
                task["note"],
                0,
                "ai",
                now(),
            )
        )

    existing_reminder = conn.execute(
        "SELECT id FROM reminders WHERE user_id=? AND title=? AND due_at=? LIMIT 1",
        (uid, goal, deadline_dt.isoformat(timespec="minutes"))
    ).fetchone()
    if not existing_reminder:
        conn.execute(
            "INSERT INTO reminders(user_id,title,due_at,created_at) VALUES(?,?,?,?)",
            (uid, goal, deadline_dt.isoformat(timespec="minutes"), now())
        )

    conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/tasks/create", methods=["POST"])
@login_required
def create_study_task():
    uid = session["user_id"]
    title = request.form.get("title", "").strip() or "Buổi học"
    study_at = request.form.get("study_at", "").strip()
    duration = _safe_int(request.form.get("duration"), 45, 15, 240)
    note = request.form.get("note", "").strip()

    if not study_at:
        return redirect(url_for("study_plan"))

    conn = db()
    subject_id = owned_subject_id(
        conn,
        uid,
        request.form.get("subject_id")
    )
    conn.execute(
        """
        INSERT INTO study_tasks(
            user_id,subject_id,title,study_at,duration,note,done,source,created_at
        ) VALUES(?,?,?,?,?,?,?,?,?)
        """,
        (uid, subject_id, title, study_at, duration, note, 0, "manual", now())
    )
    conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/tasks/<int:task_id>/update", methods=["POST"])
@login_required
def update_study_task(task_id):
    uid = session["user_id"]
    title = request.form.get("title", "").strip() or "Buổi học"
    study_at = request.form.get("study_at", "").strip()
    duration = _safe_int(request.form.get("duration"), 45, 15, 240)
    note = request.form.get("note", "").strip()

    if study_at:
        conn = db()
        old_task = conn.execute(
            "SELECT subject_id FROM study_tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        ).fetchone()
        subject_id = owned_subject_id(
            conn,
            uid,
            request.form.get("subject_id")
        )
        conn.execute(
            """
            UPDATE study_tasks
            SET subject_id=?, title=?, study_at=?, duration=?, note=?
            WHERE id=? AND user_id=?
            """,
            (subject_id, title, study_at, duration, note, task_id, uid)
        )
        if old_task and old_task["subject_id"]:
            recalculate_subject_progress(uid, old_task["subject_id"], conn)
        if subject_id:
            recalculate_subject_progress(uid, subject_id, conn)
        conn.commit()
        conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_study_task(task_id):
    uid = session["user_id"]
    conn = db()
    row = conn.execute(
        "SELECT done, subject_id FROM study_tasks WHERE id=? AND user_id=?",
        (task_id, uid)
    ).fetchone()
    if row:
        new_done = 0 if row["done"] else 1
        completed_at = now() if new_done else ""

        conn.execute(
            """
            UPDATE study_tasks
            SET done=?, completed_at=?
            WHERE id=? AND user_id=?
            """,
            (
                new_done,
                completed_at,
                task_id,
                uid
            )
        )
        if row["subject_id"]:
            recalculate_subject_progress(uid, row["subject_id"], conn)
        conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_study_task(task_id):
    uid = session["user_id"]
    conn = db()
    row = conn.execute(
        "SELECT subject_id FROM study_tasks WHERE id=? AND user_id=?",
        (task_id, uid)
    ).fetchone()
    conn.execute(
        "DELETE FROM study_tasks WHERE id=? AND user_id=?",
        (task_id, uid)
    )
    if row and row["subject_id"]:
        recalculate_subject_progress(uid, row["subject_id"], conn)
    conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/reminders/<int:reminder_id>/update", methods=["POST"])
@login_required
def update_plan_reminder(reminder_id):
    uid = session["user_id"]
    title = request.form.get("title", "").strip() or "Nhắc việc"
    due_at = request.form.get("due_at", "").strip()
    conn = db()
    conn.execute(
        "UPDATE reminders SET title=?, due_at=? WHERE id=? AND user_id=?",
        (title, due_at, reminder_id, uid)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/reminders/<int:reminder_id>/toggle", methods=["POST"])
@login_required
def toggle_plan_reminder(reminder_id):
    uid = session["user_id"]
    conn = db()
    row = conn.execute(
        "SELECT done FROM reminders WHERE id=? AND user_id=?",
        (reminder_id, uid)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE reminders SET done=? WHERE id=? AND user_id=?",
            (0 if row["done"] else 1, reminder_id, uid)
        )
        conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))


@app.route("/study-plan/reminders/<int:reminder_id>/delete", methods=["POST"])
@login_required
def delete_plan_reminder(reminder_id):
    conn = db()
    conn.execute(
        "DELETE FROM reminders WHERE id=? AND user_id=?",
        (reminder_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    return redirect(url_for("study_plan"))

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    uid = session["user_id"]
    conn = db()
    row = conn.execute(
        "SELECT id FROM documents WHERE user_id=? AND stored_name=?",
        (uid, filename)
    ).fetchone()
    conn.close()

    if not row:
        return "Không tìm thấy tài liệu.", 404

    return send_from_directory(UPLOAD_DIR, filename)

if __name__ == "__main__":
    init_db()
    app.run(
        debug=os.getenv("FLASK_DEBUG", "1") == "1",
        host="127.0.0.1",
        port=5000
    )