import os
import secrets
import sys
import sqlite3
import json
import re
import time
import random
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory
from study_schedule_conflicts import find_study_conflicts
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

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

from syllabus_routes import syllabus_bp
app.register_blueprint(syllabus_bp)
from course_path_routes import course_path_bp
app.register_blueprint(course_path_bp)
from chapter_material_routes import chapter_material_bp
app.register_blueprint(chapter_material_bp)
from study_session_routes import study_session_bp
app.register_blueprint(study_session_bp)
from study_session_quiz_routes import session_quiz_bp
app.register_blueprint(session_quiz_bp)
# Khi thiếu SECRET_KEY, dùng khóa ngẫu nhiên chỉ cho phiên chạy hiện tại.
# Khi triển khai cần đặt SECRET_KEY bí mật, ổn định trong biến môi trường.
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
# Giới hạn kích thước TOÀN BỘ HTTP request, gồm file và multipart headers.
# File PDF lớn cần được chấp nhận nhưng vẫn phải có ngưỡng để tránh DOS.
try:
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
except (TypeError, ValueError):
    MAX_UPLOAD_MB = 50
MAX_UPLOAD_MB = max(5, min(MAX_UPLOAD_MB, 100))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Bật chỉ khi chạy HTTPS thật; khi demo LAN HTTP giữ =0.
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"

ALLOWED_EXTENSIONS = {"pdf", "txt", "md"}


