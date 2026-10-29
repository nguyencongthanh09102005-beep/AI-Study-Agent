"""7.6: durable server-side Quiz preparation jobs on persistent Flask hosts.

A browser submits only one job. A single application worker performs bounded
prepare_step calls. SQLite contains the queue and partial Quiz data, so moving
to another page or closing a tab never cancels work. In serverless/ephemeral
deployments run a separate persistent worker instead; request-lifetime
threads are NOT guaranteed to survive there.
"""
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from chapter_chat_context import LessonContextError
from study_session_quiz_runtime import (
    ensure_quiz_runtime_schema, ordered_tasks, preparation_status, prepare_step
)

_lock = threading.Lock()
_thread = None


def stamp():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")


def ensure_job_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_preparation_jobs(
            user_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'queued',
            message TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,subject_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)


def enqueue(conn, project, uid, subject_id):
    ensure_job_schema(conn)
    if not ordered_tasks(conn, uid, subject_id):
        raise LessonContextError(
            "Hãy đưa lộ trình vào Kế hoạch học trước khi chuẩn bị Quiz.", 409)
    items=preparation_status(conn,project,uid,subject_id)
    ready=sum(item["status"]=="ready" for item in items)
    if ready==len(items):
        state="completed"
    else:
        state="queued"
    conn.execute("""
        INSERT INTO quiz_preparation_jobs(
            user_id,subject_id,state,message,updated_at)
        VALUES(?,?,?,'',?)
        ON CONFLICT(user_id,subject_id) DO UPDATE SET
          state=excluded.state,message='',updated_at=excluded.updated_at
    """,(uid,subject_id,state,stamp()))
    conn.commit()
    return state


def pause(conn,uid,subject_id):
    ensure_job_schema(conn)
    row=conn.execute("""
        SELECT state FROM quiz_preparation_jobs
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    if row and row["state"] in ("queued","running"):
        conn.execute("""
            UPDATE quiz_preparation_jobs SET state='paused',updated_at=?
            WHERE user_id=? AND subject_id=?
        """,(stamp(),uid,subject_id))
        conn.commit()
    return "paused" if row and row["state"] in ("queued","running") else (
        row["state"] if row else "not_started")


def status(conn,uid,subject_id):
    ensure_job_schema(conn)
    row=conn.execute("""
        SELECT state,message,updated_at FROM quiz_preparation_jobs
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    return dict(row) if row else {"state":"not_started","message":"",
                                   "updated_at":""}


def tick(project):
    """Process one bounded AI step; no unbounded Gemini call in HTTP route."""
    conn=project.db()
    try:
        ensure_job_schema(conn)
        ensure_quiz_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("""
            SELECT j.user_id,j.subject_id
            FROM quiz_preparation_jobs j
            JOIN subjects s ON s.id=j.subject_id AND s.user_id=j.user_id
            WHERE j.state IN ('queued','running')
            ORDER BY CASE j.state WHEN 'running' THEN 0 ELSE 1 END,
                     j.updated_at ASC LIMIT 1
        """).fetchone()
        if not row:
            conn.rollback()
            return False
        uid,sid=row["user_id"],row["subject_id"]
        conn.execute("""
            UPDATE quiz_preparation_jobs
            SET state='running',updated_at=?
            WHERE user_id=? AND subject_id=?
        """,(stamp(),uid,sid))
        conn.commit()
        try:
            outcome=prepare_step(project,conn,uid,sid)
            new_state="completed" if outcome.get("done") else "queued"
            message=""
        except (LessonContextError,ValueError,RuntimeError) as error:
            conn.rollback()
            new_state="error"
            message=str(getattr(error,"message",error))[:280]
        # Keep a pause request made during Gemini; never unpause implicitly.
        conn.execute("""
            UPDATE quiz_preparation_jobs SET state=?,message=?,updated_at=?
            WHERE user_id=? AND subject_id=? AND state='running'
        """,(new_state,message,stamp(),uid,sid))
        conn.commit()
        return True
    finally:
        conn.close()


def _serve(project):
    while True:
        try:
            worked=tick(project)
        except Exception:
            # An unexpected error must not terminate the worker forever.
            worked=False
        time.sleep(0.25 if worked else 1.0)


def start_local_worker(project):
    """Start at most one daemon on persistent local Flask processes."""
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _thread=threading.Thread(
            target=_serve,args=(project,),name="quiz-preparation-worker",
            daemon=True)
        _thread.start()


def run_forever(project):
    """Optional separate persistent worker: python quiz_preparation_worker.py."""
    _serve(project)
