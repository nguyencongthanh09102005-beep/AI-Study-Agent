"""Regression: student can delete old/new courses with session Quiz / timer FK rows.

Run with an isolated DB. Migrate old restrictive FKs without destroying existing
Quiz questions, attempts, personal documents, planner tasks or study seconds.
"""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from study_session_quiz_runtime import quiz_access


def login(client, uid):
    with client.session_transaction() as session:
        session.clear()
        session["user_id"] = uid


def verify():
    with TemporaryDirectory() as folder:
        old_path, old_upload = project.DB_PATH, project.UPLOAD_DIR
        try:
            project.DB_PATH = Path(folder) / "delete-test.sqlite"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn = project.db()
            # Recreate original 7.1 and 6.4 schemas (both with RESTRICT).
            conn.execute("DROP TABLE IF EXISTS quiz_session_links")
            conn.execute("DROP TABLE IF EXISTS study_session_tracking")
            conn.execute("""
                CREATE TABLE quiz_session_links(
                    quiz_id INTEGER PRIMARY KEY,
                    task_id INTEGER,
                    user_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    chapter_number INTEGER NOT NULL CHECK(chapter_number >= 1),
                    session_title TEXT NOT NULL,
                    session_signature TEXT NOT NULL,
                    source_signature TEXT NOT NULL,
                    source_ids_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE,
                    FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE SET NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(subject_id) REFERENCES subjects(id)
                )
            """)
            conn.execute("""
                CREATE TABLE study_session_tracking(
                    task_id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'paused',
                    started_at TEXT NOT NULL,
                    last_heartbeat_at TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    completed_at TEXT DEFAULT '', updated_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES study_tasks(id) ON DELETE CASCADE,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(subject_id) REFERENCES subjects(id)
                )
            """)
            uid = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Student delete','delete-s@example.test','hash','student',?)
            """, (project.now(),)).lastrowid
            other = conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Other','delete-other@example.test','hash','student',?)
            """, (project.now(),)).lastrowid

            def insert_course(user, name):
                subject = conn.execute("""
                    INSERT INTO subjects(user_id,name,code,created_at)
                    VALUES(?,?,?,?)
                """, (user, name, "TESTDEL", project.now())).lastrowid
                doc = conn.execute("""
                    INSERT INTO documents(user_id,subject_id,original_name,
                        stored_name,extracted_text,created_at)
                    VALUES(?,?,?,?,?,?)
                """, (user, subject, "Tài liệu cá nhân", f"{subject}.txt",
                      "Bài học về thuật toán và cấu trúc dữ liệu", project.now())).lastrowid
                task = conn.execute("""
                    INSERT INTO study_tasks(user_id,subject_id,title,study_at,
                        duration,note,done,source,completed_at,created_at)
                    VALUES(?,?,?,?,?,'',0,'roadmap','',?)
                """, (user, subject, "Buổi học", "2026-11-01T19:00", 60,
                      project.now())).lastrowid
                question = [{"question": "Node là gì?", "options": [
                    "Node trong linked list", "Root", "Heap", "Array"],
                    "topic": "Cấu trúc dữ liệu", "chapter": "Chương 1", "answer": 0}]
                quiz = conn.execute("""
                    INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                    VALUES(?,?,NULL,?,?,?)
                """, (user, subject, "Quiz theo buổi",
                      json.dumps(question), project.now())).lastrowid
                attempt = conn.execute("""
                    INSERT INTO quiz_attempts(
                      user_id,quiz_id,score,correct_count,total_questions,answers_json,created_at)
                    VALUES(?,?,100,1,1,'[0]',?)
                """, (user, quiz, project.now())).lastrowid
                conn.execute("""
                    INSERT INTO quiz_session_links(
                      quiz_id,task_id,user_id,subject_id,chapter_number,
                      session_title,session_signature,source_signature,
                      source_ids_json,created_at)
                    VALUES(?,?,?,?,1,'Buổi học','sig','source','[]',?)
                """, (quiz, task, user, subject, project.now()))
                conn.execute("""
                    INSERT INTO study_session_tracking(
                       task_id,user_id,subject_id,status,started_at,
                       last_heartbeat_at,elapsed_seconds,updated_at)
                    VALUES(?,?,?,'paused',?,?,1800,?)
                """, (task, user, subject, project.now(), project.now(),
                      project.now()))
                return {"subject": subject, "doc": doc, "task": task,
                        "quiz": quiz, "attempt": attempt}

            first = insert_course(uid, "Môn mới A")
            second = insert_course(uid, "Môn mới B")
            foreign = insert_course(other, "Môn người khác")
            # Pending AI work must not linger after its course is removed.
            from study_session_quiz_runtime import ensure_quiz_runtime_schema
            ensure_quiz_runtime_schema(conn)
            conn.execute("""
                INSERT INTO quiz_preparation_parts(
                  task_id,source_task_id,user_id,source_signature,questions_json,created_at)
                VALUES(?,?,?,'sig','[]',?)
            """, (first["task"], first["task"], uid, project.now()))
            conn.execute("""
                INSERT INTO quiz_preparation_claims(task_id,user_id,step_key,claimed_at)
                VALUES(?,?,?,?)
            """, (first["task"], uid, "step", project.now()))
            conn.execute("""
                INSERT INTO quiz_session_grants(quiz_id,user_id,started_at,valid_until)
                VALUES(?,?,?,?)
            """, (first["quiz"], uid, "2026-11-01T19:00", "2026-11-01T20:00"))
            conn.commit()
            conn.close()

            client = project.app.test_client()
            login(client, other)
            denied = client.post(f"/subjects/{first['subject']}/delete")
            assert denied.status_code in (302, 303)
            conn = project.db()
            assert conn.execute("SELECT id FROM subjects WHERE id=?",
                                (first["subject"],)).fetchone()
            conn.close()

            login(client, uid)
            removed = client.post(f"/subjects/{first['subject']}/delete")
            assert removed.status_code in (302, 303), removed.get_data(as_text=True)
            conn = project.db()
            assert not conn.execute("SELECT id FROM subjects WHERE id=?",
                                    (first["subject"],)).fetchone()
            for table, key, value in (
                ("documents", "id", first["doc"]),
                ("quizzes", "id", first["quiz"]),
                ("study_tasks", "id", first["task"]),
                ("quiz_attempts", "id", first["attempt"]),
            ):
                row = conn.execute(f"SELECT * FROM {table} WHERE {key}=?",
                                   (value,)).fetchone()
                assert row, (table, key)
                if table != "quiz_attempts":
                    assert row["subject_id"] is None, table
            link = conn.execute(
                "SELECT * FROM quiz_session_links WHERE quiz_id=?",
                (first["quiz"],)).fetchone()
            assert link and link["subject_id"] is None
            elapsed = conn.execute(
                "SELECT * FROM study_session_tracking WHERE task_id=?",
                (first["task"],)).fetchone()
            assert elapsed["subject_id"] is None
            assert elapsed["elapsed_seconds"] == 1800
            assert quiz_access(conn, project, uid, first["quiz"])["allowed"] is False
            assert conn.execute("SELECT COUNT(*) FROM quiz_session_grants WHERE quiz_id=?",
                                (first["quiz"],)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM quiz_preparation_parts WHERE task_id=?",
                                (first["task"],)).fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM quiz_preparation_claims WHERE task_id=?",
                                (first["task"],)).fetchone()[0] == 0
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            assert conn.execute("SELECT subject_id FROM quiz_session_links WHERE quiz_id=?",
                                (second["quiz"],)).fetchone()[0] == second["subject"]
            assert conn.execute("SELECT subject_id FROM quiz_session_links WHERE quiz_id=?",
                                (foreign["quiz"],)).fetchone()[0] == foreign["subject"]
            conn.close()
            assert str(first["quiz"]) not in client.get("/quiz").get_data(as_text=True).split('data-quiz-id="')
            assert client.get(f"/api/mobile/quizzes/{first['quiz']}").status_code == 409
            # The private archived record remains in SQLite, but the
            # deleted course's session Quiz must leave the selectable lists
            # on both Web and Mobile.
            mobile_archive = client.get("/api/mobile/quizzes")
            assert mobile_archive.status_code == 200
            assert all(q["id"] != first["quiz"]
                       for q in mobile_archive.get_json()["quizzes"])
            assert any(q["id"] == second["quiz"]
                       for q in mobile_archive.get_json()["quizzes"])
            assert client.post("/api/quiz/submit", json={
                "quiz_id": first["quiz"], "answers": [0]
            }).status_code == 409

            # Mobile route must obey exactly the same safe semantics.
            response = client.delete(f"/api/mobile/subjects/{second['subject']}")
            assert response.status_code == 200, response.get_data(as_text=True)
            conn = project.db()
            assert not conn.execute("SELECT id FROM subjects WHERE id=?",
                                    (second["subject"],)).fetchone()
            assert conn.execute("SELECT id FROM quizzes WHERE id=?",
                                (second["quiz"],)).fetchone()
            assert conn.execute("SELECT id FROM subjects WHERE id=?",
                                (foreign["subject"],)).fetchone()
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            conn.close()
        finally:
            project.DB_PATH, project.UPLOAD_DIR = old_path, old_upload


if __name__ == "__main__":
    verify()
    print("Web/Mobile course deletion + legacy 6.4/7 FK migration + archive retention OK")