@app.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(error):
    """Thay trang lỗi Werkzeug bằng phản hồi thân thiện cho Web và Mobile."""
    message = (
        f"Tệp vượt giới hạn tải lên {MAX_UPLOAD_MB} MB. "
        "Hãy chọn tệp nhỏ hơn hoặc nén/chia nhỏ PDF."
    )
    if request.path.startswith("/api/"):
        return jsonify({"error": message, "max_upload_mb": MAX_UPLOAD_MB}), 413
    if request.path == "/documents":
        # Redirect GET tránh trình duyệt ở lại trang lỗi POST và giúp giữ giao diện.
        return redirect(url_for("documents", upload_error="too_large"), code=303)
    return message, 413

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
        role TEXT NOT NULL DEFAULT 'student',
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
        personal_syllabus_document_id INTEGER DEFAULT NULL,
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
        subject_id INTEGER,
        title TEXT NOT NULL,
        due_at TEXT DEFAULT '',
        done INTEGER DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'manual',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id),
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
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
        admin_managed INTEGER NOT NULL DEFAULT 1,
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

    CREATE TABLE IF NOT EXISTS shared_documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shared_subject_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL UNIQUE,
        extracted_text TEXT NOT NULL DEFAULT '',
        knowledge_id INTEGER,
        is_syllabus INTEGER NOT NULL DEFAULT 0,
        created_by_user_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(shared_subject_id) REFERENCES shared_subjects(id) ON DELETE CASCADE,
        FOREIGN KEY(knowledge_id) REFERENCES shared_knowledge(id) ON DELETE SET NULL,
        FOREIGN KEY(created_by_user_id) REFERENCES users(id)
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
        chapter TEXT DEFAULT '',
        miss_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        last_seen_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
        UNIQUE(user_id, subject_id, topic_key)
    );
    """)

    conn.commit()

    # Migrate old databases: all existing accounts are students by default.
    user_columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in user_columns:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'student'")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_shared_documents_subject ON shared_documents(shared_subject_id,id)")
    shared_columns = {row["name"] for row in conn.execute("PRAGMA table_info(shared_subjects)")}
    if "admin_managed" not in shared_columns:
        # Preserve old catalog entries on existing databases; only future
        # student-generated placeholders are hidden from the Admin catalog.
        conn.execute("ALTER TABLE shared_subjects ADD COLUMN admin_managed INTEGER NOT NULL DEFAULT 1")
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

    if "personal_syllabus_document_id" not in subject_columns:
        conn.execute(
            "ALTER TABLE subjects ADD COLUMN personal_syllabus_document_id INTEGER"
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

    reminder_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(reminders)"
        ).fetchall()
    }
    if "subject_id" not in reminder_columns:
        conn.execute(
            "ALTER TABLE reminders ADD COLUMN subject_id INTEGER"
        )
    if "source" not in reminder_columns:
        # Never treat old manual deadlines as automatically generated.
        conn.execute(
            "ALTER TABLE reminders ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reminders_user_subject_due "
        "ON reminders(user_id, subject_id, due_at)"
    )

    weakness_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(learning_weaknesses)"
        ).fetchall()
    }

    if "chapter" not in weakness_columns:
        conn.execute(
            "ALTER TABLE learning_weaknesses ADD COLUMN chapter TEXT DEFAULT ''"
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
    if not demo and os.getenv("DEMO_ACCOUNT_ENABLED", "0") == "1":
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
        demo_base = datetime.now().replace(
            second=0,
            microsecond=0
        )
        reminders = [
            (
                "Ôn tập chương 3 - Trí tuệ nhân tạo",
                (demo_base + timedelta(days=1)).replace(
                    hour=9,
                    minute=0
                ).isoformat(timespec="minutes")
            ),
            (
                "Làm quiz chương 2",
                (demo_base + timedelta(days=1)).replace(
                    hour=14,
                    minute=0
                ).isoformat(timespec="minutes")
            ),
            (
                "Nộp bài tập lớn - Lập trình Web",
                (demo_base + timedelta(days=2)).replace(
                    hour=23,
                    minute=59
                ).isoformat(timespec="minutes")
            ),
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

    subject_key = _normalize_subject_key(subject["code"], subject["name"])
    if subject["shared_subject_id"]:
        shared = conn.execute(
            "SELECT * FROM shared_subjects WHERE id=?",
            (subject["shared_subject_id"],)
        ).fetchone()
        # If the student edits the course code, relink to the correct shared
        # library instead of leaking materials from the old course.
        if shared and shared["subject_key"] == subject_key:
            return shared

    shared = conn.execute(
        "SELECT * FROM shared_subjects WHERE subject_key=?",
        (subject_key,)
    ).fetchone()

    if not shared:
        created_at = now()
        cur = conn.execute(
            """
            INSERT INTO shared_subjects(
                subject_key,code,name,description,syllabus_text,admin_managed,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                subject_key,
                subject["code"] or "",
                subject["name"],
                subject["description"] or "",
                "",
                0,
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
    """
    Ngữ cảnh học thuật của môn cho Chat/Quiz:
    ưu tiên Shared Syllabus; nếu chưa có thì dùng Personal Syllabus fallback;
    sau đó mới bổ sung Shared Knowledge.
    """
    conn = db()

    subject = conn.execute(
        """
        SELECT id,personal_syllabus_document_id
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, user_id)
    ).fetchone()
    if not subject:
        conn.close()
        return "", []

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

    shared_syllabus = (shared["syllabus_text"] or "").strip()
    personal_syllabus = ""
    personal_syllabus_name = ""

    if not shared_syllabus and subject["personal_syllabus_document_id"]:
        personal_doc = conn.execute(
            """
            SELECT original_name,extracted_text
            FROM documents
            WHERE id=? AND user_id=? AND subject_id=?
            """,
            (
                subject["personal_syllabus_document_id"],
                user_id,
                subject_id
            )
        ).fetchone()
        if personal_doc:
            personal_syllabus = (
                personal_doc["extracted_text"] or ""
            ).strip()
            personal_syllabus_name = personal_doc["original_name"] or ""

    syllabus_text = shared_syllabus or personal_syllabus
    if syllabus_text:
        clipped = syllabus_text[:max_chars]
        if shared_syllabus:
            parts.append(f"ĐỀ CƯƠNG CHUẨN CỦA MÔN:\n{clipped}")
            source_labels.append("Đề cương chuẩn của môn")
        else:
            parts.append(
                "ĐỀ CƯƠNG CÁ NHÂN FALLBACK "
                f"({personal_syllabus_name or 'tài liệu cá nhân'}):\n{clipped}"
            )
            source_labels.append(
                personal_syllabus_name or "Đề cương cá nhân"
            )
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
        SELECT topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
          AND miss_count > correct_count
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
            (
                f"{row['chapter']} - {row['topic']} "
                f"(sai {row['miss_count']}, đúng {row['correct_count']})"
                if (row["chapter"] or "").strip()
                else f"{row['topic']} (sai {row['miss_count']}, đúng {row['correct_count']})"
            )
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


def get_next_best_action(conn, user_id, subject_id=None):
    """
    Companion Agent / Next Best Action.
    Dùng dữ liệu học hiện tại để chủ động đề xuất đúng 1 việc nên làm tiếp theo.
    Không gọi Gemini mỗi lần mở trang để Dashboard phản hồi nhanh và ổn định.
    """
    now_dt = datetime.now()
    now_iso = now_dt.isoformat(timespec="minutes")

    subject = None
    if subject_id:
        subject = conn.execute(
            """
            SELECT id,name,code,target_score,progress
            FROM subjects
            WHERE id=? AND user_id=?
            """,
            (subject_id, user_id)
        ).fetchone()
        if not subject:
            return None

    weakness_params = [user_id]
    weakness_subject_filter = ""
    if subject_id:
        weakness_subject_filter = " AND lw.subject_id=?"
        weakness_params.append(subject_id)

    weakness = conn.execute(
        f"""
        SELECT
            lw.topic,lw.chapter,lw.miss_count,lw.correct_count,lw.last_seen_at,
            s.id AS subject_id,s.name AS subject_name,s.progress
        FROM learning_weaknesses lw
        JOIN subjects s
          ON s.id=lw.subject_id AND s.user_id=lw.user_id
        WHERE lw.user_id=?
          AND lw.miss_count > lw.correct_count
          {weakness_subject_filter}
        ORDER BY
            (lw.miss_count - lw.correct_count * 0.5) DESC,
            lw.last_seen_at DESC
        LIMIT 1
        """,
        tuple(weakness_params)
    ).fetchone()

    task_params = [user_id]
    task_subject_filter = ""
    if subject_id:
        task_subject_filter = " AND t.subject_id=?"
        task_params.append(subject_id)

    open_tasks = conn.execute(
        f"""
        SELECT
            t.id,t.subject_id,t.title,t.study_at,t.duration,t.note,t.source,
            s.name AS subject_name
        FROM study_tasks t
        LEFT JOIN subjects s
          ON s.id=t.subject_id AND s.user_id=t.user_id
        WHERE t.user_id=? AND t.done=0
          {task_subject_filter}
        ORDER BY t.study_at ASC,t.id ASC
        LIMIT 30
        """,
        tuple(task_params)
    ).fetchall()

    overdue_task = None
    today_task = None
    upcoming_task = None

    for row in open_tasks:
        try:
            task_dt = datetime.fromisoformat(row["study_at"])
        except (TypeError, ValueError):
            continue

        if task_dt < now_dt and overdue_task is None:
            overdue_task = row
        elif task_dt.date() == now_dt.date() and today_task is None:
            today_task = row
        elif task_dt >= now_dt and upcoming_task is None:
            upcoming_task = row

    # Deadline toàn cục chỉ dùng ở Dashboard; mỗi AI Plan reminder đã gắn subject_id.
    urgent_reminder = None
    if not subject_id:
        reminder_rows = conn.execute(
            """
            SELECT id,title,due_at
            FROM reminders
            WHERE user_id=? AND done=0 AND due_at IS NOT NULL AND due_at<>''
            ORDER BY due_at ASC,id ASC
            LIMIT 12
            """,
            (user_id,)
        ).fetchall()

        for row in reminder_rows:
            try:
                due_dt = datetime.fromisoformat(row["due_at"])
            except (TypeError, ValueError):
                continue

            if due_dt < now_dt or (due_dt - now_dt) <= timedelta(days=2):
                urgent_reminder = row
                break

    quiz_params = [user_id, user_id]
    quiz_subject_filter = ""
    if subject_id:
        quiz_subject_filter = " AND q.subject_id=?"
        quiz_params.append(subject_id)

    recent_quiz = conn.execute(
        f"""
        SELECT
            qa.score,qa.correct_count,qa.total_questions,qa.created_at,
            q.subject_id,s.name AS subject_name
        FROM quiz_attempts qa
        JOIN quizzes q
          ON q.id=qa.quiz_id AND q.user_id=qa.user_id
        LEFT JOIN subjects s
          ON s.id=q.subject_id AND s.user_id=q.user_id
        WHERE qa.user_id=? AND q.user_id=?
          {quiz_subject_filter}
        ORDER BY qa.id DESC
        LIMIT 1
        """,
        tuple(quiz_params)
    ).fetchone()

    def task_action(row, eyebrow, reason_prefix):
        try:
            task_dt = datetime.fromisoformat(row["study_at"])
            time_text = task_dt.strftime("%d/%m lúc %H:%M")
        except (TypeError, ValueError):
            time_text = "trong kế hoạch hiện tại"

        subject_name = row["subject_name"] or "Kế hoạch học"
        subject_value = row["subject_id"]
        return {
            "kind": "task",
            "eyebrow": eyebrow,
            "title": row["title"],
            "reason": (
                f"{reason_prefix} {subject_name}. "
                f"Buổi này dự kiến {row['duration'] or 45} phút, {time_text}."
            ),
            "subject_id": subject_value,
            "subject_name": subject_name,
            "meta": [
                f"{row['duration'] or 45} phút",
                "Adaptive" if row["source"] == "adaptive" else "Theo kế hoạch"
            ],
            "primary_label": "Xem kế hoạch",
            "primary_url": url_for("study_plan", subject_id=subject_value)
                if subject_value else url_for("study_plan"),
            "secondary_label": "Hỏi Study Agent",
            "secondary_url": (
                url_for("chat") + f"?subject_id={subject_value}"
                if subject_value else url_for("chat")
            )
        }

    # 1) Deadline rất gần/quá hạn cần xử lý trước ở Dashboard.
    if urgent_reminder:
        try:
            due_dt = datetime.fromisoformat(urgent_reminder["due_at"])
            if due_dt < now_dt:
                due_text = "đã quá hạn"
            else:
                hours_left = max(
                    0,
                    round((due_dt - now_dt).total_seconds() / 3600)
                )
                due_text = (
                    f"còn khoảng {hours_left} giờ"
                    if hours_left < 48
                    else "còn khoảng 2 ngày"
                )
        except (TypeError, ValueError):
            due_text = "sắp đến hạn"

        return {
            "kind": "deadline",
            "eyebrow": "Ưu tiên deadline",
            "title": urgent_reminder["title"],
            "reason": (
                f"Deadline này {due_text}. Study Agent ưu tiên bạn kiểm tra "
                "lại các buổi học liên quan trước khi tiếp tục nội dung mới."
            ),
            "subject_id": None,
            "subject_name": "Toàn bộ kế hoạch",
            "meta": ["Deadline gần", "Ưu tiên cao"],
            "primary_label": "Mở kế hoạch học",
            "primary_url": url_for("study_plan"),
            "secondary_label": "Hỏi Study Agent",
            "secondary_url": url_for("chat")
        }

    # 2) Điểm yếu từ Quiz là tín hiệu học tập mạnh nhất.
    if weakness:
        chapter = (weakness["chapter"] or "").strip()
        topic = weakness["topic"]
        weak_label = f"{chapter} · {topic}" if chapter else topic
        gap = int(weakness["miss_count"] or 0) - int(
            weakness["correct_count"] or 0
        )
        return {
            "kind": "weakness",
            "eyebrow": "Đề xuất từ kết quả Quiz",
            "title": f"Ôn lại {weak_label}",
            "reason": (
                f"Bạn vẫn còn yếu ở chủ đề này trong {weakness['subject_name']}. "
                f"Hiện số lần sai đang nhiều hơn số lần đúng {max(1, gap)} lần, "
                "nên Agent ưu tiên củng cố trước khi học tiếp."
            ),
            "subject_id": weakness["subject_id"],
            "subject_name": weakness["subject_name"],
            "meta": [
                f"Tiến độ {int(weakness['progress'] or 0)}%",
                f"Sai {weakness['miss_count']} · Đúng {weakness['correct_count']}"
            ],
            "primary_label": "Ôn điểm yếu",
            "primary_url": url_for(
                "quiz",
                mode="weakness",
                subject_id=weakness["subject_id"]
            ),
            "secondary_label": "Xem môn học",
            "secondary_url": url_for(
                "subject_detail",
                subject_id=weakness["subject_id"]
            )
        }

    # 3) Có buổi học bị trễ.
    if overdue_task:
        return task_action(
            overdue_task,
            "Buổi học cần xử lý",
            "Buổi học này đã qua thời gian dự kiến của"
        )

    # 4) Có task hôm nay.
    if today_task:
        return task_action(
            today_task,
            "Việc nên làm hôm nay",
            "Đây là nhiệm vụ gần nhất hôm nay của"
        )

    # 5) Subject detail: nếu chưa có task thì chủ động yêu cầu tạo roadmap.
    if subject_id and not open_tasks:
        quiz_text = ""
        if recent_quiz:
            quiz_text = f" Quiz gần nhất đạt {round(float(recent_quiz['score'] or 0))}%."

        return {
            "kind": "plan",
            "eyebrow": "Bước tiếp theo",
            "title": "Tạo lộ trình học theo đề cương",
            "reason": (
                f"{subject['name']} hiện chưa có buổi học sắp tới.{quiz_text} "
                "Agent đề xuất tạo roadmap để xác định rõ nội dung và nhịp học tiếp theo."
            ),
            "subject_id": subject_id,
            "subject_name": subject["name"],
            "meta": [
                f"Tiến độ {int(subject['progress'] or 0)}%",
                (
                    f"Mục tiêu {subject['target_score']:g}"
                    if subject["target_score"] else "Chưa đặt mục tiêu điểm"
                )
            ],
            "primary_label": "Tạo kế hoạch",
            "primary_url": url_for("study_plan", subject_id=subject_id),
            "secondary_label": "Hỏi Study Agent",
            "secondary_url": url_for("chat") + f"?subject_id={subject_id}"
        }

    # 6) Task kế tiếp trong tương lai.
    if upcoming_task:
        return task_action(
            upcoming_task,
            "Tiếp theo trong lộ trình",
            "Đây là buổi học tiếp theo của"
        )

    # 7) Dashboard chưa có task/weakness: chọn môn tiến độ thấp nhất.
    if not subject_id:
        low_subject = conn.execute(
            """
            SELECT id,name,target_score,progress
            FROM subjects
            WHERE user_id=?
            ORDER BY progress ASC,id DESC
            LIMIT 1
            """,
            (user_id,)
        ).fetchone()

        if low_subject:
            return {
                "kind": "plan",
                "eyebrow": "Agent đề xuất bước tiếp theo",
                "title": f"Lập kế hoạch cho {low_subject['name']}",
                "reason": (
                    f"Môn này đang có tiến độ {int(low_subject['progress'] or 0)}% "
                    "và hiện chưa có việc ưu tiên hơn. Tạo lộ trình sẽ giúp Agent "
                    "theo sát việc học thay vì chờ bạn tự chọn nội dung."
                ),
                "subject_id": low_subject["id"],
                "subject_name": low_subject["name"],
                "meta": [
                    f"Tiến độ {int(low_subject['progress'] or 0)}%",
                    "Chưa có task ưu tiên"
                ],
                "primary_label": "Tạo kế hoạch",
                "primary_url": url_for(
                    "study_plan",
                    subject_id=low_subject["id"]
                ),
                "secondary_label": "Xem môn học",
                "secondary_url": url_for(
                    "subject_detail",
                    subject_id=low_subject["id"]
                )
            }

        return {
            "kind": "setup",
            "eyebrow": "Bắt đầu với Study Agent",
            "title": "Thêm môn học đầu tiên",
            "reason": (
                "Khi có môn học, Agent mới có thể theo dõi đề cương, Quiz, "
                "điểm yếu, tiến độ và chủ động đề xuất bước học tiếp theo."
            ),
            "subject_id": None,
            "subject_name": "Study Agent",
            "meta": ["Chưa có môn học"],
            "primary_label": "Thêm môn học",
            "primary_url": url_for("subjects"),
            "secondary_label": "Tài liệu của tôi",
            "secondary_url": url_for("documents")
        }

    # 8) Subject detail đã ổn: khuyến nghị kiểm tra lại bằng Quiz.
    score_text = (
        f"Quiz gần nhất đạt {round(float(recent_quiz['score'] or 0))}%."
        if recent_quiz else
        "Chưa có kết quả Quiz gần đây."
    )
    return {
        "kind": "check",
        "eyebrow": "Đang đúng tiến độ",
        "title": "Kiểm tra lại mức độ nắm bài",
        "reason": (
            f"{score_text} Hiện không có điểm yếu hoặc buổi học tồn đọng, "
            "nên Agent đề xuất một Quiz ngắn trước khi chuyển sang nội dung tiếp theo."
        ),
        "subject_id": subject_id,
        "subject_name": subject["name"],
        "meta": [
            f"Tiến độ {int(subject['progress'] or 0)}%",
            "Không có weakness đang mở"
        ],
        "primary_label": "Tạo Quiz môn học",
        "primary_url": url_for(
            "quiz",
            mode="subject",
            subject_id=subject_id
        ),
        "secondary_label": "Hỏi Study Agent",
        "secondary_url": url_for("chat") + f"?subject_id={subject_id}"
    }


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
    topic,
    chapter,
    is_correct,
    question_text=""
):
    """Ghi nhận tín hiệu học theo chủ đề/chương thay vì lưu nguyên câu hỏi."""
    if not subject_id:
        return

    topic = re.sub(
        r"\s+",
        " ",
        (topic or question_text or "").strip()
    )[:220]
    chapter = re.sub(
        r"\s+",
        " ",
        (chapter or "").strip()
    )[:120]

    if not topic:
        return

    topic_key = _quiz_topic_key(
        f"{chapter} {topic}" if chapter else topic
    )
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
                chapter=?,
                last_seen_at=?
            WHERE id=?
            """,
            (
                int(row["miss_count"] or 0) + (0 if is_correct else 1),
                int(row["correct_count"] or 0) + (1 if is_correct else 0),
                topic,
                chapter,
                now(),
                row["id"]
            )
        )
    elif not is_correct:
        # Chỉ tạo weakness mới khi sinh viên thực sự trả lời sai.
        # Câu đúng ngay lần đầu không nên xuất hiện trong "Phần cần ôn thêm".
        conn.execute(
            """
            INSERT INTO learning_weaknesses(
                user_id,subject_id,topic_key,topic,chapter,
                miss_count,correct_count,last_seen_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                subject_id,
                topic_key,
                topic,
                chapter,
                0 if is_correct else 1,
                1 if is_correct else 0,
                now()
            )
        )



def rebuild_subject_learning_signals(conn, user_id, subject_id):
    """Tính lại điểm yếu từ các lượt Quiz còn tồn tại sau khi xóa/đổi môn.

    Không dùng dữ liệu quiz đã xóa để duy trì điểm yếu hoặc task Adaptive.
    Những nhiệm vụ Adaptive đã hoàn thành được giữ làm lịch sử học tập.
    """
    if not subject_id or not owned_subject_id(conn, user_id, subject_id):
        return

    attempts = conn.execute(
        """
        SELECT q.payload, qa.answers_json
        FROM quiz_attempts qa
        JOIN quizzes q ON q.id=qa.quiz_id AND q.user_id=qa.user_id
        WHERE qa.user_id=? AND q.subject_id=?
        ORDER BY qa.created_at ASC, qa.id ASC
        """,
        (user_id, subject_id)
    ).fetchall()

    conn.execute(
        "DELETE FROM learning_weaknesses WHERE user_id=? AND subject_id=?",
        (user_id, subject_id)
    )

    for attempt in attempts:
        try:
            questions = json.loads(attempt["payload"] or "[]")
            answers = json.loads(attempt["answers_json"] or "[]")
        except (ValueError, TypeError):
            continue
        if not isinstance(questions, list) or not isinstance(answers, list):
            continue
        for question, chosen in zip(questions, answers):
            if not isinstance(question, dict) or isinstance(chosen, bool):
                continue
            try:
                chosen = int(chosen)
                expected = int(question["answer"])
            except (TypeError, ValueError, KeyError):
                continue
            if chosen not in (0, 1, 2, 3) or expected not in (0, 1, 2, 3):
                continue
            record_quiz_learning_signal(
                conn, user_id, subject_id,
                str(question.get("topic") or ""),
                str(question.get("chapter") or ""),
                chosen == expected,
                str(question.get("question") or "")
            )

    sync_adaptive_review_task(conn, user_id, subject_id)
    recalculate_subject_progress(user_id, subject_id, conn)


def get_active_weakness_rows(conn, user_id, subject_id, limit=12):
    """Các chủ đề vẫn còn yếu: số lần sai đang lớn hơn số lần làm đúng."""
    if not subject_id:
        return []

    return conn.execute(
        """
        SELECT id,topic_key,topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
          AND miss_count > correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC,
                 last_seen_at DESC
        LIMIT ?
        """,
        (user_id, subject_id, limit)
    ).fetchall()


def sync_adaptive_review_task(conn, user_id, subject_id):
    """
    Đồng bộ một nhiệm vụ ôn thích nghi từ kết quả Quiz.
    - Còn weakness: tạo/cập nhật 1 task source='adaptive'.
    - Đã xử lý hết weakness: xóa task adaptive chưa hoàn thành.
    """
    if not subject_id:
        return None

    subject = conn.execute(
        "SELECT id,name FROM subjects WHERE id=? AND user_id=?",
        (subject_id, user_id)
    ).fetchone()
    if not subject:
        return None

    weaknesses = get_active_weakness_rows(
        conn,
        user_id,
        subject_id,
        limit=5
    )

    if not weaknesses:
        conn.execute(
            """
            DELETE FROM study_tasks
            WHERE user_id=? AND subject_id=?
              AND source='adaptive' AND done=0
            """,
            (user_id, subject_id)
        )
        return None

    profile = ensure_learning_profile(conn, user_id)
    preferred_time = str(
        profile["preferred_study_time"] or "19:00"
    ).strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", preferred_time):
        preferred_time = "19:00"

    duration = _safe_int(
        profile["daily_minutes"],
        45,
        15,
        120
    )

    from adaptive_review_schedule import (
        ensure_review_schedule_schema, has_manual_time, next_review_slot
    )
    ensure_review_schedule_schema(conn)

    top = weaknesses[0]
    top_label = (
        f"{top['chapter']} · {top['topic']}"
        if (top["chapter"] or "").strip()
        else top["topic"]
    )
    title = f"Ôn điểm yếu: {top['topic']}"[:160]

    weak_labels = []
    for row in weaknesses[:3]:
        label = (
            f"{row['chapter']} - {row['topic']}"
            if (row["chapter"] or "").strip()
            else row["topic"]
        )
        weak_labels.append(label)

    note = (
        "Study Agent tự điều chỉnh sau Quiz. "
        f"Ưu tiên: {'; '.join(weak_labels)}. "
        "Ôn lại nội dung liên quan rồi làm Quiz Ôn điểm yếu để kiểm tra mức độ cải thiện."
    )[:500]

    existing_rows = conn.execute(
        """
        SELECT id,study_at,duration FROM study_tasks
        WHERE user_id=? AND subject_id=?
          AND source='adaptive' AND done=0
        ORDER BY id DESC
        """,
        (user_id, subject_id)
    ).fetchall()

    if existing_rows:
        keep_id = existing_rows[0]["id"]
        if has_manual_time(conn, keep_id, user_id):
            # Preserve user-chosen time/duration on every later Quiz.
            study_at = existing_rows[0]["study_at"]
            duration = existing_rows[0]["duration"]
        else:
            study_at = next_review_slot(
                conn, user_id, duration, preferred_time, keep_id)
        conn.execute(
            """
            UPDATE study_tasks
            SET title=?, study_at=?, duration=?, note=?
            WHERE id=? AND user_id=?
            """,
            (title, study_at, duration, note, keep_id, user_id)
        )

        extra_ids = [row["id"] for row in existing_rows[1:]]
        for task_id in extra_ids:
            conn.execute(
                "DELETE FROM study_tasks WHERE id=? AND user_id=?",
                (task_id, user_id)
            )
        task_id = keep_id
    else:
        study_at = next_review_slot(conn, user_id, duration, preferred_time)
        cursor = conn.execute(
            """
            INSERT INTO study_tasks(
                user_id,subject_id,title,study_at,duration,
                note,done,source,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                user_id,
                subject_id,
                title,
                study_at,
                duration,
                note,
                0,
                "adaptive",
                now()
            )
        )
        task_id = cursor.lastrowid

    return {
        "id": task_id,
        "subject_id": subject_id,
        "subject_name": subject["name"],
        "title": title,
        "study_at": study_at,
        "duration": duration,
        "top_weakness": top_label,
        "weakness_count": len(weaknesses),
        "source": "adaptive"
    }


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for(
                "login", tab="login",
                error="Vui lòng đăng nhập để tiếp tục."
            ))
        conn = db()
        user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if not user:
            session.clear()
            return redirect(url_for("login", tab="login"))
        # All student views and mutations are restricted to students.
        # Admin can only preview shared PDFs through an additional
        # per-document authorization in shared_document_file.
        if user["role"] != "student" and request.endpoint != "shared_document_file":
            return "Vui lòng sử dụng trang quản trị.", 403
        return fn(*args, **kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        uid = session.get("user_id")
        if not uid:
            return redirect(url_for("login", tab="admin"))
        conn = db()
        row = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        if not row or row["role"] != "admin":
            return "Bạn không có quyền truy cập trang quản trị.", 403
        return fn(*args, **kwargs)
    return wrapper


def admin_form_token():
    if "admin_csrf_token" not in session:
        session["admin_csrf_token"] = secrets.token_urlsafe(32)
    return session["admin_csrf_token"]


def admin_csrf_valid():
    submitted = request.form.get("csrf_token", "")
    expected = session.get("admin_csrf_token", "")
    return bool(expected and submitted and secrets.compare_digest(submitted, expected))


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
    """
    Gửi prompt tới Gemini với retry + model failover.

    Thứ tự mặc định:
    1) GEMINI_MODEL (mặc định gemini-3.8-flash)
    2) GEMINI_FALLBACK_MODELS (mặc định 3.6 Flash, 3.5 Flash-Lite)

    Chỉ retry các lỗi tạm thời: 408, 429 và 5xx.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return None, "Chưa cấu hình GEMINI_API_KEY trong file .env."

    if requests is None:
        return None, "Thiếu thư viện requests."

    primary_model = (
        os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        or "gemini-3.8-flash"
    )

    fallback_raw = os.getenv(
        "GEMINI_FALLBACK_MODELS",
        "gemini-3.6-flash,gemini-3.5-flash-lite"
    )

    models = [primary_model]
    for item in fallback_raw.split(","):
        model = item.strip()
        if model and model not in models:
            models.append(model)

    try:
        primary_retries = int(os.getenv("GEMINI_PRIMARY_RETRIES", "2"))
    except ValueError:
        primary_retries = 2
    primary_retries = max(0, min(primary_retries, 4))

    transient_statuses = {408, 429, 500, 502, 503, 504}

    try:
        request_timeout = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "25"))
    except ValueError:
        request_timeout = 25
    request_timeout = max(10, min(request_timeout, 60))

    last_error = ""

    for model_index, model in enumerate(models):
        # Model chính được retry thêm; model dự phòng thử 1 lần/model
        max_attempts = 1 + primary_retries if model_index == 0 else 1

        for attempt in range(max_attempts):
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
                                "parts": [{"text": prompt}],
                            }
                        ]
                    },
                    timeout=request_timeout,
                )

                if res.ok:
                    data = res.json()
                    candidates = data.get("candidates") or []

                    if not candidates:
                        last_error = f"{model}: Gemini không trả về candidate nào."
                        break

                    content = candidates[0].get("content") or {}
                    parts = content.get("parts") or []

                    answer_parts = [
                        str(part.get("text", "")).strip()
                        for part in parts
                        if isinstance(part, dict) and part.get("text")
                    ]

                    answer = "\n".join(
                        part for part in answer_parts if part
                    ).strip()

                    if answer:
                        if model != primary_model:
                            print(f"Gemini failover thành công: {model}")
                        return answer, None

                    last_error = f"{model}: Gemini trả về phản hồi rỗng."
                    break

                detail = ""
                try:
                    error_data = res.json()
                    detail = (
                        error_data.get("error", {}).get("message", "")
                        if isinstance(error_data, dict)
                        else ""
                    )
                except ValueError:
                    detail = res.text[:240]

                status = int(res.status_code)
                last_error = (
                    f"{model}: HTTP {status}"
                    + (f" - {detail}" if detail else "")
                )

                if status not in transient_statuses:
                    # 400/401/403... không retry vì thường là cấu hình/key.
                    return None, last_error

                # Retry model chính với exponential backoff + jitter.
                if model_index == 0 and attempt < max_attempts - 1:
                    delay = min(4.0, (2 ** attempt)) + random.uniform(0.1, 0.5)
                    print(
                        f"Gemini {model} tạm lỗi HTTP {status}; "
                        f"retry sau {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue

                # Hết retry model hiện tại -> thử model kế tiếp.
                break

            except requests.Timeout:
                # Timeout thường do đường truyền/model bị treo; chuyển model
                # ngay để tránh người dùng phải chờ quá lâu khi demo.
                last_error = f"{model}: timeout khi gọi Gemini."
                break

            except requests.RequestException as exc:
                last_error = f"{model}: lỗi kết nối Gemini - {exc}"

                if model_index == 0 and attempt < max_attempts - 1:
                    delay = min(4.0, (2 ** attempt)) + random.uniform(0.1, 0.5)
                    time.sleep(delay)
                    continue

                break

            except (ValueError, TypeError, KeyError, IndexError) as exc:
                last_error = f"{model}: không đọc được phản hồi Gemini - {exc}"
                break

    return None, (
        "AI đang bận hoặc kết nối chưa ổn định. "
        "Hệ thống đã thử model chính và model dự phòng."
        + (f" Chi tiết: {last_error}" if last_error else "")
    )

def gemini_subject_answer(
    subject_name,
    question,
    context,
    source_names,
    conversation_history="",
    shared_context="",
    personal_context="",
    shared_source_names=None
):
    """
    Trả lời theo môn học:
    - Có tài liệu phù hợp: ưu tiên tài liệu và ghi rõ tên file.
    - Tài liệu không đủ / không liên quan: dùng kiến thức chung, không gắn nguồn file.
    - Không có tài liệu: dùng kiến thức chung, không gắn nguồn file.
    """
    source_names = source_names or []
    shared_source_names = shared_source_names or []
    sources_text = ", ".join(source_names) if source_names else "Không có"
    shared_sources_text = (
        ", ".join(shared_source_names)
        if shared_source_names
        else "Không có"
    )

    from chat_output_style import FORMAT_POLICY
    prompt = f"""
Bạn là AI Study Agent đang hỗ trợ môn học: {subject_name}.

{FORMAT_POLICY}

MỤC TIÊU:
Trả lời câu hỏi của sinh viên bằng tiếng Việt, rõ ràng, dễ học và chính xác.
Nếu có HỒ SƠ HỌC TẬP CÁ NHÂN, hãy điều chỉnh cách giải thích theo mục tiêu,
tiến độ và những phần sinh viên thường sai. Không nhắc lại dữ liệu cá nhân
một cách máy móc nếu không cần thiết.
Nếu sinh viên hỏi "môn này cần học gì", "học theo thứ tự nào", "đang học tới đâu"
hoặc câu hỏi tương tự về phạm vi/lộ trình, hãy xem ĐỀ CƯƠNG MÔN HỌC trong
KIẾN THỨC CHUNG là nguồn ưu tiên số 1 và trình bày theo đúng thứ tự đề cương.
Tài liệu cá nhân dùng để giải thích/bổ sung cho từng mục, không được tự mở rộng
phạm vi môn học ngoài đề cương nếu đề cương đã có.

QUY TẮC NGUỒN RẤT QUAN TRỌNG:
1. Nếu NGỮ CẢNH TÀI LIỆU CÁ NHÂN thực sự hỗ trợ câu trả lời,
   đặt mode = "document" và chỉ liệt kê file cá nhân thực sự dùng.
2. Nếu KIẾN THỨC CHUNG THEO MÔN hoặc đề cương hỗ trợ câu trả lời,
   đặt mode = "shared" và chỉ liệt kê nguồn dùng chung thực sự dùng.
3. Nếu không có nguồn phù hợp, đặt mode = "general" và dùng kiến thức chung của mô hình.
4. Khi mode = "general", sources phải là mảng rỗng.
5. Không được giả vờ thông tin nằm trong tài liệu/đề cương nếu nguồn không hỗ trợ.
6. Không sao chép nguyên văn dài từ nguồn.

CÁC FILE CÁ NHÂN ĐƯỢC CUNG CẤP:
{sources_text}

CÁC NGUỒN DÙNG CHUNG ĐƯỢC CUNG CẤP:
{shared_sources_text}

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

Chỉ trả về một JSON hợp lệ, không dùng code fence bao ngoài JSON.
Trường "answer" ĐƯỢC dùng Markdown hoặc công thức toán để trình bày đẹp,
nhưng phải nằm bên trong chuỗi JSON escape đúng quy tắc. Cấu trúc:
{{
  "mode": "document", "shared" hoặc "general",
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

            personal_allowed = {name: name for name in source_names}
            shared_allowed = {name: name for name in shared_source_names}
            used_sources = []

            if isinstance(requested_sources, list):
                allowed = (
                    personal_allowed
                    if mode == "document"
                    else shared_allowed
                    if mode == "shared"
                    else {}
                )
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

            if mode == "shared" and used_sources:
                if len(used_sources) == 1:
                    source_line = f'Dựa trên kiến thức chung "{used_sources[0]}":'
                else:
                    joined = ", ".join(f'"{name}"' for name in used_sources)
                    source_line = f"Dựa trên các nguồn kiến thức chung {joined}:"

                return source_line + "\n\n" + answer, used_sources, "shared"

            # Không có nguồn hợp lệ -> coi là kiến thức chung để tránh gắn nguồn sai.
            return answer, [], "general"

        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            print("Không đọc được JSON Chat từ Gemini:", exc)
            # Không gắn tên file khi không xác định chắc chắn mode nguồn.
            cleaned = raw.strip()
            return cleaned, [], "general"

    # Nếu Gemini/model dự phòng đều lỗi, vẫn cố gắng trả lời từ
    # tài liệu cá nhân hoặc kiến thức chung đã có trong hệ thống.
    fallback_context_parts = []
    fallback_sources = []
    fallback_mode = "general"

    if context:
        fallback_context_parts.append(context)
        fallback_sources.extend(source_names)
        fallback_mode = "document"

    if shared_context:
        fallback_context_parts.append(shared_context)
        for name in shared_source_names:
            if name not in fallback_sources:
                fallback_sources.append(name)
        if fallback_mode == "general":
            fallback_mode = "shared"

    fallback_context = "\n\n".join(fallback_context_parts)
    fallback = local_ai_answer(
        question,
        fallback_context,
        fallback_sources
    )

    if error:
        print("Gemini Chat fallback:", error)

    return (
        fallback,
        fallback_sources if fallback_context else [],
        fallback_mode
    )


def build_quiz(text, question_count=10, focus_topics=None, session_mode=False, avoid_questions=None):
    """
    Tạo quiz 10 / 20 / 30 câu bằng Gemini.

    focus_topics (nếu có) dùng để ưu tiên các chủ đề sinh viên đang yếu.
    Để tránh Gemini trả thiếu câu khi yêu cầu quá dài,
    hệ thống tạo theo từng nhóm tối đa 10 câu rồi ghép lại.
    """
    focus_topics = focus_topics or []

    # =====================================================
    # CHỈ CHO PHÉP 10 / 20 / 30
    # =====================================================
    try:
        question_count = int(question_count)
    except (TypeError, ValueError):
        question_count = 10

    if session_mode:
        if question_count < 1 or question_count > 60:
            return []
    elif question_count not in (10, 20, 30):
        question_count = 10

    clean_text = (text or "").strip()


    # Không bịa câu điền từ hay đáp án A cố định khi Gemini không khả dụng.
    # Trả lỗi rõ ràng để không làm méo dữ liệu Adaptive Learning.
    if not clean_text:
        return []


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

        topic = re.sub(
            r"\s+",
            " ",
            str(item.get("topic") or "").strip()
        )[:160]
        chapter = re.sub(
            r"\s+",
            " ",
            str(item.get("chapter") or "").strip()
        )[:120]

        if not question:
            return None

        # Course metadata is not a learning outcome: the model often turns
        # administrative syllabus fields into trivial memory questions.
        if re.search(
            r"(?:giảng viên|giáo viên|người dạy|mã học phần|mã môn học|"
            r"mã môn|bao nhiêu tín chỉ|số tín chỉ|course code|lecturer|"
            r"tên giảng viên|tên giáo viên|họ tên giáo viên|mã lớp|"
            r"phòng học|lịch học|địa chỉ email|email giảng viên)",
            question.casefold()
        ):
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

        if not topic:
            topic = re.sub(r"\s+", " ", question).strip()[:160]

        if not chapter:
            chapter = "Nội dung tài liệu"

        return {
            "question": question,
            "topic": topic,
            "chapter": chapter,
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

        if existing_questions or avoid_questions:
            # Chỉ gửi phần câu hỏi để Gemini tránh lặp,
            # không cần gửi lại options/answer.
            avoid_lines = [
                f"- {q['question']}"
                for q in existing_questions[-25:]
            ] + ["- " + str(q)[:260] for q in (avoid_questions or [])[-80:]]

            avoid_text = (
                "\\nCÁC CÂU ĐÃ TẠO - KHÔNG ĐƯỢC LẶP LẠI:\\n"
                + "\\n".join(avoid_lines)
            )

        focus_lines = []
        for item in focus_topics[:8]:
            if isinstance(item, dict):
                topic = str(item.get("topic") or "").strip()
                chapter = str(item.get("chapter") or "").strip()
                miss_count = item.get("miss_count")
                if topic:
                    label = f"{chapter} - {topic}" if chapter else topic
                    if miss_count is not None:
                        label += f" (đã sai {miss_count} lần)"
                    focus_lines.append(f"- {label}")
            else:
                topic = str(item or "").strip()
                if topic:
                    focus_lines.append(f"- {topic}")

        focus_text = (
            "\nCÁC CHỦ ĐỀ CẦN ƯU TIÊN ÔN TẬP:\n"
            + "\n".join(focus_lines)
            + (
                "\nHãy dành phần lớn câu hỏi cho các chủ đề này nếu tài liệu có nội dung liên quan.\n"
                "Khi câu hỏi kiểm tra một chủ đề ưu tiên, trường topic PHẢI dùng nguyên văn "
                "tên chủ đề trong danh sách trên; chapter cũng giữ nguyên nếu đã có.\n"
            )
            if focus_lines
            else ""
        )

        focus_policy = (
            "- Đây là BÀI KIỂM TRA KIẾN THỨC theo từng buổi, không phải "
            "trắc nghiệm dữ liệu hành chính của đề cương. "
            "Tập trung vào định nghĩa, nguyên lý, thuật toán, "
            "bài tập vận dụng, phân tích tình huống và công thức. "
            "KHÔNG hỏi tên giảng viên/giáo viên, mã môn/mã học phần, "
            "số tín chỉ, lịch học, phòng học, email, trường/khoa. "
            "Không dùng thông tin giới thiệu làm câu hỏi. "
            "Câu hỏi phải được chứng minh từ NỘI DUNG KIẾN THỨC cung cấp; "
            "không suy diễn từ tiêu đề hoặc tự bổ sung kiến thức."
            if session_mode else ""
        )
        prompt = f"""
Bạn là AI Study Agent.

{focus_policy}

Nhiệm vụ:
Tạo đúng {batch_size} câu hỏi trắc nghiệm bằng tiếng Việt
cho NHÓM {batch_number}, dựa CHỈ trên nội dung tài liệu.
{focus_text}

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
- Không tạo câu hỏi chỉ để nhớ email, số điện thoại, tên giảng viên hoặc thông tin hành chính; ưu tiên kiến thức chuyên môn.
- Ưu tiên phủ nhiều phần kiến thức khác nhau trong tài liệu.
- Mỗi câu phải có "topic": tên chủ đề/khái niệm ngắn gọn mà câu hỏi đang kiểm tra.
- Mỗi câu phải có "chapter": tên chương/phần tương ứng nếu xác định được từ tài liệu.
- Nếu tài liệu không ghi rõ chương/phần, chapter dùng "Nội dung tài liệu".
- Không dùng nguyên câu hỏi làm topic.
- answer là vị trí đáp án đúng: 0=A, 1=B, 2=C, 3=D.

CHỈ trả về JSON array.
Không markdown.
Không ```json.
Không giải thích thêm.

Cấu trúc:
[
  {{
    "question": "Nội dung câu hỏi",
    "topic": "Tên chủ đề ngắn gọn",
    "chapter": "Tên chương/phần",
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


    # Không ghi Quiz bị thiếu câu. Nguồn AI lỗi -> UI hướng dẫn thử lại.
    if len(questions) != question_count:
        return []

    # Với Quiz ôn điểm yếu, chuẩn hóa topic/chapter về đúng nhãn weakness cũ.
    # Nhờ vậy lần làm đúng sau đó sẽ tăng correct_count của chính weakness đó,
    # thay vì tạo một topic gần giống nhưng khác key.
    if focus_topics:
        stop_tokens = {
            "chương", "phần", "bài", "nội", "dung", "tài", "liệu",
            "các", "của", "và", "trong", "theo", "với", "một"
        }

        canonical_topics = []
        for item in focus_topics[:12]:
            if not isinstance(item, dict):
                continue

            topic_value = re.sub(
                r"\s+",
                " ",
                str(item.get("topic") or "").strip()
            )[:220]
            chapter_value = re.sub(
                r"\s+",
                " ",
                str(item.get("chapter") or "").strip()
            )[:120]
            if not topic_value:
                continue

            token_set = {
                token.casefold()
                for token in re.findall(
                    r"[\wÀ-ỹ]+",
                    f"{chapter_value} {topic_value}",
                    flags=re.UNICODE
                )
                if len(token) >= 3 and token.casefold() not in stop_tokens
            }

            canonical_topics.append({
                "topic": topic_value,
                "chapter": chapter_value,
                "tokens": token_set
            })

        for question in questions:
            question_tokens = {
                token.casefold()
                for token in re.findall(
                    r"[\wÀ-ỹ]+",
                    (
                        f"{question.get('chapter', '')} "
                        f"{question.get('topic', '')} "
                        f"{question.get('question', '')}"
                    ),
                    flags=re.UNICODE
                )
                if len(token) >= 3 and token.casefold() not in stop_tokens
            }

            best = None
            best_score = 0
            for candidate in canonical_topics:
                overlap = len(question_tokens & candidate["tokens"])
                if overlap > best_score:
                    best = candidate
                    best_score = overlap

            if best and best_score > 0:
                question["topic"] = best["topic"]
                question["chapter"] = best["chapter"] or question.get(
                    "chapter",
                    "Nội dung tài liệu"
                )

    # Hoán vị bốn lựa chọn, đồng thời cập nhật đáp án đúng tương ứng.
    # Tránh mẫu đáp án cố định, vẫn giữ chấm điểm tuyệt đối ở backend.
    for question in questions:
        permutation = list(range(4))
        random.shuffle(permutation)
        original_options = list(question["options"])
        original_answer = question["answer"]
        question["options"] = [original_options[i] for i in permutation]
        question["answer"] = permutation.index(original_answer)

    return questions

def _safe_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _extract_syllabus_topics(syllabus_text, max_topics=24):
    """Tách các mục học chính từ đề cương để lộ trình luôn bám đúng phạm vi môn."""
    text_value = (syllabus_text or "").strip()
    if not text_value:
        return []

    raw_lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in text_value.replace("\r", "\n").split("\n")
        if re.sub(r"\s+", " ", line).strip()
    ]

    heading_pattern = re.compile(
        r"^(?:chương|bài|phần|tuần|unit|module|chapter|lesson|topic)\s*"
        r"(?:[ivxlcdm]+|\d+(?:\.\d+)*)?\s*[:.\-–—]?\s*.+$",
        re.IGNORECASE,
    )
    numbered_pattern = re.compile(
        r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)\-:]?\s+.+$",
        re.IGNORECASE,
    )
    bullet_pattern = re.compile(r"^[•●▪◦*+\-–—]\s+.+$")

    selected = []
    fallback_lines = []

    for line in raw_lines:
        cleaned = re.sub(r"^[•●▪◦*+\-–—]\s*", "", line).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        if len(cleaned) < 3 or len(cleaned) > 220:
            continue

        fallback_lines.append(cleaned)

        if (
            heading_pattern.match(line)
            or numbered_pattern.match(line)
            or bullet_pattern.match(line)
        ):
            selected.append(cleaned)

    # Một số đề cương chỉ là danh sách dòng không đánh số/bullet.
    if len(selected) < 2:
        selected = fallback_lines

    topics = []
    seen = set()
    for item in selected:
        normalized = item.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        topics.append(item)
        if len(topics) >= max_topics:
            break

    return topics


def get_course_learning_backbone(conn, user_id, subject_id, query=""):
    """
    Course Learning Backbone:
    Đề cương là khung chính; shared knowledge và tài liệu cá nhân là nguồn bổ trợ.
    Hàm này dùng chung cho Web và Mobile để tránh hai frontend sinh lộ trình khác nhau.
    """
    subject = conn.execute(
        """
        SELECT id,name,code,target_score,progress,shared_subject_id,
               personal_syllabus_document_id
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, user_id)
    ).fetchone()

    if not subject:
        return None

    shared = ensure_shared_subject_for_user_subject(
        conn,
        user_id,
        subject_id
    )

    shared_syllabus_text = (
        (shared["syllabus_text"] or "").strip()
        if shared
        else ""
    )

    personal_syllabus_doc = None
    personal_syllabus_text = ""
    personal_syllabus_id = subject["personal_syllabus_document_id"]
    if personal_syllabus_id:
        personal_syllabus_doc = conn.execute(
            """
            SELECT id,original_name,extracted_text
            FROM documents
            WHERE id=? AND user_id=? AND subject_id=?
            """,
            (personal_syllabus_id, user_id, subject_id)
        ).fetchone()
        if personal_syllabus_doc:
            personal_syllabus_text = (
                personal_syllabus_doc["extracted_text"] or ""
            ).strip()

    # Đề cương chuẩn luôn ưu tiên. Khi Shared Knowledge chưa có syllabus,
    # sinh viên có thể chọn một tài liệu cá nhân làm đề cương fallback.
    syllabus_text = shared_syllabus_text or personal_syllabus_text
    syllabus_source = (
        "shared"
        if shared_syllabus_text
        else "personal"
        if personal_syllabus_text
        else "none"
    )
    syllabus_source_name = (
        "Đề cương chuẩn của môn"
        if syllabus_source == "shared"
        else personal_syllabus_doc["original_name"]
        if personal_syllabus_doc
        else ""
    )
    syllabus_topics = _extract_syllabus_topics(syllabus_text)

    document_rows = conn.execute(
        """
        SELECT original_name, extracted_text
        FROM documents
        WHERE user_id=? AND subject_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (user_id, subject_id)
    ).fetchall()

    personal_parts = []
    document_names = []
    personal_total = 0
    for row in document_rows:
        text_value = (row["extracted_text"] or "").strip()
        if not text_value:
            continue
        remaining = 8000 - personal_total
        if remaining <= 0:
            break
        clipped = text_value[:min(1800, remaining)]
        personal_parts.append(
            f"TÀI LIỆU CÁ NHÂN - {row['original_name']}:\n{clipped}"
        )
        document_names.append(row["original_name"])
        personal_total += len(clipped)

    shared_parts = []
    shared_names = []
    if shared:
        knowledge_rows = conn.execute(
            """
            SELECT title,content,source_type
            FROM shared_knowledge
            WHERE shared_subject_id=?
            ORDER BY id DESC
            LIMIT 10
            """,
            (shared["id"],)
        ).fetchall()

        query_terms = {
            token.casefold()
            for token in re.findall(
                r"[\wÀ-ỹ]+",
                query or "",
                flags=re.UNICODE
            )
            if len(token) >= 3
        }

        scored_rows = []
        for row in knowledge_rows:
            content_value = (row["content"] or "").strip()
            if not content_value:
                continue
            lowered = content_value.casefold()
            score = sum(lowered.count(term) for term in query_terms)
            scored_rows.append((score, row))

        scored_rows.sort(key=lambda item: item[0], reverse=True)

        shared_total = 0
        for _, row in scored_rows:
            remaining = 6500 - shared_total
            if remaining <= 0:
                break
            content_value = (row["content"] or "").strip()
            clipped = content_value[:min(1600, remaining)]
            shared_parts.append(
                f"KIẾN THỨC DÙNG CHUNG - {row['title']}:\n{clipped}"
            )
            shared_names.append(row["title"])
            shared_total += len(clipped)

    return {
        "subject": subject,
        "syllabus_text": syllabus_text[:12000],
        "syllabus_topics": syllabus_topics,
        "syllabus_source": syllabus_source,
        "syllabus_source_name": syllabus_source_name,
        "personal_context": "\n\n".join(personal_parts),
        "personal_document_names": document_names,
        "shared_context": "\n\n".join(shared_parts),
        "shared_source_names": shared_names,
    }


def _fallback_study_plan(
    subject_name,
    goal,
    deadline_dt,
    daily_minutes,
    preferred_time,
    priority_topics=None,
    syllabus_topics=None,
    document_names=None,
):
    """
    Kế hoạch cục bộ khi Gemini/API lỗi.
    Nếu có đề cương, fallback vẫn đi theo đúng thứ tự các mục trong đề cương
    thay vì tạo một roadmap chung chung.
    """
    priority_topics = priority_topics or []
    syllabus_topics = syllabus_topics or []
    document_names = document_names or []

    today = datetime.now().date()
    end_date = max(today, deadline_dt.date())
    span_days = max(0, (end_date - today).days)

    if span_days == 0:
        session_count = 1
    elif span_days <= 3:
        session_count = span_days + 1
    else:
        session_count = min(8, max(4, (span_days + 1) // 2))

    weak_units = []
    for item in priority_topics[:4]:
        if isinstance(item, dict):
            topic = str(item.get("topic") or "").strip()
            chapter = str(item.get("chapter") or "").strip()
            miss_count = _safe_int(item.get("miss_count"), 0, 0, 999)
        else:
            topic = str(item or "").strip()
            chapter = ""
            miss_count = 0

        if not topic:
            continue

        label = f"{chapter} - {topic}" if chapter else topic
        note = (
            "Ưu tiên vì đây là phần còn yếu"
            + (f", đã sai {miss_count} lần" if miss_count else "")
            + ". Ôn lại khái niệm, ví dụ và ghi chú nguyên nhân chưa vững."
        )
        weak_units.append((label, note))

    weak_keys = {
        re.sub(r"\s+", " ", label).casefold()
        for label, _ in weak_units
    }
    syllabus_units = []
    for topic in syllabus_topics:
        normalized = re.sub(r"\s+", " ", topic).casefold()
        if any(
            normalized in weak_key or weak_key in normalized
            for weak_key in weak_keys
        ):
            continue
        syllabus_units.append(topic)

    learning_slots = session_count - 1 if session_count >= 2 else 1
    units = [label for label, _ in weak_units] + syllabus_units

    if not units:
        units = [goal or f"Nội dung trọng tâm môn {subject_name}"]

    chunks = []
    for index in range(learning_slots):
        start = round(index * len(units) / learning_slots)
        end = round((index + 1) * len(units) / learning_slots)
        chunk = units[start:end]
        if not chunk and units:
            chunk = [units[min(index, len(units) - 1)]]
        chunks.append(chunk)

    docs_text = (
        " Tài liệu tham khảo của bạn: " + ", ".join(document_names[:3]) + "."
        if document_names
        else ""
    )

    tasks = []
    for i in range(session_count):
        if session_count == 1:
            offset = 0
        else:
            offset = round(i * span_days / (session_count - 1))
        task_date = today + timedelta(days=offset)

        if session_count >= 2 and i == session_count - 1:
            title = "Kiểm tra và đánh giá cuối lộ trình"
            note = (
                "Làm Quiz theo các phần đã học, xem lại câu sai và xác định "
                "nội dung cần ôn tiếp trước deadline."
            )
        else:
            chunk = chunks[min(i, len(chunks) - 1)] if chunks else []
            short_label = " · ".join(chunk[:2])[:120]
            title = (
                f"Học theo đề cương: {short_label}"
                if syllabus_topics and short_label
                else f"Học: {short_label or goal or subject_name}"
            )[:160]

            full_scope = "; ".join(chunk)[:320]
            note = (
                f"Mục tiêu: {goal}. "
                if i == 0 and goal
                else ""
            )
            note += (
                f"Bám theo đề cương: {full_scope}. "
                if syllabus_topics and full_scope
                else f"Tập trung nội dung: {full_scope}. "
            )
            note += (
                "Đọc tài liệu liên quan, ghi chú ý chính và dùng Study Agent "
                "để hỏi ngay phần chưa hiểu."
            )
            note += docs_text

        tasks.append({
            "date": task_date.isoformat(),
            "time": preferred_time,
            "title": title,
            "duration": daily_minutes,
            "note": note[:500],
        })

    return tasks


def build_study_plan(
    subject_name,
    goal,
    deadline_dt,
    daily_minutes,
    preferred_time,
    context="",
    syllabus_text="",
    syllabus_topics=None,
    shared_context="",
    personal_context="",
    priority_topics=None,
    document_names=None,
):
    """
    Tạo lộ trình học theo Course Learning Backbone:
    Đề cương -> tài liệu -> học -> kiểm tra/đánh giá.
    """
    syllabus_topics = syllabus_topics or _extract_syllabus_topics(syllabus_text)
    priority_topics = priority_topics or []
    document_names = document_names or []

    fallback = _fallback_study_plan(
        subject_name,
        goal,
        deadline_dt,
        daily_minutes,
        preferred_time,
        priority_topics=priority_topics,
        syllabus_topics=syllabus_topics,
        document_names=document_names,
    )

    today = datetime.now().date().isoformat()
    deadline_date = deadline_dt.date().isoformat()
    topic_outline = "\n".join(
        f"{index + 1}. {topic}"
        for index, topic in enumerate(syllabus_topics[:24])
    )

    prompt = f"""
Bạn là AI Study Planner trong hệ thống AI Study Agent.

NHIỆM VỤ:
Biến đề cương của một môn thành lộ trình học có thể thực hiện được:
ĐỀ CƯƠNG -> TÀI LIỆU -> HỌC -> KIỂM TRA/ĐÁNH GIÁ.

THÔNG TIN NGƯỜI HỌC:
- Môn học: {subject_name}
- Mục tiêu: {goal}
- Ngày hiện tại: {today}
- Deadline: {deadline_date}
- Thời lượng tối đa mỗi buổi: {daily_minutes} phút
- Giờ học ưu tiên: {preferred_time}

ĐỀ CƯƠNG GỐC - NGUỒN XÁC ĐỊNH PHẠM VI HỌC:
{syllabus_text[:7000] if syllabus_text else "Chưa có đề cương."}

CÁC MỤC HỌC ĐÃ NHẬN DIỆN TỪ ĐỀ CƯƠNG:
{topic_outline if topic_outline else "Chưa nhận diện được mục học cụ thể."}

TÀI LIỆU CÁ NHÂN - NGUỒN BỔ TRỢ CHO CÁC MỤC TRONG ĐỀ CƯƠNG:
{context[:5500] if context else "Không có tài liệu cá nhân cho môn học này."}

KIẾN THỨC DÙNG CHUNG - NGUỒN BỔ TRỢ:
{shared_context[:4500] if shared_context else "Chưa có kiến thức dùng chung bổ sung."}

HỒ SƠ HỌC TẬP CÁ NHÂN:
{personal_context[:3500] if personal_context else "Chưa có dữ liệu cá nhân hóa."}

NGUYÊN TẮC BẮT BUỘC:
1. Nếu có đề cương, ĐỀ CƯƠNG là nguồn chính để xác định học những gì.
2. Giữ thứ tự logic của các mục trong đề cương; không tự thêm chương/chủ đề ngoài phạm vi.
3. Tài liệu cá nhân và kiến thức dùng chung chỉ dùng để bổ sung nội dung cho các mục đề cương.
4. Mỗi buổi học phải nêu rõ đang học mục/chương nào của đề cương trong title hoặc note.
5. Không cố định 7 ngày; số buổi phải phù hợp thời gian còn lại và tối đa 8 buổi.
6. Mọi ngày học phải nằm từ {today} đến {deadline_date}.
7. Nếu số mục đề cương nhiều hơn số buổi, gộp các mục liền kề hợp lý nhưng vẫn giữ thứ tự.
8. Nếu hồ sơ có phần kiến thức cần chú ý/điểm yếu, ưu tiên ôn phần đó sớm nhưng không làm mất cấu trúc đề cương.
9. Phải có ít nhất một hoạt động kiểm tra/Quiz hoặc xem lại câu sai trước deadline nếu có từ 2 buổi trở lên.
10. Có thể dùng Study Agent để giải thích phần chưa hiểu trong từng buổi học.
11. Không tạo công việc ngoài phạm vi học tập.
12. Chỉ trả về một JSON array, không markdown, không giải thích thêm.
13. Mỗi phần tử có đúng các trường:
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

        if not valid:
            return fallback

        if syllabus_topics:
            topic_tokens = set()
            stop_words = {
                "chương", "phần", "bài", "tuần", "module", "unit", "chapter",
                "lesson", "và", "các", "của", "trong", "theo", "với", "một"
            }
            for topic in syllabus_topics[:16]:
                for token in re.findall(r"[\wÀ-ỹ]+", topic, flags=re.UNICODE):
                    token_value = token.casefold()
                    if len(token_value) >= 4 and token_value not in stop_words:
                        topic_tokens.add(token_value)

            learning_tasks = [
                task for task in valid
                if not any(
                    marker in (task["title"] + " " + task["note"]).casefold()
                    for marker in ("quiz", "kiểm tra", "đánh giá", "câu sai")
                )
            ]
            matched_tasks = 0
            for task in learning_tasks:
                task_text = (task["title"] + " " + task["note"]).casefold()
                if any(token in task_text for token in topic_tokens):
                    matched_tasks += 1

            required_matches = max(1, (len(learning_tasks) + 1) // 2)
            if learning_tasks and matched_tasks < required_matches:
                return fallback

        return valid

    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print("Study planner JSON fallback:", exc)
        return fallback


def _format_weekday(dt):
    labels = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
    return labels[dt.weekday()]


@app.route("/")
def index():
    if "user_id" in session:
        conn = db()
        user = conn.execute("SELECT role FROM users WHERE id=?", (session["user_id"],)).fetchone()
        conn.close()
        return redirect(url_for("admin_dashboard" if user and user["role"] == "admin" else "dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = request.args.get("error", "").strip()[:300]
    auth_tab = request.args.get("tab", "login").strip().lower()
    if auth_tab not in {"login", "signup", "admin"}:
        auth_tab = "login"

    if request.method == "POST":
        auth_tab = "login"
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        conn.close()
        if user and user["role"] == "student" and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        error = "Email hoặc mật khẩu không đúng."

    return render_template(
        "login.html",
        error=error,
        auth_tab=auth_tab
    )

@app.route("/admin/login", methods=["POST"])
def admin_login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    if user and user["role"] == "admin" and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("login", tab="admin", error="Tài khoản quản trị hoặc mật khẩu không đúng."))


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if (
        not name
        or not email
        or len(password) < 6
        or password != confirm_password
    ):
        return redirect(
            url_for(
                "login",
                tab="signup",
                error="Vui lòng nhập đủ thông tin, mật khẩu tối thiểu 6 ký tự và xác nhận trùng khớp."
            )
        )

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
        return redirect(
            url_for(
                "login",
                tab="signup",
                error="Email này đã được đăng ký."
            )
        )
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

    today_start = now_dt.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )
    tomorrow_start = today_start + timedelta(days=1)

    today_task_rows = conn.execute(
        """
        SELECT t.id,t.subject_id,t.title,t.study_at,t.duration,t.done,t.source,
               s.name AS subject_name
        FROM study_tasks t
        LEFT JOIN subjects s
          ON s.id=t.subject_id AND s.user_id=t.user_id
        WHERE t.user_id=?
          AND t.study_at>=?
          AND t.study_at<?
        ORDER BY t.done ASC,t.study_at ASC,t.id ASC
        LIMIT 6
        """,
        (
            uid,
            today_start.isoformat(timespec="minutes"),
            tomorrow_start.isoformat(timespec="minutes")
        )
    ).fetchall()

    today_tasks = []
    for row in today_task_rows:
        item = dict(row)
        try:
            task_dt = datetime.fromisoformat(row["study_at"])
            item["time_text"] = task_dt.strftime("%H:%M")
        except (TypeError, ValueError):
            item["time_text"] = "--:--"
        today_tasks.append(item)

    next_best_action = get_next_best_action(
        conn,
        uid
    )

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
        today_tasks=today_tasks,
        quiz_count=quiz_count,
        avg_progress=avg_progress,
        weekly_study_hours=weekly_study_hours,
        weekly_total_hours=weekly_total_hours,
        previous_week_hours=previous_week_hours,
        weekly_growth_text=weekly_growth_text,
        weekly_growth_class=weekly_growth_class,
        next_best_action=next_best_action
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

@app.route("/subjects/<int:subject_id>", methods=["GET", "POST"])
@login_required
def subject_detail(subject_id):
    uid = session["user_id"]
    conn = db()

    subject = conn.execute(
        """
        SELECT *
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, uid)
    ).fetchone()

    if not subject:
        conn.close()
        return redirect(url_for("subjects"))

    shared = ensure_shared_subject_for_user_subject(
        conn,
        uid,
        subject_id
    )
    profile = ensure_learning_profile(conn, uid)

    if request.method == "POST":
        action_type = request.form.get("action_type", "").strip()

        if action_type == "profile":
            learning_style = (
                request.form.get("learning_style", "balanced").strip()[:40]
                or "balanced"
            )
            preferred_study_time = (
                request.form.get("preferred_study_time", "19:00").strip()
                or "19:00"
            )
            if not re.fullmatch(
                r"(?:[01]\d|2[0-3]):[0-5]\d",
                preferred_study_time
            ):
                preferred_study_time = "19:00"

            daily_minutes = _safe_int(
                request.form.get("daily_minutes"),
                45,
                15,
                240
            )
            goals = request.form.get("goals", "").strip()[:1200]
            notes = request.form.get("notes", "").strip()[:1200]

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

        elif action_type == "personal_syllabus":
            selected_doc_id = request.form.get(
                "personal_syllabus_document_id",
                type=int
            )

            if selected_doc_id:
                selected_doc = conn.execute(
                    """
                    SELECT id
                    FROM documents
                    WHERE id=? AND user_id=? AND subject_id=?
                    """,
                    (selected_doc_id, uid, subject_id)
                ).fetchone()
                if not selected_doc:
                    conn.close()
                    return "Tài liệu đề cương không hợp lệ.", 400

            conn.execute(
                """
                UPDATE subjects
                SET personal_syllabus_document_id=?
                WHERE id=? AND user_id=?
                """,
                (selected_doc_id, subject_id, uid)
            )

        elif action_type in {"syllabus", "shared_file", "shared_note"}:
            # Shared Knowledge là dữ liệu học thuật dùng chung của môn.
            # Ở scope sinh viên hiện tại, tài khoản sinh viên chỉ được đọc,
            # không được ghi dữ liệu cá nhân vào kho dùng chung.
            conn.close()
            return (
                "Kho kiến thức chung chỉ đọc đối với sinh viên. "
                "Tài liệu sinh viên tải lên luôn được lưu ở phạm vi cá nhân.",
                403
            )

        elif action_type:
            conn.close()
            return "Thao tác không hợp lệ.", 400

        conn.commit()
        conn.close()
        return redirect(
            url_for("subject_detail", subject_id=subject_id)
        )

    recalculate_subject_progress(uid, subject_id, conn)
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()

    shared = ensure_shared_subject_for_user_subject(
        conn,
        uid,
        subject_id
    )
    profile = ensure_learning_profile(conn, uid)

    shared_items = conn.execute(
        """
        SELECT id,title,content,source_type,created_at
        FROM shared_knowledge
        WHERE shared_subject_id=?
        ORDER BY id DESC
        LIMIT 12
        """,
        (shared["id"],)
    ).fetchall()

    shared_file_ids = {
        row["knowledge_id"]: row["id"]
        for row in conn.execute(
            "SELECT knowledge_id,id FROM shared_documents "
            "WHERE shared_subject_id=?",
            (shared["id"],)
        ).fetchall()
    }

    weaknesses = conn.execute(
        """
        SELECT topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
          AND miss_count > correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC, last_seen_at DESC
        LIMIT 8
        """,
        (uid, subject_id)
    ).fetchall()

    docs = conn.execute(
        """
        SELECT id,original_name,created_at
        FROM documents
        WHERE user_id=? AND subject_id=?
        ORDER BY id DESC
        LIMIT 8
        """,
        (uid, subject_id)
    ).fetchall()

    syllabus_documents = conn.execute(
        """
        SELECT id,original_name,created_at
        FROM documents
        WHERE user_id=? AND subject_id=?
        ORDER BY id DESC
        LIMIT 100
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

    upcoming_tasks = conn.execute(
        """
        SELECT id,title,study_at,duration
        FROM study_tasks
        WHERE user_id=? AND subject_id=? AND done=0
        ORDER BY study_at ASC
        LIMIT 5
        """,
        (uid, subject_id)
    ).fetchall()

    next_best_action = get_next_best_action(
        conn,
        uid,
        subject_id=subject_id
    )
    # Phase 8.1/8.2: evidence-backed and read-only; no Gemini on page load.
    from adaptive_decision_phase8 import decide_next_learning_step
    adaptive_decision = decide_next_learning_step(conn, uid, subject_id)
    from adaptive_plan_phase8 import proposal_for_subject
    adaptive_plan_proposal = proposal_for_subject(conn, uid, subject_id)
    if "adaptive_plan_csrf" not in session:
        session["adaptive_plan_csrf"] = secrets.token_urlsafe(32)

    conn.close()

    return render_template(
        "subject_detail.html",
        page="subjects",
        subject=subject,
        shared_subject=shared,
        shared_items=shared_items,
        shared_file_ids=shared_file_ids,
        profile=profile,
        weaknesses=weaknesses,
        documents=docs,
        syllabus_documents=syllabus_documents,
        quiz_stats=quiz_stats,
        upcoming_tasks=upcoming_tasks,
        next_best_action=next_best_action,
        adaptive_decision=adaptive_decision,
        adaptive_plan_proposal=adaptive_plan_proposal,
        adaptive_plan_csrf=session["adaptive_plan_csrf"]
    )


@app.route("/subjects/<int:subject_id>/adaptive-plan", methods=["POST"])
@login_required
def choose_adaptive_plan(subject_id):
    """Phase 8.3: explicit, CSRF-protected consent; owner-scoped and atomic."""
    from adaptive_plan_phase8 import apply_student_choice
    submitted_csrf = request.form.get("csrf_token", "")
    expected_csrf = session.get("adaptive_plan_csrf", "")
    if not expected_csrf or not secrets.compare_digest(submitted_csrf, expected_csrf):
        return "Phiên xác nhận không hợp lệ. Tải lại trang và thử lại.", 403
    uid = session["user_id"]
    conn = db()
    try:
        proposal = apply_student_choice(
            conn, uid, subject_id, request.form.get("proposal_key"),
            request.form.get("choice")
        )
    except (ValueError, sqlite3.IntegrityError):
        conn.close()
        return redirect(url_for("subject_detail", subject_id=subject_id,
                                adaptive_notice="stale"), code=303)
    conn.close()
    notice = "accepted" if request.form.get("choice") == "accept" else "dismissed"
    return redirect(url_for("subject_detail", subject_id=subject_id,
                            adaptive_notice=notice), code=303)


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
        # Keep old unclassified documents/Quiz/tasks + new session metadata.
        from subject_course_cleanup import detach_subject_learning_records
        detach_subject_learning_records(conn, uid, subject_id)
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
            "DELETE FROM reminders WHERE subject_id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.execute(
            "DELETE FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid)
        )
        conn.commit()

    conn.close()
    return redirect(url_for("subjects"))

# =============================================================
# ADMIN: shared course catalog and pre-extracted common documents
# =============================================================
@app.route("/admin")
@admin_required
def admin_dashboard():
    # Keep the original Admin entry point for the subjects page.
    if request.args.get("view") == "documents":
        return redirect(url_for(
            "admin_shared_documents",
            error=request.args.get("error", ""),
            notice=request.args.get("notice", "")
        ))
    return _render_admin_page("subjects")


@app.route("/admin/documents", methods=["GET"])
@admin_required
def admin_shared_documents():
    return _render_admin_page("documents")


def _render_admin_page(admin_view):
    # Both pages share the current Admin layout but render different sections.
    conn = db()
    subjects = conn.execute(
        """SELECT ss.*, COUNT(sd.id) AS document_count
           FROM shared_subjects ss
           LEFT JOIN shared_documents sd ON sd.shared_subject_id=ss.id
           WHERE ss.admin_managed=1
           GROUP BY ss.id ORDER BY ss.updated_at DESC, ss.id DESC"""
    ).fetchall()
    documents = conn.execute(
        """SELECT sd.*, ss.name AS subject_name, ss.code AS subject_code
           FROM shared_documents sd JOIN shared_subjects ss ON ss.id=sd.shared_subject_id
           ORDER BY sd.id DESC LIMIT 120"""
    ).fetchall()
    count = conn.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0]
    conn.close()
    error = request.args.get("error", "").strip()[:250]
    notice = request.args.get("notice", "").strip()[:250]
    return render_template(
        "admin.html", subjects=subjects, documents=documents, student_count=count,
        page="admin", admin_view=admin_view,
        csrf_token=admin_form_token(), error=error,
        notice=notice, upload_max_mb=MAX_UPLOAD_MB
    )


@app.route("/admin/subjects", methods=["POST"])
@admin_required
def admin_add_subject():
    if not admin_csrf_valid():
        return "Phiên biểu mẫu không hợp lệ. Hãy tải lại trang quản trị.", 400
    code = re.sub(r"\s+", "", request.form.get("code", "")).upper()[:50]
    name = request.form.get("name", "").strip()[:180]
    description = request.form.get("description", "").strip()[:900]
    if not code or not name:
        return redirect(url_for("admin_dashboard", error="Vui lòng nhập mã môn và tên môn."))
    key = _normalize_subject_key(code, name)
    conn = db()
    existing = conn.execute(
        "SELECT id FROM shared_subjects WHERE subject_key=?", (key,)
    ).fetchone()
    timestamp = now()
    if existing:
        conn.execute(
            "UPDATE shared_subjects SET code=?,name=?,description=?,admin_managed=1,updated_at=? WHERE id=?",
            (code, name, description, timestamp, existing["id"])
        )
        notice = "Đã cập nhật môn học dùng chung."
    else:
        conn.execute(
            """INSERT INTO shared_subjects(
                subject_key,code,name,description,syllabus_text,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (key, code, name, description, "", timestamp, timestamp)
        )
        notice = "Đã tạo môn học dùng chung."
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard", notice=notice))


@app.route("/admin/subjects/<int:subject_id>/edit", methods=["POST"])
@admin_required
def admin_edit_subject(subject_id):
    """Update the common course code/name without modifying student-owned courses."""
    if not admin_csrf_valid():
        return "Phiên biểu mẫu không hợp lệ. Hãy tải lại trang quản trị.", 400
    code = re.sub(r"\s+", "", request.form.get("code", "")).upper()[:50]
    name = request.form.get("name", "").strip()[:180]
    description = request.form.get("description", "").strip()[:900]
    if not code or not name:
        return redirect(url_for(
            "admin_dashboard", error="Mã môn và tên môn không được để trống."
        ))

    conn = db()
    try:
        original = conn.execute(
            "SELECT id,subject_key FROM shared_subjects WHERE id=? AND admin_managed=1", (subject_id,)
        ).fetchone()
        if not original:
            return "Không tìm thấy môn học chung.", 404

        new_key = _normalize_subject_key(code, name)
        collision = conn.execute(
            "SELECT id FROM shared_subjects WHERE subject_key=? AND id<>?",
            (new_key, subject_id)
        ).fetchone()
        if collision:
            return redirect(url_for(
                "admin_dashboard",
                error="Mã môn này đã được dùng bởi một môn khác. Vui lòng chọn mã khác."
            ))

        conn.execute(
            """UPDATE shared_subjects
               SET subject_key=?,code=?,name=?,description=?,updated_at=?
               WHERE id=?""",
            (new_key, code, name, description, now(), subject_id)
        )
        if new_key != original["subject_key"]:
            # Personal subjects keep their original code, notes and files.
            # Unlink old-code enrollments; new-code enrollments are resolved by
            # ensure_shared_subject_for_user_subject on their next request.
            conn.execute(
                "UPDATE subjects SET shared_subject_id=NULL WHERE shared_subject_id=?",
                (subject_id,)
            )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return redirect(url_for(
            "admin_dashboard", error="Mã môn đã tồn tại. Không thể lưu thay đổi."
        ))
    finally:
        conn.close()
    return redirect(url_for(
        "admin_dashboard", notice="Đã cập nhật mã môn và tên môn học chung."
    ))


@app.route("/admin/subjects/<int:subject_id>/delete", methods=["POST"])
@admin_required
def admin_delete_subject(subject_id):
    """Delete the common catalog entry and its materials, never student data."""
    if not admin_csrf_valid():
        return "Phiên biểu mẫu không hợp lệ. Hãy tải lại trang quản trị.", 400

    conn = db()
    uploaded_files = []
    try:
        subject = conn.execute(
            "SELECT id,code FROM shared_subjects WHERE id=? AND admin_managed=1", (subject_id,)
        ).fetchone()
        if not subject:
            return "Không tìm thấy môn học chung.", 404

        if request.form.get("confirm_code", "").strip() != (subject["code"] or ""):
            return "Mã môn xác nhận xóa không hợp lệ.", 400

        uploaded_files = [
            row["stored_name"] for row in conn.execute(
                "SELECT stored_name FROM shared_documents WHERE shared_subject_id=?",
                (subject_id,)
            ).fetchall()
        ]
        # Preserve ALL student-owned subjects, personal PDFs, quizzes, plans,
        # weaknesses and learning progress; only their shared catalog link goes.
        conn.execute(
            "UPDATE subjects SET shared_subject_id=NULL WHERE shared_subject_id=?",
            (subject_id,)
        )
        conn.execute("DELETE FROM shared_subjects WHERE id=?", (subject_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    for filename in uploaded_files:
        (UPLOAD_DIR / filename).unlink(missing_ok=True)

    return redirect(url_for(
        "admin_dashboard",
        notice="Đã xóa môn học và tài liệu chung. Dữ liệu cá nhân của sinh viên vẫn được giữ nguyên."
    ))


@app.route("/admin/documents", methods=["POST"])
@admin_required
def admin_add_document():
    if not admin_csrf_valid():
        return "Phiên biểu mẫu không hợp lệ. Hãy tải lại trang quản trị.", 400
    subject_id = request.form.get("shared_subject_id", type=int)
    upload = request.files.get("file")
    if not subject_id or not upload or not upload.filename or not allowed_file(upload.filename):
        return redirect(url_for(
            "admin_shared_documents", error="Chọn môn và tệp PDF, TXT hoặc MD hợp lệ."
        ))
    original = os.path.basename(upload.filename.replace("\\", "/")).strip()[:180]
    safe = secure_filename(original)
    if not safe:
        return redirect(url_for(
            "admin_shared_documents", error="Tên tệp không hợp lệ."
        ))
    conn = db()
    shared_subject = conn.execute(
        "SELECT id FROM shared_subjects WHERE id=? AND admin_managed=1", (subject_id,)
    ).fetchone()
    if not shared_subject:
        conn.close()
        return redirect(url_for(
            "admin_shared_documents", error="Môn học dùng chung không tồn tại."
        ))
    stored = "shared_" + secrets.token_hex(12) + "_" + safe
    target = UPLOAD_DIR / stored
    is_syllabus = request.form.get("is_syllabus") == "1"
    try:
        upload.save(target)
        extracted = extract_text(target)
        if not extracted.strip():
            target.unlink(missing_ok=True)
            conn.close()
            return redirect(url_for(
                "admin_shared_documents",
                error="Tệp không trích xuất được chữ. PDF scan ảnh cần OCR trước khi tải."
            ))
        if is_syllabus:
            # Do not let a per-chapter slide replace the whole shared syllabus.
            # Academic modules vary, so this is a minimum safety heuristic, not
            # a claim that all valid academic syllabi have the same format.
            from syllabus_learning import extract_syllabus_units
            chapters = extract_syllabus_units(extracted)
            distinct_chapters = {item["evidence"].casefold() for item in chapters}
            # Older subjects may legitimately use a short, unstructured
            # outline (e.g. "Đề cương Điện toán đám mây: ..."). Do not break
            # this established upload contract merely because no numbered
            # chapter headings exist. Still reject chapter-only lecture slides.
            is_course_outline = bool(re.search(
                r"(?i)\b(?:đề cương(?: chi tiết)?|mục tiêu học phần|"
                r"chuẩn đầu ra(?: học phần)?|course syllabus|course outline)\b",
                extracted
            ))
            if len(distinct_chapters) < 2 and not is_course_outline:
                target.unlink(missing_ok=True)
                return redirect(url_for(
                    "admin_shared_documents",
                    error=(
                        "File này chưa có ít nhất 2 tiêu đề chương/bài có thể nhận diện "
                        "hoặc nội dung thể hiện đây là đề cương học phần. "
                        "Không thay thế đề cương chuẩn. Nếu đây là slide/bài tập một chương, "
                        "hãy upload không đánh dấu 'Đặt làm đề cương chuẩn của môn'."
                    )
                ))
        timestamp = now()
        cur = conn.execute(
            """INSERT INTO shared_knowledge(
                shared_subject_id,title,content,source_type,created_by_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?)""",
            (subject_id, original, extracted, "shared_document", session["user_id"],
             timestamp, timestamp)
        )
        knowledge_id = cur.lastrowid
        conn.execute(
            """INSERT INTO shared_documents(
                shared_subject_id,original_name,stored_name,extracted_text,
                knowledge_id,is_syllabus,created_by_user_id,created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (subject_id, original, stored, extracted, knowledge_id,
             int(is_syllabus), session["user_id"], timestamp)
        )
        if is_syllabus:
            # Only one official syllabus per course; newest admin upload wins.
            conn.execute(
                "UPDATE shared_documents SET is_syllabus=0 "
                "WHERE shared_subject_id=? AND stored_name<>?",
                (subject_id, stored)
            )
            conn.execute(
                "UPDATE shared_subjects SET syllabus_text=?,updated_at=? WHERE id=?",
                (extracted[:20000], timestamp, subject_id)
            )
        else:
            conn.execute(
                "UPDATE shared_subjects SET updated_at=? WHERE id=?",
                (timestamp, subject_id)
            )
        conn.commit()
    except Exception:
        conn.rollback()
        target.unlink(missing_ok=True)
        raise
    finally:
        # Avoid leaking handles if file extraction or SQLite insert fails.
        try:
            conn.close()
        except Exception:
            pass
    return redirect(url_for(
        "admin_shared_documents",
        notice="Đã lưu và trích xuất nội dung tài liệu dùng chung."
    ))


@app.route("/admin/documents/<int:doc_id>/delete", methods=["POST"])
@admin_required
def admin_delete_document(doc_id):
    if not admin_csrf_valid():
        return "Phiên biểu mẫu không hợp lệ. Hãy tải lại trang quản trị.", 400
    conn = db()
    doc = conn.execute(
        "SELECT * FROM shared_documents WHERE id=?", (doc_id,)
    ).fetchone()
    if not doc:
        conn.close()
        return "Không tìm thấy tài liệu.", 404
    conn.execute("DELETE FROM shared_documents WHERE id=?", (doc_id,))
    if doc["knowledge_id"]:
        conn.execute("DELETE FROM shared_knowledge WHERE id=?", (doc["knowledge_id"],))
    if doc["is_syllabus"]:
        # Shared syllabus fallback: reset rather than serve deleted content.
        conn.execute(
            "UPDATE shared_subjects SET syllabus_text='',updated_at=? WHERE id=?",
            (now(), doc["shared_subject_id"])
        )
    conn.commit()
    conn.close()
    (UPLOAD_DIR / doc["stored_name"]).unlink(missing_ok=True)
    return redirect(url_for(
        "admin_shared_documents", notice="Đã xóa tài liệu dùng chung."
    ))


@app.route("/shared-documents/<int:doc_id>/file")
@login_required
def shared_document_file(doc_id):
    conn = db()
    document = conn.execute(
        "SELECT * FROM shared_documents WHERE id=?", (doc_id,)
    ).fetchone()
    if not document:
        conn.close()
        return "Không tìm thấy tài liệu.", 404

    account = conn.execute(
        "SELECT role FROM users WHERE id=?", (session["user_id"],)
    ).fetchone()
    authorized = bool(account and account["role"] == "admin")
    if not authorized:
        # A student may read common files ONLY for their own registered course.
        subjects = conn.execute(
            "SELECT id FROM subjects WHERE user_id=?", (session["user_id"],)
        ).fetchall()
        for item in subjects:
            ensure_shared_subject_for_user_subject(conn, session["user_id"], item["id"])
        authorized = bool(conn.execute(
            "SELECT id FROM subjects WHERE user_id=? AND shared_subject_id=? LIMIT 1",
            (session["user_id"], document["shared_subject_id"])
        ).fetchone())
    conn.close()
    if not authorized:
        return "Không có quyền xem tài liệu của môn học này.", 403
    return send_from_directory(
        UPLOAD_DIR, document["stored_name"],
        as_attachment=False, download_name=document["original_name"]
    )


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

    # Resolve current code -> shared subject linkage for older student accounts too.
    # This makes an admin upload visible on the very next student page request.
    shared_subject_names = {}
    for student_subject in subs:
        common = ensure_shared_subject_for_user_subject(conn, uid, student_subject["id"])
        if common:
            shared_subject_names[common["id"]] = student_subject["name"]

    shared_docs = []
    if shared_subject_names:
        placeholders = ",".join("?" for _ in shared_subject_names)
        shared_docs = conn.execute(
            f"""SELECT sd.id,sd.original_name,sd.created_at,sd.is_syllabus,
                       sd.shared_subject_id,ss.code,ss.name AS shared_subject_name
                FROM shared_documents sd
                JOIN shared_subjects ss ON ss.id=sd.shared_subject_id
                WHERE sd.shared_subject_id IN ({placeholders})
                ORDER BY sd.id DESC""",
            tuple(shared_subject_names.keys())
        ).fetchall()

    extracted_count = sum(
        1 for row in docs
        if (row["extracted_text"] or "").strip()
    )
    total_bytes = 0
    for row in docs:
        try:
            path = UPLOAD_DIR / row["stored_name"]
            if path.exists():
                total_bytes += path.stat().st_size
        except OSError:
            pass

    extraction_percent = (
        round((extracted_count / len(docs)) * 100)
        if docs else 0
    )
    storage_mb = round(total_bytes / (1024 * 1024), 2)

    conn.close()
    return render_template(
        "documents.html",
        page="documents",
        documents=docs,
        subjects=subs,
        extracted_count=extracted_count,
        extraction_percent=extraction_percent,
        storage_mb=storage_mb,
        shared_documents=shared_docs,
        upload_max_mb=MAX_UPLOAD_MB,
        upload_error=request.args.get("upload_error") == "too_large"
    )


@app.route("/documents/<int:doc_id>/summary")
@login_required
def document_summary(doc_id):
    uid = session["user_id"]
    conn = db()
    row = conn.execute(
        """
        SELECT d.*, s.name AS subject_name
        FROM documents d
        LEFT JOIN subjects s
          ON s.id=d.subject_id AND s.user_id=d.user_id
        WHERE d.id=? AND d.user_id=?
        """,
        (doc_id, uid)
    ).fetchone()
    conn.close()

    if not row:
        return redirect(url_for("documents"))

    source_text = (row["extracted_text"] or "").strip()
    if not source_text:
        summary = (
            "Không trích xuất được nội dung chữ từ tài liệu này. "
            "Nếu đây là PDF scan/ảnh, hệ thống hiện chưa OCR."
        )
        used_ai = False
        ai_error = ""
    else:
        prompt = f"""
Bạn là AI Study Agent.
Hãy tóm tắt tài liệu học tập dưới đây bằng tiếng Việt để sinh viên ôn nhanh.

Yêu cầu:
- Chỉ dùng thông tin có trong tài liệu.
- Giữ đúng thuật ngữ của tài liệu.
- Chia thành: Ý chính, Khái niệm quan trọng, Nội dung cần nhớ.
- Ngắn gọn nhưng đủ ý; không bịa thêm kiến thức ngoài tài liệu.
- Nếu tài liệu có chương/mục rõ ràng, giữ cấu trúc đó khi hợp lý.

TÀI LIỆU:
{source_text[:14000]}
""".strip()

        generated, ai_error = gemini_generate(prompt)
        if generated:
            summary = generated.strip()
            used_ai = True
        else:
            # Fallback cục bộ để nút "Tóm tắt" vẫn có ích khi API tạm lỗi.
            chunks = [
                part.strip()
                for part in re.split(r"\n{2,}|(?<=[.!?])\s+", source_text)
                if len(part.strip()) >= 25
            ]
            summary = "\n\n".join(chunks[:12])[:3500]
            if not summary:
                summary = source_text[:3500]
            used_ai = False

    return render_template(
        "document_summary.html",
        page="documents",
        document=row,
        summary=summary,
        used_ai=used_ai,
        ai_error=ai_error or ""
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

        if old_subject_id and old_subject_id != new_subject_id:
            conn.execute(
                """
                UPDATE subjects
                SET personal_syllabus_document_id=NULL
                WHERE id=? AND user_id=?
                  AND personal_syllabus_document_id=?
                """,
                (old_subject_id, uid, doc_id)
            )

        # Quiz sinh từ tài liệu phải luôn đi theo môn của tài liệu.
        conn.execute(
            "UPDATE quizzes SET subject_id=? WHERE document_id=? AND user_id=?",
            (new_subject_id, doc_id, uid)
        )

        # Quiz sinh từ tài liệu đổi môn: chuyển cả tín hiệu học tương ứng.
        for affected_id in {old_subject_id, new_subject_id} - {None}:
            rebuild_subject_learning_signals(conn, uid, affected_id)

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
            SELECT id,subject_id
            FROM quizzes
            WHERE user_id=?
              AND (
                    document_id=?
                    OR (document_id IS NULL AND title=?)
                  )
            """,
            (uid, doc_id, f"Quiz từ {row['original_name']}")
        ).fetchall()
        affected_subject_ids = {subject_id} | {
            quiz_row["subject_id"] for quiz_row in quiz_rows
        }

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
            """
            UPDATE subjects
            SET personal_syllabus_document_id=NULL
            WHERE user_id=? AND personal_syllabus_document_id=?
            """,
            (uid, doc_id)
        )

        conn.execute(
            "DELETE FROM documents WHERE id=? AND user_id=?",
            (doc_id, uid)
        )

        for affected_id in affected_subject_ids - {None}:
            rebuild_subject_learning_signals(conn, uid, affected_id)

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
    methods=["GET"]
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

    # Student API is read-only. Shared academic content is consumed here,
    # while management is reserved for a future lecturer/admin role.
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
        "knowledge": [dict(row) for row in knowledge_rows],
        "read_only": True,
        "scope": "shared_academic_knowledge",
        "managed_by": "lecturer_or_academic_admin_future"
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
        SELECT id,topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
          AND miss_count > correct_count
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

    adaptive_task = conn.execute(
        """
        SELECT id,title,study_at,duration,note,source
        FROM study_tasks
        WHERE user_id=? AND subject_id=?
          AND source='adaptive' AND done=0
        ORDER BY study_at ASC,id DESC
        LIMIT 1
        """,
        (uid, subject_id)
    ).fetchone()

    mastery_stats = conn.execute(
        """
        SELECT
            SUM(CASE WHEN miss_count > correct_count THEN 1 ELSE 0 END) AS active_count,
            SUM(CASE WHEN miss_count <= correct_count THEN 1 ELSE 0 END) AS mastered_count
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
        """,
        (uid, subject_id)
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
        "weaknesses": [dict(row) for row in weaknesses],
        "adaptive_task": dict(adaptive_task) if adaptive_task else None,
        "mastery": {
            "active_count": int(mastery_stats["active_count"] or 0),
            "mastered_count": int(mastery_stats["mastered_count"] or 0)
        }
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


@app.route("/api/chat/course-outline", methods=["GET"])
@login_required
def api_chat_course_outline():
    """Read-only chapter choices for the current student's course."""
    from chapter_chat_context import LessonContextError, list_chapter_options
    try:
        subject_id = int(request.args.get("subject_id"))
    except (ValueError, TypeError):
        return jsonify({"error": "Hãy chọn một môn học hợp lệ."}), 400
    conn = db()
    try:
        result = list_chapter_options(
            sys.modules[__name__], conn, session["user_id"], subject_id
        )
    except LessonContextError as exc:
        return jsonify({"error": exc.message}), exc.status
    finally:
        conn.close()
    return jsonify(result)


@app.route("/api/chat/lesson-context", methods=["GET"])
@login_required
def api_chat_lesson_context():
    """Validate chapter launch parameters before displaying lesson mode."""
    from chapter_chat_context import LessonContextError, resolve_lesson_context
    try:
        subject_id = int(request.args.get("subject_id"))
        chapter_number = int(request.args.get("chapter_number"))
        topic_value = request.args.get("topic_index")
        topic_index = int(topic_value) if topic_value not in (None, "") else None
    except (ValueError, TypeError):
        return jsonify({"error": "Thiếu mã môn hoặc chương hợp lệ."}), 400
    conn = db()
    try:
        context = resolve_lesson_context(
            sys.modules[__name__], conn, session["user_id"],
            subject_id, chapter_number, topic_index
        )
    except LessonContextError as exc:
        return jsonify({"error": exc.message}), exc.status
    finally:
        conn.close()
    return jsonify({
        "subject_id": context["subject_id"],
        "subject_name": context["subject_name"],
        "chapter_number": context["chapter_number"],
        "chapter": context["chapter"],
        "topic_index": context["topic_index"],
        "topic": context["topic"],
        "topics": context["topics"],
        "source_names": list(dict.fromkeys(
            src["name"] for src in context["sources"]
        ))
    })


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

    subject_id = conversation["subject_id"]
    subject_name = conversation["subject_name"]
    lesson_context = None
    personal_context = ""
    shared_sources = []

    # A lesson launch is still the EXISTING per-subject Chat AI conversation,
    # but its source scope must be enforced server-side on every message.
    requested_lesson = payload.get("lesson")
    if requested_lesson is not None:
        if not isinstance(requested_lesson, dict):
            conn.close()
            return jsonify({"error": "Ngữ cảnh chương không hợp lệ."}), 400
        from chapter_tutor import MAX_QUESTION_CHARS
        if len(question) > MAX_QUESTION_CHARS:
            conn.close()
            return jsonify({
                "error": f"Câu hỏi học theo chương không được quá {MAX_QUESTION_CHARS} ký tự."
            }), 400
        try:
            chapter_number = int(requested_lesson.get("chapter_number"))
            topic_value = requested_lesson.get("topic_index")
            topic_index = int(topic_value) if topic_value not in (None, "") else None
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "Chương hoặc tiểu mục không hợp lệ."}), 400
        from chapter_chat_context import LessonContextError, resolve_lesson_context
        try:
            if "task_id" in requested_lesson:
                # An in-room request must be validated against the *saved* task,
                # course ownership and current roadmap signature on each send.
                if topic_index is not None:
                    raise LessonContextError(
                        "Chat theo buổi tự dùng các tiểu mục của chính buổi học.", 400
                    )
                raw_task_id = requested_lesson["task_id"]
                if isinstance(raw_task_id, bool) or not str(raw_task_id).isdigit():
                    raise LessonContextError("Mã buổi học không hợp lệ.", 400)
                from study_session_chat_context import validated_session_chat
                lesson_context = validated_session_chat(
                    sys.modules[__name__], conn, uid, int(raw_task_id), question=question
                )
                if (lesson_context["subject_id"] != subject_id or
                        lesson_context["chapter_number"] != chapter_number):
                    raise LessonContextError("Buổi học không thuộc môn/chương đã chọn.", 404)
            else:
                lesson_context = resolve_lesson_context(
                    sys.modules[__name__], conn, uid, subject_id,
                    chapter_number, topic_index, question=question
                )
        except LessonContextError as exc:
            conn.close()
            return jsonify({"error": exc.message}), exc.status

    # Keep one visible Chat AI history per subject, but only pass back recent
    # turns from the SAME mode, chapter, topic, and approved source version.
    # Previous free-chat and other chapter content must not become evidence.
    from chat_lesson_memory import history_for_mode, save_message_context
    history_rows = history_for_mode(
        conn, uid, conversation_id, lesson_context
    )
    conversation_history = "\n".join(
        f"{'Bạn' if row['role']=='user' else 'AI'}: {row['content']}"
        for row in history_rows
    )
    conn.close()

    if lesson_context:
        from chapter_tutor import make_tutor_prompt, parse_tutor_answer
        personal_context = get_personal_learning_context(uid, subject_id)
        session_scope = ""
        if lesson_context.get("session_task_id"):
            session_scope = (
                "BUỔI ĐANG HỌC: " + lesson_context["session_title"] + "\n"
                "CHỈ GIẢNG CÁC TIỂU MỤC CỦA BUỔI: " +
                "; ".join(lesson_context["session_topics"])[:800] + "\n"
                "MỤC TIÊU CỦA BUỔI: " +
                "; ".join(lesson_context["session_objectives"])[:500] + "\n"
                "HOẠT ĐỘNG DỰ KIẾN: " +
                "; ".join(lesson_context["session_activities"])[:500] + "\n"
                "Nếu câu hỏi nằm ngoài phạm vi buổi này, hãy nêu rõ và gợi ý "
                "quay về nội dung đang học. Không lấy nội dung của các buổi "
                "khác làm nội dung được giao trong buổi này."
            )
        prompt = make_tutor_prompt(
            subject_name, lesson_context["chapter"],
            ("; ".join(lesson_context["session_topics"])
             if lesson_context.get("session_task_id") else
             ("; ".join(lesson_context["topics"])
              if lesson_context["topic_index"] is None else lesson_context["topic"])),
            question, lesson_context["sources"], conversation_history,
            profile=personal_context, session_scope=session_scope
        )
        raw, ai_error = gemini_generate(prompt)
        tutored = parse_tutor_answer(raw, lesson_context["sources"]) if raw else None
        if not tutored:
            return jsonify({
                "error": ("AI chưa trả được câu trả lời có dẫn chứng kiểm chứng "
                          "được trong học liệu đã duyệt. Hãy thử hỏi lại.")
            }), 502
        # Persist a readable, sourced response in the EXISTING chat history.
        quotes = "\n".join(
            f'[{item["source_key"]}] {item["source_name"]}: “{item["quote"]}”'
            for item in tutored["citations"]
        )
        answer = tutored["explanation"]
        if tutored["practice"]:
            answer += "\n\nTự luyện: " + tutored["practice"]
        answer += "\n\nDẫn chứng từ học liệu đã duyệt:\n" + quotes
        used_sources = list(dict.fromkeys(
            item["source_name"] for item in tutored["citations"]
        ))
        source_mode = "chapter"
    else:
        context, candidate_sources = get_subject_context(
            uid, subject_id, question
        )
        shared_context, shared_sources = get_shared_subject_context(
            uid, subject_id, question
        )
        personal_context = get_personal_learning_context(uid, subject_id)
        answer, used_sources, source_mode = gemini_subject_answer(
            subject_name, question, context, candidate_sources,
            conversation_history, shared_context, personal_context,
            shared_sources
        )

    conn = db()
    if lesson_context:
        # Admin may revoke/replace a source while the AI is generating.
        # Never persist or return a chapter answer for an outdated approval.
        from chapter_chat_context import LessonContextError, resolve_lesson_context
        try:
            if lesson_context.get("session_task_id"):
                from study_session_chat_context import validated_session_chat
                live = validated_session_chat(
                    sys.modules[__name__], conn, uid,
                    lesson_context["session_task_id"], question=question
                )
            else:
                live = resolve_lesson_context(
                    sys.modules[__name__], conn, uid, subject_id,
                    lesson_context["chapter_number"], lesson_context["topic_index"],
                    question=question
                )
        except LessonContextError:
            conn.close()
            return jsonify({
                "error": "Học liệu hoặc đề cương đã thay đổi. Hãy tải lại chương trước khi hỏi tiếp."
            }), 409
        if live["source_signature"] != lesson_context["source_signature"]:
            conn.close()
            return jsonify({
                "error": "Học liệu chương đã được cập nhật. Hãy tải lại trước khi tiếp tục."
            }), 409
    created_at = now()

    user_message = conn.execute(
        """
        INSERT INTO chat_messages(
            user_id,conversation_id,role,content,created_at
        ) VALUES(?,?,?,?,?)
        """,
        (uid, conversation_id, "user", question, created_at)
    )
    save_message_context(
        conn, user_message.lastrowid, uid, conversation_id, lesson_context
    )
    assistant_message = conn.execute(
        """
        INSERT INTO chat_messages(
            user_id,conversation_id,role,content,created_at
        ) VALUES(?,?,?,?,?)
        """,
        (uid, conversation_id, "assistant", answer, now())
    )
    save_message_context(
        conn, assistant_message.lastrowid, uid, conversation_id, lesson_context
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
        "lesson": ({
            "chapter_number": lesson_context["chapter_number"],
            "topic_index": lesson_context["topic_index"],
            "session_task_id": lesson_context.get("session_task_id"),
            "chapter": lesson_context["chapter"],
            "topic": lesson_context["topic"],
            "topics": lesson_context["topics"],
        } if lesson_context else None),
        "updated_at": updated_at
    })


@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    uid = session["user_id"]
    conn = db()

    # =====================================================
    # TẠO QUIZ MỚI: TÀI LIỆU / MÔN HỌC / ÔN ĐIỂM YẾU
    # =====================================================
    if request.method == "POST":
        mode = (request.form.get("quiz_mode") or "document").strip().lower()

        try:
            question_count = int(request.form.get("question_count", 10))
        except (TypeError, ValueError):
            question_count = 10

        if question_count not in (10, 20, 30):
            question_count = 10

        questions = []
        subject_id = None
        document_id = None
        title = "Quiz luyện tập"

        if mode == "document":
            doc_id = request.form.get("document_id")
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
                subject_id = doc["subject_id"]
                document_id = doc["id"]
                title = f"Quiz từ {doc['original_name']}"

        elif mode in {"subject", "weakness"}:
            subject_id = owned_subject_id(
                conn,
                uid,
                request.form.get("subject_id")
            )

            subject = None
            if subject_id:
                subject = conn.execute(
                    """
                    SELECT id,name
                    FROM subjects
                    WHERE id=? AND user_id=?
                    """,
                    (subject_id, uid)
                ).fetchone()

            if subject:
                backbone = get_course_learning_backbone(
                    conn,
                    uid,
                    subject_id,
                    query=""
                )

                context_parts = []
                if backbone and backbone["syllabus_text"]:
                    syllabus_label = (
                        "ĐỀ CƯƠNG CHUẨN CỦA MÔN"
                        if backbone["syllabus_source"] == "shared"
                        else "ĐỀ CƯƠNG CÁ NHÂN FALLBACK"
                    )
                    context_parts.append(
                        f"{syllabus_label}:\n"
                        f"{backbone['syllabus_text'][:9000]}"
                    )

                if backbone and backbone["shared_context"]:
                    context_parts.append(
                        "KIẾN THỨC DÙNG CHUNG BỔ TRỢ:\n"
                        + backbone["shared_context"][:5500]
                    )

                if backbone and backbone["personal_context"]:
                    context_parts.append(
                        "TÀI LIỆU CÁ NHÂN BỔ TRỢ:\n"
                        + backbone["personal_context"][:7500]
                    )

                # Thứ tự trên là có chủ đích: syllabus luôn đứng đầu context,
                # nên không bị cắt mất khi môn có nhiều tài liệu.
                combined_context = "\n\n".join(context_parts)[:22000]

                focus_topics = []
                if mode == "weakness":
                    weakness_rows = conn.execute(
                        """
                        SELECT topic,chapter,miss_count,correct_count
                        FROM learning_weaknesses
                        WHERE user_id=? AND subject_id=? AND miss_count > correct_count
                        ORDER BY (miss_count - correct_count * 0.5) DESC,
                                 last_seen_at DESC
                        LIMIT 8
                        """,
                        (uid, subject_id)
                    ).fetchall()
                    focus_topics = [dict(row) for row in weakness_rows]

                    # Nếu chưa có weakness thì không tạo quiz giả vờ cá nhân hóa.
                    if not focus_topics:
                        conn.close()
                        return redirect(url_for("quiz"))

                if combined_context:
                    questions = build_quiz(
                        combined_context,
                        question_count,
                        focus_topics=focus_topics
                    )

                    if mode == "weakness":
                        title = f"Ôn điểm yếu · {subject['name']}"
                    else:
                        title = f"Quiz môn {subject['name']}"

        if questions:
            cursor = conn.execute(
                """
                INSERT INTO quizzes(
                    user_id,subject_id,document_id,title,payload,created_at
                )
                VALUES(?,?,?,?,?,?)
                """,
                (
                    uid,
                    subject_id,
                    document_id,
                    title,
                    json.dumps(questions, ensure_ascii=False),
                    now()
                )
            )
            if mode == "weakness" and subject_id:
                from quiz_review_progress import save_review_baseline
                save_review_baseline(conn, uid, subject_id, cursor.lastrowid, now())
            conn.commit()

        conn.close()
        if not questions:
            return redirect(url_for(
                "quiz",
                generation_error="Không tạo đủ câu hỏi hợp lệ. Kiểm tra tài liệu và kết nối Gemini rồi thử lại."
            ))
        return redirect(url_for("quiz"))

    # =====================================================
    # DỮ LIỆU TRANG QUIZ
    # =====================================================
    from study_session_quiz import get_session_quiz_context, public_session_quiz_context
    from study_session_quiz_runtime import (
        ensure_quiz_runtime_schema, context_for_task, saved_quiz, quiz_access,
    )
    from chapter_chat_context import LessonContextError
    ensure_quiz_runtime_schema(conn)
    session_quiz_context = None
    session_quiz_status = None
    if not session.get("session_quiz_csrf"):
        session["session_quiz_csrf"] = secrets.token_hex(24)
    requested_task = request.args.get('task_id')
    if requested_task is not None:
        try:
            task_number = int(requested_task)
            if task_number <= 0:
                raise ValueError('Invalid session')
        except (ValueError, TypeError):
            conn.close()
            return 'Mã buổi học không hợp lệ.', 400
        try:
            verified = get_session_quiz_context(sys.modules[__name__], conn, uid, task_number)
            session_quiz_context = public_session_quiz_context(verified)
            # Final examination can use approved earlier sessions even if
            # the final review slot has no standalone approved document.
            try:
                scoped, previous, total = context_for_task(
                    sys.modules[__name__], conn, uid, task_number
                )
                existing = saved_quiz(conn, uid, task_number,
                                      scoped["source_signature"])
                session_quiz_context["ready"] = bool(scoped["ready"])
                if previous:
                    session_quiz_context["source_names"] = scoped["source_names"]
                if existing:
                    access = quiz_access(conn, sys.modules[__name__], uid,
                                         existing["id"])
                    session_quiz_status = {
                        "quiz_id": existing["id"], "count": total,
                        "allowed": access["allowed"],
                        "review_unlocked": access.get("review_unlocked", False),
                        "can_start": access.get("can_start", False),
                        "study_at": access.get("study_at", ""),
                        "ends_at": access.get("ends_at", ""),
                        "reason": access.get("reason", ""),
                    }
                else:
                    session_quiz_status = {"quiz_id": None, "count": total}
            except LessonContextError as error:
                session_quiz_context["ready"] = False
                session_quiz_context["reason"] = error.message
        except LessonContextError as error:
            conn.close()
            return error.message, error.status
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

    subjects = conn.execute(
        """
        SELECT
            s.*,
            COUNT(DISTINCT lw.id) AS weakness_count
        FROM subjects s
        LEFT JOIN learning_weaknesses lw
          ON lw.subject_id=s.id
         AND lw.user_id=s.user_id
         AND lw.miss_count > lw.correct_count
        WHERE s.user_id=?
        GROUP BY s.id
        ORDER BY s.name ASC
        """,
        (uid,)
    ).fetchall()

    quizzes = conn.execute(
        """
        SELECT
            q.*,
            qsl.session_title AS linked_session_title,
            qsl.chapter_number AS linked_chapter_number,
            qsl.quiz_id AS linked_quiz_id,
            COUNT(qa.id) AS attempt_count,
            MAX(qa.created_at) AS last_attempt_at,
            MAX(qa.score) AS best_score
        FROM quizzes q
        LEFT JOIN quiz_session_links qsl
          ON qsl.quiz_id=q.id AND qsl.user_id=q.user_id
        LEFT JOIN quiz_attempts qa
          ON qa.quiz_id=q.id
         AND qa.user_id=q.user_id
        WHERE q.user_id=?
        GROUP BY q.id
        ORDER BY q.id DESC
        """,
        (uid,)
    ).fetchall()

    parsed = []
    for q in quizzes:
        # Never send questions for a locked session Quiz to Jinja/HTML.
        if q["linked_quiz_id"]:
            access = quiz_access(conn, sys.modules[__name__], uid, q["id"])
            if not access["allowed"]:
                continue
        item = dict(q)
        try:
            item["questions"] = json.loads(q["payload"])
        except (json.JSONDecodeError, TypeError):
            item["questions"] = []
        item["attempted"] = int(q["attempt_count"] or 0) > 0
        parsed.append(item)
    conn.close()
    active_session_quiz_id = (
        session_quiz_status["quiz_id"] if session_quiz_status
        and session_quiz_status.get("allowed") else None
    )
    active_quiz_id = (active_session_quiz_id or
                      (parsed[0]["id"] if parsed else None))

    selected_document_id = request.args.get("document_id", type=int)
    selected_subject_id = request.args.get("subject_id", type=int)
    if selected_subject_id:
        subject_check_conn = db()
        selected_subject_id = owned_subject_id(
            subject_check_conn,
            uid,
            selected_subject_id
        )
        subject_check_conn.close()

    if session_quiz_context:
        selected_subject_id = session_quiz_context['subject_id']
    selected_quiz_mode = (request.args.get("mode") or "").strip().lower()
    if selected_quiz_mode not in {"subject", "document", "weakness"}:
        selected_quiz_mode = "document" if selected_document_id else "subject"

    return render_template(
        "quiz.html",
        page="quiz",
        documents=docs,
        subjects=subjects,
        quizzes=parsed,
        selected_document_id=selected_document_id,
        selected_subject_id=selected_subject_id,
        selected_quiz_mode=selected_quiz_mode,
        session_quiz_context=session_quiz_context,
        session_quiz_status=session_quiz_status,
        session_quiz_csrf=session.get('session_quiz_csrf', ''),
        active_quiz_id=active_quiz_id,
        generation_error=request.args.get("generation_error", "").strip()[:240]
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
        rebuild_subject_learning_signals(conn, uid, quiz_row["subject_id"])

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

    from study_session_quiz_runtime import quiz_access
    gate = quiz_access(conn, sys.modules[__name__], uid, quiz_id)
    if gate["linked"] and not gate["allowed"]:
        conn.close()
        return jsonify({"error": gate.get("reason", "Quiz đang khóa.")}), 409

    # Optional request id is generated per submit click by the Web client.
    # Retries of the same POST must NOT add another attempt/weakness signal.
    submission_key = payload.get("request_id")
    if submission_key is not None and (
        not isinstance(submission_key, str) or
        not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", submission_key)
    ):
        conn.close()
        return jsonify({"error": "Mã lần nộp không hợp lệ."}), 400
    if submission_key:
        from quiz_learning_analysis import ensure_quiz_submission_receipts
        # The profile creator commits on first use. Run it BEFORE locking
        # the graded attempt to keep Quiz/weakness/receipt atomic.
        if quiz_row["subject_id"]:
            ensure_learning_profile(conn, uid)
        ensure_quiz_submission_receipts(conn)
        conn.execute("BEGIN IMMEDIATE")
        submitted_before = conn.execute("""
            SELECT response_json FROM quiz_submission_receipts
            WHERE user_id=? AND quiz_id=? AND request_id=?
        """, (uid, quiz_id, submission_key)).fetchone()
        if submitted_before:
            response_copy = json.loads(submitted_before["response_json"])
            conn.rollback()
            conn.close()
            return jsonify(response_copy)

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

    if len(answers) != total_questions:
        conn.close()
        return jsonify({
            "error": "Vui lòng trả lời đầy đủ tất cả câu hỏi trước khi nộp."
        }), 400

    validated_answers = []
    for value in answers:
        try:
            selected_value = int(value)
        except (TypeError, ValueError):
            conn.close()
            return jsonify({
                "error": "Vui lòng trả lời đầy đủ tất cả câu hỏi trước khi nộp."
            }), 400

        if selected_value not in (0, 1, 2, 3):
            conn.close()
            return jsonify({
                "error": "Đáp án Quiz không hợp lệ."
            }), 400

        validated_answers.append(selected_value)

    answers = validated_answers
    correct_count = 0
    normalized_answers = []
    subject_id = quiz_row["subject_id"]

    active_before = (
        get_active_weakness_rows(conn, uid, subject_id, limit=100)
        if subject_id
        else []
    )
    active_before_map = {
        row["topic_key"]: {
            "topic": row["topic"],
            "chapter": row["chapter"]
        }
        for row in active_before
    }

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
            str(question.get("topic") or ""),
            str(question.get("chapter") or ""),
            is_correct,
            str(question.get("question") or "")
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

    subject_name = ""
    weaknesses = []
    weakness_count = 0
    resolved_topics = []
    new_weakness_topics = []
    adaptive_task = None

    if subject_id:
        subject_row = conn.execute(
            "SELECT name FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid)
        ).fetchone()
        subject_name = subject_row["name"] if subject_row else ""

        active_after_rows = get_active_weakness_rows(
            conn,
            uid,
            subject_id,
            limit=100
        )
        active_after_map = {
            row["topic_key"]: {
                "topic": row["topic"],
                "chapter": row["chapter"]
            }
            for row in active_after_rows
        }

        resolved_keys = [
            key for key in active_before_map
            if key not in active_after_map
        ]
        new_keys = [
            key for key in active_after_map
            if key not in active_before_map
        ]

        resolved_topics = [
            active_before_map[key]["topic"]
            for key in resolved_keys[:8]
        ]
        new_weakness_topics = [
            active_after_map[key]["topic"]
            for key in new_keys[:8]
        ]

        adaptive_task = sync_adaptive_review_task(
            conn,
            uid,
            subject_id
        )

        # Task thích nghi cũng là một phần của lộ trình, nên tính lại tiến độ
        # sau khi đồng bộ task để Dashboard/Kế hoạch phản ánh đúng trạng thái mới.
        recalculate_subject_progress(
            uid,
            subject_id,
            conn
        )

        weakness_rows = get_active_weakness_rows(
            conn,
            uid,
            subject_id,
            limit=8
        )
        weaknesses = [dict(row) for row in weakness_rows]
        # The UI shows only eight examples, but the total MUST count all
        # currently active weak topics (not just the preview rows).
        weakness_count = conn.execute("""
            SELECT COUNT(*) FROM learning_weaknesses
            WHERE user_id=? AND subject_id=? AND miss_count>correct_count
        """, (uid, subject_id)).fetchone()[0]

    attempt_stats = conn.execute(
        """
        SELECT COUNT(*) AS attempt_count, MAX(score) AS best_score
        FROM quiz_attempts
        WHERE user_id=? AND quiz_id=?
        """,
        (uid, quiz_id)
    ).fetchone()

    from quiz_learning_analysis import summarize_quiz_attempt
    from quiz_review_progress import compare_review_attempt
    analysis = summarize_quiz_attempt(questions, normalized_answers)
    review_comparison = compare_review_attempt(
        conn, uid, quiz_id, questions, normalized_answers)
    response_data = {
        "success": True,
        "attempt_id": attempt_id,
        "score": score,
        "correct_count": correct_count,
        "total_questions": total_questions,
        # Chỉ tiết lộ đáp án và lời giải sau khi server chấm bài.
        "correct_answers": [
            int(q.get("answer")) if str(q.get("answer", "")).isdigit() else -1
            for q in questions
        ],
        "explanations": [str(q.get("explanation") or "") for q in questions],
        "subject_id": subject_id,
        "subject_name": subject_name,
        "attempt_count": int(attempt_stats["attempt_count"] or 0),
        "best_score": float(attempt_stats["best_score"] or score),
        "weakness_count": weakness_count,
        "weaknesses": weaknesses,
        "new_weakness_topics": new_weakness_topics,
        "resolved_topics": resolved_topics,
        "adaptive_task": adaptive_task,
        "learning_updated": bool(subject_id),
        "adaptive_learning": bool(subject_id),
        "analysis": analysis,
        "review_comparison": review_comparison,
    }
    if submission_key:
        conn.execute("""
            INSERT INTO quiz_submission_receipts(
                user_id,quiz_id,request_id,attempt_id,response_json,created_at)
            VALUES(?,?,?,?,?,?)
        """, (uid, quiz_id, submission_key, attempt_id,
              json.dumps(response_data, ensure_ascii=False), now()))
    conn.commit()
    conn.close()
    return jsonify(response_data)


@app.route("/api/quiz/<int:quiz_id>/analysis", methods=["GET"])
@login_required
def quiz_attempt_analysis(quiz_id):
    """Read only the logged-in student's aggregated scored results.

    The JSON never contains the original question, options, submitted answer
    or answer key. Archived/locked Quiz payload is not disclosed.
    """
    uid = session["user_id"]
    from quiz_learning_analysis import analysis_for_saved_attempt
    conn = db()
    try:
        attempt_id = request.args.get("attempt_id", type=int)
        result = analysis_for_saved_attempt(conn, uid, quiz_id, attempt_id)
        if not result:
            return jsonify({"error": "Không có kết quả Quiz của bạn."}), 404
        return jsonify(result)
    finally:
        conn.close()


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

    profile = ensure_learning_profile(conn, uid)

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

    adaptive_weakness_rows = conn.execute(
        """
        SELECT lw.topic,lw.chapter,lw.miss_count,lw.correct_count,
               s.id AS subject_id,s.name AS subject_name
        FROM learning_weaknesses lw
        JOIN subjects s
          ON s.id=lw.subject_id AND s.user_id=lw.user_id
        WHERE lw.user_id=? AND lw.miss_count > lw.correct_count
        ORDER BY (lw.miss_count - lw.correct_count * 0.5) DESC,
                 lw.last_seen_at DESC
        LIMIT 5
        """,
        (uid,)
    ).fetchall()
    adaptive_weaknesses = [dict(row) for row in adaptive_weakness_rows]
    conn.close()

    today = datetime.now().date()
    now_dt = datetime.now()

    schedule_conflicts = find_study_conflicts(task_rows)
    conflict_task_count = len(schedule_conflicts)

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
        collision = schedule_conflicts.get(item["id"], {})
        item["schedule_conflict"] = bool(collision)
        item["conflict_titles"] = ", ".join(collision.get("with_titles", []))
        item["suggested_study_at"] = collision.get("suggested_at", "")
        item["suggested_time_text"] = (
            item["suggested_study_at"][11:16] if item["suggested_study_at"] else ""
        )
        item["is_today"] = study_dt.date() == today
        item["_study_date"] = study_dt.date()
        item["is_overdue"] = (not row["done"]) and study_dt < now_dt
        completed_tasks += 1 if row["done"] else 0
        overdue_tasks += 1 if item["is_overdue"] else 0
        tasks.append(item)

    # "Danh sách nhiệm vụ hôm nay" chỉ hiển thị đúng các task của ngày hiện tại.
    # Lịch tổng phía trên vẫn giữ toàn bộ task của tất cả môn.
    today_tasks = [
        item
        for item in tasks
        if item["is_today"]
    ]

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

    week_start_date = today - timedelta(days=today.weekday())
    week_end_date = week_start_date + timedelta(days=7)
    week_tasks = [
        item
        for item in tasks
        if week_start_date <= item["_study_date"] < week_end_date
    ]

    weekly_task_count = len(week_tasks)
    weekly_completed_count = sum(
        1 for item in week_tasks if item["done"]
    )
    completion = (
        round((weekly_completed_count / weekly_task_count) * 100)
        if weekly_task_count else 0
    )
    planned_minutes = sum(
        int(item["duration"] or 0)
        for item in week_tasks
    )
    completed_minutes = sum(
        int(item["duration"] or 0)
        for item in week_tasks
        if item["done"]
    )
    time_completion = (
        round((completed_minutes / planned_minutes) * 100)
        if planned_minutes else 0
    )
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
    elif adaptive_weaknesses:
        top_weak = adaptive_weaknesses[0]
        weak_label = (
            f"{top_weak['chapter']} - {top_weak['topic']}"
            if (top_weak["chapter"] or "").strip()
            else top_weak["topic"]
        )
        agent_tip = (
            f"Quiz gần đây cho thấy {top_weak['subject_name']} còn yếu ở “{weak_label}”. "
            "Study Agent đã ưu tiên một buổi ôn thích nghi; sau khi ôn hãy làm Quiz điểm yếu để kiểm tra lại."
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

    # Keep pending deadlines immediately visible. Completed deadlines are
    # still available (with edit/toggle controls) inside a collapsible group.
    pending_reminders = [item for item in reminders if not item["done"]]
    completed_reminders = [item for item in reminders if item["done"]]

    return render_template(
        "study_plan.html",
        page="study_plan",
        subjects=subjects,
        tasks=tasks,
        conflict_task_count=conflict_task_count,
        today_tasks=today_tasks,
        reminders=reminders,
        pending_reminders=pending_reminders,
        completed_reminders=completed_reminders,
        priority_count=priority_count,
        deadline_week=deadline_week,
        reminder_today=reminder_today,
        completion=completion,
        weekly_task_count=weekly_task_count,
        weekly_completed_count=weekly_completed_count,
        planned_minutes=planned_minutes,
        completed_minutes=completed_minutes,
        time_completion=time_completion,
        agent_tip=agent_tip,
        adaptive_weaknesses=adaptive_weaknesses,
        urgent_count=urgent_count,
        today_input=today.isoformat(),
        profile=profile,
    )


@app.route("/study-plan/generate", methods=["POST"])
@login_required
def generate_study_plan_route():
    uid = session["user_id"]
    subject_id = request.form.get("subject_id", type=int)
    goal = request.form.get("goal", "").strip()
    deadline_raw = request.form.get("deadline", "").strip()
    preferred_time = request.form.get("preferred_time", "19:00").strip() or "19:00"
    daily_minutes = _safe_int(request.form.get("daily_minutes"), 45, 15, 180)

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

    backbone = get_course_learning_backbone(
        conn,
        uid,
        subject_id,
        query=goal
    )
    if not backbone:
        conn.close()
        return redirect(url_for("study_plan"))

    weakness_rows = conn.execute(
        """
        SELECT topic,chapter,miss_count,correct_count
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=? AND miss_count > correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC, last_seen_at DESC
        LIMIT 5
        """,
        (uid, subject_id)
    ).fetchall()
    priority_topics = [dict(row) for row in weakness_rows]

    personal_context = get_personal_learning_context(
        uid,
        subject_id,
        max_weaknesses=8
    )

    generated = build_study_plan(
        subject_name=subject["name"],
        goal=goal,
        deadline_dt=deadline_dt,
        daily_minutes=daily_minutes,
        preferred_time=preferred_time,
        context=backbone["personal_context"],
        syllabus_text=backbone["syllabus_text"],
        syllabus_topics=backbone["syllabus_topics"],
        shared_context=backbone["shared_context"],
        personal_context=personal_context,
        priority_topics=priority_topics,
        document_names=backbone["personal_document_names"],
    )

    # Tránh nhân đôi khi người dùng tạo lại kế hoạch cho cùng môn.
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

    # Một môn chỉ giữ 1 deadline đang mở của AI Plan hiện tại.
    # Tạo lại roadmap nghĩa là thay deadline cũ, không cộng dồn reminder.
    conn.execute(
        """
        DELETE FROM reminders
        WHERE user_id=? AND subject_id=? AND done=0 AND source='ai'
        """,
        (uid, subject_id)
    )
    conn.execute(
        """
        INSERT INTO reminders(
            user_id,subject_id,title,due_at,source,created_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            uid,
            subject_id,
            goal,
            deadline_dt.isoformat(timespec="minutes"),
            "ai",
            now()
        )
    )

    conn.commit()
    conn.close()
    return redirect(url_for("study_plan", subject_id=subject_id))


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
            "SELECT subject_id,source FROM study_tasks WHERE id=? AND user_id=?",
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
        if old_task and old_task["source"] == "adaptive":
            from adaptive_review_schedule import lock_adaptive_time
            lock_adaptive_time(conn, task_id, uid)
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


# =====================================================
# MOBILE API - DÙNG CHUNG BACKEND FLASK HIỆN TẠI
# =====================================================
def _mobile_require_user():
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "Phiên đăng nhập đã hết hạn."}), 401)
    conn = db()
    user = conn.execute("SELECT role FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    if not user:
        session.clear()
        return None, (jsonify({"error": "Phiên đăng nhập không hợp lệ."}), 401)
    if user["role"] != "student":
        return None, (jsonify({"error": "Tài khoản quản trị không thể sử dụng API sinh viên."}), 403)
    return uid, None


@app.route("/api/mobile/login", methods=["POST"])
def api_mobile_login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email") or "").strip().lower()
    password = str(payload.get("password") or "")

    if not email or not password:
        return jsonify({"error": "Vui lòng nhập email và mật khẩu."}), 400

    conn = db()
    user = conn.execute(
        "SELECT id,name,email,password_hash,role FROM users WHERE email=?",
        (email,)
    ).fetchone()
    conn.close()

    if (
        not user or user["role"] != "student"
        or not check_password_hash(user["password_hash"], password)
    ):
        return jsonify({"error": "Email hoặc mật khẩu không đúng."}), 401

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]

    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"]
        }
    })


@app.route("/api/mobile/register", methods=["POST"])
def api_mobile_register():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()[:120]
    email = str(payload.get("email") or "").strip().lower()[:240]
    password = str(payload.get("password") or "")
    if not name or not email or "@" not in email or len(password) < 6:
        return jsonify({"error": "Cần tên, email và mật khẩu ít nhất 6 ký tự."}), 400
    conn = db()
    try:
        cursor = conn.execute(
            "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
            (name, email, generate_password_hash(password), now())
        )
        uid = cursor.lastrowid
        conn.commit()
        ensure_learning_profile(conn, uid)
        conn.commit()
        session["user_id"] = uid
        session["user_name"] = name
        return jsonify({"success": True, "user": {"id": uid, "name": name, "email": email}}), 201
    except sqlite3.IntegrityError:
        conn.rollback()
        return jsonify({"error": "Email này đã được đăng ký."}), 409
    finally:
        conn.close()


@app.route("/api/mobile/logout", methods=["POST"])
def api_mobile_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/mobile/session", methods=["GET"])
def api_mobile_session():
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    user = conn.execute(
        "SELECT id,name,email FROM users WHERE id=?", (uid,)
    ).fetchone()
    conn.close()
    if not user:
        session.clear()
        return jsonify({"error": "Phiên đăng nhập không hợp lệ."}), 401
    return jsonify({"user": dict(user)})


@app.route("/api/mobile/dashboard", methods=["GET"])
def api_mobile_dashboard():
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()
    recalculate_all_subject_progress(uid, conn)

    user = conn.execute(
        "SELECT id,name,email FROM users WHERE id=?",
        (uid,)
    ).fetchone()

    subject_rows = conn.execute(
        """
        SELECT id,name,code,progress,target_score
        FROM subjects
        WHERE user_id=?
        ORDER BY progress ASC, name ASC
        """,
        (uid,)
    ).fetchall()

    subjects = []
    for subject in subject_rows:
        weakness = conn.execute(
            """
            SELECT topic,chapter,miss_count,correct_count
            FROM learning_weaknesses
            WHERE user_id=? AND subject_id=?
              AND miss_count > correct_count
            ORDER BY (miss_count - correct_count * 0.5) DESC, last_seen_at DESC
            LIMIT 1
            """,
            (uid, subject["id"])
        ).fetchone()

        item = dict(subject)
        item["weakness"] = dict(weakness) if weakness else None
        subjects.append(item)

    task_rows = conn.execute(
        """
        SELECT t.id,t.title,t.study_at,t.duration,t.done,t.source,
               s.id AS subject_id,s.name AS subject_name
        FROM study_tasks t
        LEFT JOIN subjects s
          ON s.id=t.subject_id AND s.user_id=t.user_id
        WHERE t.user_id=? AND t.done=0
        ORDER BY t.study_at ASC
        LIMIT 8
        """,
        (uid,)
    ).fetchall()

    profile = ensure_learning_profile(conn, uid)
    next_best_action = get_next_best_action(conn, uid)
    stats = {
        "subject_count": len(subjects),
        "task_count": len(task_rows),
        "quiz_attempt_count": conn.execute(
            "SELECT COUNT(*) AS c FROM quiz_attempts WHERE user_id=?", (uid,)
        ).fetchone()["c"],
        "document_count": conn.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE user_id=?", (uid,)
        ).fetchone()["c"],
    }
    conn.close()

    return jsonify({
        "user": dict(user) if user else {},
        "subjects": subjects,
        "tasks": [dict(row) for row in task_rows],
        "next_best_action": next_best_action,
        "stats": stats,
        "profile": {
            "learning_style": profile["learning_style"],
            "preferred_study_time": profile["preferred_study_time"],
            "daily_minutes": profile["daily_minutes"],
            "goals": profile["goals"],
            "notes": profile["notes"]
        }
    })


@app.route("/api/mobile/subjects", methods=["GET"])
def api_mobile_subjects():
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()
    recalculate_all_subject_progress(uid, conn)
    rows = conn.execute(
        """
        SELECT id,name,code,description,credits,target_score,progress
        FROM subjects
        WHERE user_id=?
        ORDER BY name ASC
        """,
        (uid,)
    ).fetchall()

    result = []
    for row in rows:
        item = dict(row)
        weaknesses = conn.execute(
            """
            SELECT topic,chapter,miss_count,correct_count
            FROM learning_weaknesses
            WHERE user_id=? AND subject_id=?
              AND miss_count > correct_count
            ORDER BY (miss_count - correct_count * 0.5) DESC,last_seen_at DESC
            LIMIT 3
            """,
            (uid, row["id"])
        ).fetchall()
        item["weaknesses"] = [dict(value) for value in weaknesses]
        result.append(item)

    conn.close()
    return jsonify(result)


@app.route("/api/mobile/subjects/<int:subject_id>", methods=["GET"])
def api_mobile_subject_detail(subject_id):
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()
    recalculate_subject_progress(uid, subject_id, conn)

    subject = conn.execute(
        """
        SELECT id,name,code,description,credits,target_score,progress,shared_subject_id,
               personal_syllabus_document_id
        FROM subjects
        WHERE id=? AND user_id=?
        """,
        (subject_id, uid)
    ).fetchone()

    if not subject:
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404

    shared = ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    profile = ensure_learning_profile(conn, uid)
    backbone = get_course_learning_backbone(
        conn,
        uid,
        subject_id,
        query=""
    )

    weaknesses = conn.execute(
        """
        SELECT topic,chapter,miss_count,correct_count,last_seen_at
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=?
          AND miss_count > correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC,last_seen_at DESC
        LIMIT 8
        """,
        (uid, subject_id)
    ).fetchall()

    shared_count = conn.execute(
        "SELECT COUNT(*) AS c FROM shared_knowledge WHERE shared_subject_id=?",
        (shared["id"],)
    ).fetchone()["c"]

    document_count = conn.execute(
        "SELECT COUNT(*) AS c FROM documents WHERE user_id=? AND subject_id=?",
        (uid, subject_id)
    ).fetchone()["c"]

    common_docs = conn.execute(
        """SELECT id,original_name,is_syllabus,created_at,
                  LENGTH(extracted_text) AS extracted_chars
           FROM shared_documents
           WHERE shared_subject_id=?
           ORDER BY id DESC LIMIT 60""",
        (shared["id"],)
    ).fetchall()

    conn.close()

    return jsonify({
        "subject": dict(subject),
        "shared": {
            "id": shared["id"],
            "name": shared["name"],
            "code": shared["code"],
            "syllabus_available": bool(backbone and backbone["syllabus_text"]),
            "syllabus_source": (
                backbone["syllabus_source"]
                if backbone else "none"
            ),
            "syllabus_source_name": (
                backbone["syllabus_source_name"]
                if backbone else ""
            ),
            "knowledge_count": int(shared_count or 0)
        },
        "profile": {
            "learning_style": profile["learning_style"],
            "preferred_study_time": profile["preferred_study_time"],
            "daily_minutes": profile["daily_minutes"],
            "goals": profile["goals"],
            "notes": profile["notes"]
        },
        "document_count": int(document_count or 0),
        "shared_documents": [dict(row) for row in common_docs],
        "weaknesses": [dict(row) for row in weaknesses]
    })



@app.route("/api/mobile/shared-documents/<int:doc_id>")
def api_mobile_shared_document(doc_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    row = conn.execute(
        """SELECT sd.id,sd.original_name,sd.extracted_text,sd.is_syllabus,
                  sd.shared_subject_id,ss.name AS subject_name
           FROM shared_documents sd
           JOIN shared_subjects ss ON ss.id=sd.shared_subject_id
           WHERE sd.id=?""",
        (doc_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Không tìm thấy tài liệu chung."}), 404
    student_subjects = conn.execute(
        "SELECT id FROM subjects WHERE user_id=?", (uid,)
    ).fetchall()
    for item in student_subjects:
        ensure_shared_subject_for_user_subject(conn, uid, item["id"])
    allowed = conn.execute(
        "SELECT id FROM subjects WHERE user_id=? AND shared_subject_id=? LIMIT 1",
        (uid, row["shared_subject_id"])
    ).fetchone()
    if not allowed:
        conn.close()
        return jsonify({"error": "Bạn chưa đăng ký môn học tương ứng."}), 403
    output = dict(row)
    # Full extracted text stays cached in DB for the AI. Preview only a sensible limit on iPhone.
    output["extracted_text"] = (row["extracted_text"] or "")[:20000]
    conn.close()
    return jsonify({"document": output})


# =====================================================
# MOBILE PHASE 5B — SUBJECT / PERSONAL DOCUMENT MANAGEMENT
# =====================================================
def _mobile_subject_payload(payload):
    name = str(payload.get("name") or "").strip()[:160]
    if not name:
        return None, "Tên môn học không được để trống."
    code = str(payload.get("code") or "").strip()[:60]
    description = str(payload.get("description") or "").strip()[:2000]
    try:
        credits = int(payload.get("credits") or 0)
        target_score = float(payload.get("target_score") or 0)
    except (ValueError, TypeError):
        return None, "Tín chỉ hoặc mục tiêu điểm không hợp lệ."
    if not 0 <= credits <= 30 or not 0 <= target_score <= 10:
        return None, "Tín chỉ phải từ 0–30 và mục tiêu điểm từ 0–10."
    return (name, code, description, credits, target_score), None


@app.route("/api/mobile/subjects", methods=["POST"])
def api_mobile_create_subject():
    uid, error = _mobile_require_user()
    if error:
        return error
    values, validation = _mobile_subject_payload(request.get_json(silent=True) or {})
    if validation:
        return jsonify({"error": validation}), 400
    conn = db()
    created_at = now()
    cursor = conn.execute(
        """INSERT INTO subjects(
            user_id,name,code,description,credits,target_score,progress,created_at
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (uid, *values, 0, created_at)
    )
    subject_id = cursor.lastrowid
    conn.execute(
        """INSERT INTO chat_conversations(
            user_id,subject_id,title,pinned,created_at,updated_at
        ) VALUES(?,?,?,?,?,?)""",
        (uid, subject_id, values[0], 0, created_at, created_at)
    )
    ensure_shared_subject_for_user_subject(conn, uid, subject_id)
    conn.commit()
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?", (subject_id, uid)
    ).fetchone()
    conn.close()
    return jsonify({"subject": dict(subject)}), 201


@app.route("/api/mobile/subjects/<int:subject_id>", methods=["PUT", "DELETE"])
def api_mobile_modify_subject(subject_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    old = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?", (subject_id, uid)
    ).fetchone()
    if not old:
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404

    if request.method == "PUT":
        values, validation = _mobile_subject_payload(request.get_json(silent=True) or {})
        if validation:
            conn.close()
            return jsonify({"error": validation}), 400
        conn.execute(
            """UPDATE subjects
               SET name=?,code=?,description=?,credits=?,target_score=? 
               WHERE id=? AND user_id=?""",
            (*values, subject_id, uid)
        )
        # Rebind shared knowledge when course code/name changes, never mutate
        # the shared academic record itself.
        conn.execute(
            "UPDATE subjects SET shared_subject_id=NULL WHERE id=? AND user_id=?",
            (subject_id, uid)
        )
        ensure_shared_subject_for_user_subject(conn, uid, subject_id)
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM subjects WHERE id=? AND user_id=?", (subject_id, uid)
        ).fetchone()
        conn.close()
        return jsonify({"subject": dict(updated)})

    # Same deletion semantics as Web: preserve personal documents/quizzes/tasks
    # and safely archive per-session tracking and locked Quiz metadata.
    from subject_course_cleanup import detach_subject_learning_records
    detach_subject_learning_records(conn, uid, subject_id)
    # Remove course-specific chat and reminders.
    convs = conn.execute(
        "SELECT id FROM chat_conversations WHERE user_id=? AND subject_id=?",
        (uid, subject_id)
    ).fetchall()
    for conv in convs:
        conn.execute(
            "DELETE FROM chat_messages WHERE user_id=? AND conversation_id=?",
            (uid, conv["id"])
        )
    conn.execute(
        "DELETE FROM chat_conversations WHERE user_id=? AND subject_id=?",
        (uid, subject_id)
    )
    for table in ("documents", "quizzes", "study_tasks"):
        conn.execute(
            f"UPDATE {table} SET subject_id=NULL WHERE user_id=? AND subject_id=?",
            (uid, subject_id)
        )
    conn.execute(
        "DELETE FROM reminders WHERE user_id=? AND subject_id=?",
        (uid, subject_id)
    )
    conn.execute(
        "DELETE FROM subjects WHERE id=? AND user_id=?", (subject_id, uid)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@app.route("/api/mobile/documents", methods=["GET", "POST"])
def api_mobile_documents():
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()
    if request.method == "GET":
        rows = conn.execute(
            """SELECT d.id,d.subject_id,d.original_name,d.created_at,
                      LENGTH(COALESCE(d.extracted_text,'')) AS extracted_chars,
                      s.name AS subject_name
               FROM documents d
               LEFT JOIN subjects s ON s.id=d.subject_id AND s.user_id=d.user_id
               WHERE d.user_id=? ORDER BY d.id DESC""",
            (uid,)
        ).fetchall()
        conn.close()
        return jsonify({"documents": [dict(row) for row in rows]})

    file = request.files.get("file")
    if not file or not file.filename or not allowed_file(file.filename):
        conn.close()
        return jsonify({"error": "Chọn tệp PDF, TXT hoặc MD hợp lệ."}), 400
    raw_subject_id = request.form.get("subject_id")
    try:
        subject_id = int(raw_subject_id)
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"error": "Vui lòng chọn môn học trước khi tải tài liệu."}), 400
    if not owned_subject_id(conn, uid, subject_id):
        conn.close()
        return jsonify({"error": "Môn học không tồn tại."}), 404

    original = secure_filename(file.filename)
    if not original:
        conn.close()
        return jsonify({"error": "Tên tệp không hợp lệ."}), 400
    stored = f"{uid}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{original}"
    target = UPLOAD_DIR / stored
    try:
        file.save(target)
        extracted = extract_text(target)
        cursor = conn.execute(
            """INSERT INTO documents(
                user_id,subject_id,original_name,stored_name,extracted_text,created_at
            ) VALUES(?,?,?,?,?,?)""",
            (uid, subject_id, original, stored, extracted, now())
        )
        conn.commit()
        row = conn.execute(
            "SELECT id,subject_id,original_name,created_at FROM documents WHERE id=? AND user_id=?",
            (cursor.lastrowid, uid)
        ).fetchone()
        return jsonify({"document": dict(row), "extracted_chars": len(extracted or "")}), 201
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        conn.close()


@app.route("/api/mobile/documents/<int:doc_id>", methods=["GET"])
def api_mobile_document_detail(doc_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    row = conn.execute(
        """SELECT id,subject_id,original_name,created_at,extracted_text
           FROM documents WHERE id=? AND user_id=?""",
        (doc_id, uid)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Không tìm thấy tài liệu."}), 404
    payload = dict(row)
    payload["extracted_text"] = (payload["extracted_text"] or "")[:30000]
    return jsonify({"document": payload})


@app.route("/api/mobile/documents/<int:doc_id>/summary", methods=["POST"])
def api_mobile_document_summary(doc_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    row = conn.execute(
        "SELECT original_name,extracted_text FROM documents WHERE id=? AND user_id=?",
        (doc_id, uid)
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Không tìm thấy tài liệu."}), 404
    source_text = (row["extracted_text"] or "").strip()
    if not source_text:
        return jsonify({
            "summary": "Chưa trích xuất được nội dung chữ từ tài liệu này; PDF scan/ảnh chưa hỗ trợ OCR.",
            "used_ai": False
        })
    prompt = (
        "Bạn là AI Study Agent. Hãy tóm tắt tài liệu sau bằng tiếng Việt. "
        "Chỉ sử dụng nội dung tài liệu, không bịa thêm. Giữ nguyên thuật ngữ, "
        "chia thành: Ý chính, Khái niệm quan trọng, Nội dung cần nhớ. "
        "Ưu tiên bám cấu trúc chương/mục.\n\nTÀI LIỆU:\n"
        + source_text[:14000]
    )
    generated, ai_error = gemini_generate(prompt)
    if generated:
        return jsonify({"summary": generated.strip(), "used_ai": True})
    chunks = [
        item.strip() for item in
        re.split(r"\n{2,}|(?<=[.!?])\s+", source_text)
        if len(item.strip()) >= 25
    ]
    fallback = "\n\n".join(chunks[:12])[:3500] or source_text[:3500]
    return jsonify({"summary": fallback, "used_ai": False, "ai_error": ai_error or ""})


@app.route("/api/mobile/documents/<int:doc_id>", methods=["PUT", "DELETE"])
def api_mobile_modify_document(doc_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    row = conn.execute(
        "SELECT * FROM documents WHERE id=? AND user_id=?", (doc_id, uid)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Không tìm thấy tài liệu."}), 404

    if request.method == "PUT":
        payload = request.get_json(silent=True) or {}
        new_id = payload.get("subject_id")
        if new_id is not None:
            new_id = owned_subject_id(conn, uid, new_id)
            if not new_id:
                conn.close()
                return jsonify({"error": "Môn học không hợp lệ."}), 400
        old_id = row["subject_id"]
        conn.execute(
            "UPDATE documents SET subject_id=? WHERE id=? AND user_id=?",
            (new_id, doc_id, uid)
        )
        if old_id and old_id != new_id:
            conn.execute(
                """UPDATE subjects SET personal_syllabus_document_id=NULL
                   WHERE id=? AND user_id=? AND personal_syllabus_document_id=?""",
                (old_id, uid, doc_id)
            )
        conn.execute(
            "UPDATE quizzes SET subject_id=? WHERE document_id=? AND user_id=?",
            (new_id, doc_id, uid)
        )
        for affected_id in {old_id, new_id} - {None}:
            rebuild_subject_learning_signals(conn, uid, affected_id)
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    old_id = row["subject_id"]
    quiz_ids = conn.execute(
        """SELECT id,subject_id FROM quizzes WHERE user_id=? AND
           (document_id=? OR (document_id IS NULL AND title=?))""",
        (uid, doc_id, f"Quiz từ {row['original_name']}")
    ).fetchall()
    affected_subject_ids = {old_id} | {
        quiz_row["subject_id"] for quiz_row in quiz_ids
    }
    for quiz in quiz_ids:
        conn.execute(
            "DELETE FROM quiz_attempts WHERE user_id=? AND quiz_id=?",
            (uid, quiz["id"])
        )
        conn.execute(
            "DELETE FROM quizzes WHERE user_id=? AND id=?",
            (uid, quiz["id"])
        )
    conn.execute(
        """UPDATE subjects SET personal_syllabus_document_id=NULL
           WHERE user_id=? AND personal_syllabus_document_id=?""",
        (uid, doc_id)
    )
    conn.execute(
        "DELETE FROM documents WHERE user_id=? AND id=?", (uid, doc_id)
    )
    for affected_id in affected_subject_ids - {None}:
        rebuild_subject_learning_signals(conn, uid, affected_id)
    conn.commit()
    conn.close()
    (UPLOAD_DIR / row["stored_name"]).unlink(missing_ok=True)
    return jsonify({"success": True})


@app.route("/api/mobile/subjects/<int:subject_id>/personal-syllabus", methods=["PUT"])
def api_mobile_set_personal_syllabus(subject_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    if not owned_subject_id(conn, uid, subject_id):
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404
    payload = request.get_json(silent=True) or {}
    document_id = payload.get("document_id")
    if document_id not in (None, ""):
        try:
            document_id = int(document_id)
        except (ValueError, TypeError):
            conn.close()
            return jsonify({"error": "Tài liệu không hợp lệ."}), 400
        owned_doc = conn.execute(
            "SELECT id FROM documents WHERE id=? AND subject_id=? AND user_id=?",
            (document_id, subject_id, uid)
        ).fetchone()
        if not owned_doc:
            conn.close()
            return jsonify({"error": "Đề cương phải là tài liệu cá nhân trong môn học."}), 400
    else:
        document_id = None
    conn.execute(
        """UPDATE subjects SET personal_syllabus_document_id=?
           WHERE id=? AND user_id=?""",
        (document_id, subject_id, uid)
    )
    conn.commit()
    backbone = get_course_learning_backbone(conn, uid, subject_id)
    conn.close()
    return jsonify({
        "success": True,
        "document_id": document_id,
        "syllabus_source": backbone["syllabus_source"],
        "syllabus_source_name": backbone["syllabus_source_name"]
    })


@app.route("/api/mobile/chat", methods=["POST"])
def api_mobile_chat():
    uid, error = _mobile_require_user()
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    subject_id = payload.get("subject_id")
    question = str(payload.get("message") or payload.get("question") or "").strip()

    try:
        subject_id = int(subject_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Hãy chọn môn học trước khi hỏi."}), 400

    if not question:
        return jsonify({"error": "Câu hỏi trống."}), 400

    conn = db()
    ensure_subject_chats(uid, conn)

    conversation = conn.execute(
        """
        SELECT c.id,c.subject_id,s.name AS subject_name
        FROM chat_conversations c
        JOIN subjects s
          ON s.id=c.subject_id AND s.user_id=c.user_id
        WHERE c.user_id=? AND c.subject_id=?
        LIMIT 1
        """,
        (uid, subject_id)
    ).fetchone()

    if not conversation:
        conn.close()
        return jsonify({"error": "Không tìm thấy Chat của môn học."}), 404

    history_rows = conn.execute(
        """
        SELECT role,content
        FROM chat_messages
        WHERE user_id=? AND conversation_id=?
        ORDER BY id DESC
        LIMIT 10
        """,
        (uid, conversation["id"])
    ).fetchall()
    history_rows = list(reversed(history_rows))
    conversation_history = "\n".join(
        f"{'Bạn' if row['role']=='user' else 'AI'}: {row['content']}"
        for row in history_rows
    )
    conn.close()

    context, candidate_sources = get_subject_context(
        uid, subject_id, question
    )
    shared_context, shared_sources = get_shared_subject_context(
        uid, subject_id, question
    )
    personal_context = get_personal_learning_context(
        uid, subject_id
    )

    answer, used_sources, source_mode = gemini_subject_answer(
        conversation["subject_name"],
        question,
        context,
        candidate_sources,
        conversation_history,
        shared_context,
        personal_context,
        shared_sources
    )

    conn = db()
    created_at = now()
    conn.execute(
        """
        INSERT INTO chat_messages(user_id,conversation_id,role,content,created_at)
        VALUES(?,?,?,?,?)
        """,
        (uid, conversation["id"], "user", question, created_at)
    )
    conn.execute(
        """
        INSERT INTO chat_messages(user_id,conversation_id,role,content,created_at)
        VALUES(?,?,?,?,?)
        """,
        (uid, conversation["id"], "assistant", answer, now())
    )
    conn.execute(
        "UPDATE chat_conversations SET updated_at=? WHERE id=? AND user_id=?",
        (now(), conversation["id"], uid)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "answer": answer,
        "subject_id": subject_id,
        "subject_name": conversation["subject_name"],
        "source_mode": source_mode,
        "sources": used_sources
    })


@app.route("/api/mobile/chat/<int:subject_id>", methods=["GET"])
def api_mobile_chat_history(subject_id):
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()
    ensure_subject_chats(uid, conn)

    conversation = conn.execute(
        """
        SELECT c.id,c.subject_id,s.name AS subject_name
        FROM chat_conversations c
        JOIN subjects s
          ON s.id=c.subject_id AND s.user_id=c.user_id
        WHERE c.user_id=? AND c.subject_id=?
        LIMIT 1
        """,
        (uid, subject_id)
    ).fetchone()

    if not conversation:
        conn.close()
        return jsonify({"error": "Không tìm thấy Chat của môn học."}), 404

    rows = conn.execute(
        """
        SELECT id,role,content,created_at
        FROM chat_messages
        WHERE user_id=? AND conversation_id=?
        ORDER BY id ASC
        LIMIT 200
        """,
        (uid, conversation["id"])
    ).fetchall()
    conn.close()

    return jsonify({
        "subject_id": subject_id,
        "subject_name": conversation["subject_name"],
        "messages": [dict(row) for row in rows]
    })


def public_quiz_questions(questions):
    """Không đưa đáp án và lời giải Quiz chưa nộp xuống client."""
    return [
        {key: value for key, value in question.items()
         if key not in ("answer", "explanation")}
        for question in questions
    ]


@app.route("/api/mobile/quiz/generate", methods=["POST"])
def api_mobile_quiz_generate():
    uid, error = _mobile_require_user()
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode") or "subject").strip().lower()
    question_count = _safe_int(payload.get("count"), 10, 10, 30)
    if question_count not in (10, 20, 30):
        question_count = 10

    conn = db()
    subject_id = owned_subject_id(conn, uid, payload.get("subject_id"))
    document_id = None
    title = "Quiz luyện tập"
    questions = []

    if mode == "document":
        try:
            document_id = int(payload.get("document_id"))
        except (TypeError, ValueError):
            document_id = None

        doc = conn.execute(
            """
            SELECT *
            FROM documents
            WHERE id=? AND user_id=?
            """,
            (document_id, uid)
        ).fetchone() if document_id else None

        if doc:
            subject_id = doc["subject_id"]
            questions = build_quiz(doc["extracted_text"] or "", question_count)
            title = f"Quiz từ {doc['original_name']}"

    elif subject_id:
        subject = conn.execute(
            "SELECT id,name FROM subjects WHERE id=? AND user_id=?",
            (subject_id, uid)
        ).fetchone()

        backbone = (
            get_course_learning_backbone(
                conn,
                uid,
                subject_id,
                query=""
            )
            if subject else None
        )

        context_parts = []
        if backbone and backbone["syllabus_text"]:
            syllabus_label = (
                "ĐỀ CƯƠNG CHUẨN CỦA MÔN"
                if backbone["syllabus_source"] == "shared"
                else "ĐỀ CƯƠNG CÁ NHÂN FALLBACK"
            )
            context_parts.append(
                f"{syllabus_label}:\n"
                f"{backbone['syllabus_text'][:9000]}"
            )

        if backbone and backbone["shared_context"]:
            context_parts.append(
                "KIẾN THỨC DÙNG CHUNG BỔ TRỢ:\n"
                + backbone["shared_context"][:5500]
            )

        if backbone and backbone["personal_context"]:
            context_parts.append(
                "TÀI LIỆU CÁ NHÂN BỔ TRỢ:\n"
                + backbone["personal_context"][:7500]
            )

        focus_topics = []
        if mode == "weakness":
            weakness_rows = conn.execute(
                """
                SELECT topic,chapter,miss_count,correct_count
                FROM learning_weaknesses
                WHERE user_id=? AND subject_id=?
                  AND miss_count > correct_count
                ORDER BY (miss_count - correct_count * 0.5) DESC,last_seen_at DESC
                LIMIT 8
                """,
                (uid, subject_id)
            ).fetchall()
            focus_topics = [dict(row) for row in weakness_rows]

        combined_context = "\n\n".join(context_parts)[:22000]
        if combined_context and subject and (mode != "weakness" or focus_topics):
            questions = build_quiz(
                combined_context,
                question_count,
                focus_topics=focus_topics
            )
            title = (
                f"Ôn điểm yếu · {subject['name']}"
                if mode == "weakness"
                else f"Quiz môn {subject['name']}"
            )

    if not questions:
        conn.close()
        return jsonify({
            "error": "Chưa đủ tài liệu, dữ liệu điểm yếu hoặc Gemini chưa tạo đủ câu hỏi hợp lệ. Hãy kiểm tra nguồn học và thử lại."
        }), 400

    cursor = conn.execute(
        """
        INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
        VALUES(?,?,?,?,?,?)
        """,
        (
            uid,
            subject_id,
            document_id,
            title,
            json.dumps(questions, ensure_ascii=False),
            now()
        )
    )
    quiz_id = cursor.lastrowid
    if mode == "weakness" and subject_id:
        from quiz_review_progress import save_review_baseline
        save_review_baseline(conn, uid, subject_id, quiz_id, now())
    conn.commit()
    conn.close()

    return jsonify({
        "quiz_id": quiz_id,
        "title": title,
        "questions": public_quiz_questions(questions)
    })


@app.route("/api/mobile/quiz/submit", methods=["POST"])
def api_mobile_quiz_submit():
    uid, error = _mobile_require_user()
    if error:
        return error

    # submit_quiz dùng cùng session + JSON payload, nên tái sử dụng toàn bộ
    # logic chấm bài và cập nhật learning_weaknesses của web.
    return submit_quiz()


@app.route("/api/mobile/study-plan", methods=["GET", "POST"])
def api_mobile_study_plan():
    uid, error = _mobile_require_user()
    if error:
        return error

    conn = db()

    if request.method == "GET":
        profile = ensure_learning_profile(conn, uid)
        rows = conn.execute(
            """
            SELECT t.id,t.subject_id,t.title,t.study_at,t.duration,t.note,t.done,t.source,
                   s.name AS subject_name
            FROM study_tasks t
            LEFT JOIN subjects s
              ON s.id=t.subject_id AND s.user_id=t.user_id
            WHERE t.user_id=?
            ORDER BY t.done ASC,t.study_at ASC
            LIMIT 200
            """,
            (uid,)
        ).fetchall()
        total_tasks = conn.execute(
            "SELECT COUNT(*) FROM study_tasks WHERE user_id=?", (uid,)
        ).fetchone()[0]
        conn.close()
        return jsonify({
            "total_tasks": total_tasks,
            "truncated": total_tasks > len(rows),
            "profile": {
                "learning_style": profile["learning_style"],
                "preferred_study_time": profile["preferred_study_time"],
                "daily_minutes": profile["daily_minutes"],
                "goals": profile["goals"],
                "notes": profile["notes"]
            },
            "tasks": [dict(row) for row in rows]
        })

    payload = request.get_json(silent=True) or {}
    subject_id = owned_subject_id(conn, uid, payload.get("subject_id"))
    goal = str(payload.get("goal") or "").strip()
    deadline_raw = str(payload.get("deadline") or "").strip()

    if not subject_id or not goal or not deadline_raw:
        conn.close()
        return jsonify({"error": "Thiếu môn học, mục tiêu hoặc deadline."}), 400

    try:
        deadline_dt = datetime.fromisoformat(deadline_raw)
    except ValueError:
        conn.close()
        return jsonify({"error": "Deadline không hợp lệ."}), 400

    if deadline_dt < datetime.now():
        conn.close()
        return jsonify({"error": "Deadline phải ở tương lai."}), 400

    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id, uid)
    ).fetchone()
    if not subject:
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404

    profile = ensure_learning_profile(conn, uid)

    preferred_time = str(
        payload.get("preferred_time")
        or profile["preferred_study_time"]
        or "19:00"
    ).strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", preferred_time):
        preferred_time = "19:00"

    daily_minutes = _safe_int(
        payload.get("daily_minutes"),
        int(profile["daily_minutes"] or 45),
        15,
        180
    )

    backbone = get_course_learning_backbone(
        conn,
        uid,
        subject_id,
        query=goal
    )
    if not backbone:
        conn.close()
        return jsonify({"error": "Không đọc được cấu trúc môn học."}), 400

    weakness_rows = conn.execute(
        """
        SELECT topic,chapter,miss_count,correct_count
        FROM learning_weaknesses
        WHERE user_id=? AND subject_id=? AND miss_count > correct_count
        ORDER BY (miss_count - correct_count * 0.5) DESC,last_seen_at DESC
        LIMIT 5
        """,
        (uid, subject_id)
    ).fetchall()
    priority_topics = [dict(row) for row in weakness_rows]

    personal_context = get_personal_learning_context(
        uid,
        subject_id,
        max_weaknesses=8
    )

    generated = build_study_plan(
        subject_name=subject["name"],
        goal=goal,
        deadline_dt=deadline_dt,
        daily_minutes=daily_minutes,
        preferred_time=preferred_time,
        context=backbone["personal_context"],
        syllabus_text=backbone["syllabus_text"],
        syllabus_topics=backbone["syllabus_topics"],
        shared_context=backbone["shared_context"],
        personal_context=personal_context,
        priority_topics=priority_topics,
        document_names=backbone["personal_document_names"],
    )

    conn.execute(
        """
        DELETE FROM study_tasks
        WHERE user_id=? AND subject_id=? AND source='ai' AND done=0
        """,
        (uid, subject_id)
    )

    for task in generated:
        conn.execute(
            """
            INSERT INTO study_tasks(
                user_id,subject_id,title,study_at,duration,note,done,source,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                uid,
                subject_id,
                task["title"],
                f"{task['date']}T{task['time']}",
                task["duration"],
                task["note"],
                0,
                "ai",
                now()
            )
        )

    # Đồng bộ đúng semantics với Web: tạo lại AI Plan sẽ thay deadline cũ
    # đang mở của chính môn đó, không để nhiều reminder chồng lên nhau.
    conn.execute(
        """
        DELETE FROM reminders
        WHERE user_id=? AND subject_id=? AND done=0 AND source='ai'
        """,
        (uid, subject_id)
    )
    conn.execute(
        """
        INSERT INTO reminders(
            user_id,subject_id,title,due_at,source,created_at
        ) VALUES(?,?,?,?,?,?)
        """,
        (
            uid,
            subject_id,
            goal,
            deadline_dt.isoformat(timespec="minutes"),
            "ai",
            now()
        )
    )

    conn.commit()

    rows = conn.execute(
        """
        SELECT id,subject_id,title,study_at,duration,note,done,source
        FROM study_tasks
        WHERE user_id=? AND subject_id=?
        ORDER BY study_at ASC
        """,
        (uid, subject_id)
    ).fetchall()
    conn.close()

    return jsonify({
        "success": True,
        "course_backbone": {
            "has_syllabus": bool(backbone["syllabus_text"]),
            "syllabus_source": backbone["syllabus_source"],
            "syllabus_source_name": backbone["syllabus_source_name"],
            "syllabus_topics": backbone["syllabus_topics"][:12],
            "personal_documents": backbone["personal_document_names"],
            "shared_sources": backbone["shared_source_names"],
        },
        "tasks": [dict(row) for row in rows]
    })



# =====================================================
# MOBILE FEATURE PARITY — PLANNER, QUIZZES, PERSONAL PROFILE
# =====================================================
@app.route("/api/mobile/tasks", methods=["POST"])
@app.route("/api/mobile/tasks/<int:task_id>", methods=["PUT", "DELETE"])
def api_mobile_tasks(task_id=None):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    old = None
    if task_id is not None:
        old = conn.execute(
            "SELECT * FROM study_tasks WHERE id=? AND user_id=?",
            (task_id, uid)
        ).fetchone()
        if not old:
            conn.close()
            return jsonify({"error": "Không tìm thấy buổi học."}), 404
    if request.method == "DELETE":
        conn.execute(
            "DELETE FROM study_tasks WHERE id=? AND user_id=?", (task_id, uid)
        )
        if old["subject_id"]:
            recalculate_subject_progress(uid, old["subject_id"], conn)
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    payload = request.get_json(silent=True) or {}
    subject_value = payload.get("subject_id")
    subject_id = owned_subject_id(conn, uid, subject_value) if subject_value else None
    if subject_value and not subject_id:
        conn.close()
        return jsonify({"error": "Môn học không hợp lệ."}), 400
    title = str(payload.get("title") or "").strip()[:240]
    study_at = str(payload.get("study_at") or "").strip()
    note = str(payload.get("note") or "").strip()[:1500]
    duration = _safe_int(payload.get("duration"), 45, 15, 240)
    try:
        parsed = datetime.fromisoformat(study_at)
    except (ValueError, TypeError):
        parsed = None
    if not title or not parsed:
        conn.close()
        return jsonify({"error": "Cần tên nhiệm vụ và thời gian hợp lệ (YYYY-MM-DDTHH:MM)."}), 400

    if old:
        conn.execute(
            """UPDATE study_tasks SET title=?,subject_id=?,study_at=?,duration=?,note=?
               WHERE id=? AND user_id=?""",
            (title, subject_id, study_at, duration, note, task_id, uid)
        )
        if old["source"] == "adaptive":
            from adaptive_review_schedule import lock_adaptive_time
            lock_adaptive_time(conn, task_id, uid)
        if old["subject_id"]:
            recalculate_subject_progress(uid, old["subject_id"], conn)
    else:
        task_id = conn.execute(
            """INSERT INTO study_tasks(
                 user_id,subject_id,title,study_at,duration,note,done,source,created_at
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (uid, subject_id, title, study_at, duration, note, 0, "manual", now())
        ).lastrowid
    if subject_id:
        recalculate_subject_progress(uid, subject_id, conn)
    conn.commit()
    row = conn.execute(
        "SELECT * FROM study_tasks WHERE id=? AND user_id=?", (task_id, uid)
    ).fetchone()
    conn.close()
    return jsonify({"task": dict(row)}), 200 if old else 201


@app.route("/api/mobile/tasks/<int:task_id>/toggle", methods=["POST"])
def api_mobile_toggle_task(task_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    row = conn.execute(
        "SELECT * FROM study_tasks WHERE id=? AND user_id=?", (task_id, uid)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Không tìm thấy buổi học."}), 404
    done = 0 if row["done"] else 1
    conn.execute(
        "UPDATE study_tasks SET done=?, completed_at=? WHERE id=? AND user_id=?",
        (done, now() if done else "", task_id, uid)
    )
    if row["subject_id"]:
        recalculate_subject_progress(uid, row["subject_id"], conn)
    conn.commit()
    conn.close()
    return jsonify({"success": True, "done": done})


@app.route("/api/mobile/reminders", methods=["GET", "POST"])
@app.route("/api/mobile/reminders/<int:reminder_id>", methods=["PUT", "DELETE"])
def api_mobile_reminders(reminder_id=None):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    if request.method == "GET":
        rows = conn.execute(
            """SELECT r.*, s.name AS subject_name FROM reminders r
               LEFT JOIN subjects s ON s.id=r.subject_id AND s.user_id=r.user_id
               WHERE r.user_id=? ORDER BY r.done ASC,r.due_at ASC""",
            (uid,)
        ).fetchall()
        conn.close()
        return jsonify({"reminders": [dict(row) for row in rows]})
    existing = None
    if reminder_id is not None:
        existing = conn.execute(
            "SELECT * FROM reminders WHERE id=? AND user_id=?",
            (reminder_id, uid)
        ).fetchone()
        if not existing:
            conn.close()
            return jsonify({"error": "Không tìm thấy deadline."}), 404
    if request.method == "DELETE":
        conn.execute(
            "DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, uid)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True})

    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()[:240]
    due_at = str(payload.get("due_at") or "").strip()
    subject_value = payload.get("subject_id")
    subject_id = owned_subject_id(conn, uid, subject_value) if subject_value else None
    if subject_value and not subject_id:
        conn.close()
        return jsonify({"error": "Môn học không hợp lệ."}), 400
    if not title:
        conn.close()
        return jsonify({"error": "Vui lòng nhập tiêu đề."}), 400
    try:
        datetime.fromisoformat(due_at)
    except (ValueError, TypeError):
        conn.close()
        return jsonify({"error": "Thời hạn không hợp lệ."}), 400
    done = 1 if payload.get("done") else 0
    if existing:
        conn.execute(
            """UPDATE reminders SET title=?,due_at=?,subject_id=?,done=?
               WHERE id=? AND user_id=?""",
            (title, due_at, subject_id, done, reminder_id, uid)
        )
    else:
        reminder_id = conn.execute(
            """INSERT INTO reminders(user_id,subject_id,title,due_at,done,created_at)
               VALUES(?,?,?,?,?,?)""",
            (uid, subject_id, title, due_at, done, now())
        ).lastrowid
    conn.commit()
    row = conn.execute(
        "SELECT * FROM reminders WHERE id=? AND user_id=?", (reminder_id, uid)
    ).fetchone()
    conn.close()
    return jsonify({"reminder": dict(row)}), 200 if existing else 201


@app.route("/api/mobile/quizzes", methods=["GET"])
def api_mobile_quizzes():
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    subject_id = request.args.get("subject_id", type=int)
    if subject_id and not owned_subject_id(conn, uid, subject_id):
        conn.close()
        return jsonify({"error": "Không tìm thấy môn học."}), 404
    rows = conn.execute(
        """SELECT q.id,q.subject_id,q.document_id,q.title,q.created_at,
                  s.name AS subject_name,COUNT(qa.id) AS attempt_count,
                  MAX(qa.score) AS best_score
           FROM quizzes q
           LEFT JOIN quiz_attempts qa ON qa.quiz_id=q.id AND qa.user_id=q.user_id
           LEFT JOIN subjects s ON s.id=q.subject_id AND s.user_id=q.user_id
           LEFT JOIN quiz_session_links qsl
             ON qsl.quiz_id=q.id AND qsl.user_id=q.user_id
           WHERE q.user_id=? AND (? IS NULL OR q.subject_id=?)
             AND (qsl.quiz_id IS NULL OR qsl.subject_id IS NOT NULL)
           GROUP BY q.id ORDER BY q.id DESC LIMIT 100""",
        (uid, subject_id, subject_id)
    ).fetchall()
    conn.close()
    return jsonify({"quizzes": [dict(row) for row in rows]})


@app.route("/api/mobile/quizzes/<int:quiz_id>", methods=["GET"])
def api_mobile_quiz_detail(quiz_id):
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    quiz = conn.execute(
        "SELECT * FROM quizzes WHERE id=? AND user_id=?", (quiz_id, uid)
    ).fetchone()
    if not quiz:
        conn.close()
        return jsonify({"error": "Không tìm thấy Quiz."}), 404
    from study_session_quiz_runtime import quiz_access
    gate = quiz_access(conn, sys.modules[__name__], uid, quiz_id)
    if gate["linked"] and not gate["allowed"]:
        conn.close()
        return jsonify({"error": gate.get("reason", "Quiz đang khóa."),
                        "locked": True}), 409
    attempts = conn.execute(
        """SELECT id,score,correct_count,total_questions,answers_json,created_at
           FROM quiz_attempts WHERE quiz_id=? AND user_id=?
           ORDER BY id DESC LIMIT 20""",
        (quiz_id, uid)
    ).fetchall()
    conn.close()
    return jsonify({
        "quiz_id": quiz_id,
        "subject_id": quiz["subject_id"],
        "title": quiz["title"],
        "questions": public_quiz_questions(json.loads(quiz["payload"] or "[]")),
        "attempts": [dict(row) for row in attempts]
    })


@app.route("/api/mobile/profile", methods=["GET", "PUT"])
def api_mobile_profile():
    uid, error = _mobile_require_user()
    if error:
        return error
    conn = db()
    profile = ensure_learning_profile(conn, uid)
    if request.method == "GET":
        conn.close()
        return jsonify({"profile": dict(profile)})
    payload = request.get_json(silent=True) or {}
    learning_style = str(payload.get("learning_style", profile["learning_style"] or "balanced")).strip()[:40] or "balanced"
    preferred_time = str(payload.get("preferred_study_time", profile["preferred_study_time"] or "19:00")).strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", preferred_time):
        conn.close()
        return jsonify({"error": "Giờ học cần có dạng HH:MM."}), 400
    daily_minutes = _safe_int(payload.get("daily_minutes"), 45, 15, 240)
    goals = str(payload.get("goals", profile["goals"] or "")).strip()[:1200]
    notes = str(payload.get("notes", profile["notes"] or "")).strip()[:1200]
    conn.execute(
        """UPDATE learning_profiles SET learning_style=?,preferred_study_time=?,
                  daily_minutes=?,goals=?,notes=?,updated_at=? WHERE user_id=?""",
        (learning_style, preferred_time, daily_minutes, goals, notes, now(), uid)
    )
    conn.commit()
    updated = conn.execute(
        "SELECT * FROM learning_profiles WHERE user_id=?", (uid,)
    ).fetchone()
    conn.close()
    return jsonify({"profile": dict(updated)})


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
    # Local persistent Flask server: resume queued AI Quiz preparation even
    # after navigating away, tab close, or application restart. Disable the
    # development reloader to prevent duplicate concurrent worker threads.
    from quiz_preparation_jobs import start_local_worker
    start_local_worker(sys.modules[__name__])
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        use_reloader=False,
        host=os.getenv("FLASK_HOST", "0.0.0.0"),
        port=int(os.getenv("FLASK_PORT", "5000"))
    )