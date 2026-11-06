"""7.6: durable server-side Quiz preparation jobs on persistent Flask hosts.

A browser submits only one job. A single application worker performs bounded
prepare_step calls. SQLite contains the queue and partial Quiz data, so moving
to another page or closing a tab never cancels work. In serverless/ephemeral
deployments run a separate persistent worker instead; request-lifetime
threads are NOT guaranteed to survive there.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from chapter_chat_context import LessonContextError
from quiz_provider_limits import QuizRateLimitError
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
            retry_after TEXT NOT NULL DEFAULT '',
            rate_limit_attempts INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id,subject_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE CASCADE
        )
    """)
    fields = {row["name"] for row in conn.execute(
        "PRAGMA table_info(quiz_preparation_jobs)")}
    if "retry_after" not in fields:
        conn.execute("ALTER TABLE quiz_preparation_jobs ADD COLUMN retry_after TEXT NOT NULL DEFAULT ''")
    if "rate_limit_attempts" not in fields:
        conn.execute("ALTER TABLE quiz_preparation_jobs ADD COLUMN rate_limit_attempts INTEGER NOT NULL DEFAULT 0")


def enqueue(conn, project, uid, subject_id):
    ensure_job_schema(conn)
    if not ordered_tasks(conn, uid, subject_id):
        raise LessonContextError(
            "Hãy đưa lộ trình vào Kế hoạch học trước khi chuẩn bị Quiz.", 409)
    items=preparation_status(conn,project,uid,subject_id)
    handled=sum(item["status"] in ("ready","archived") for item in items)
    if handled==len(items):
        state="completed"
    else:
        state="queued"
    conn.execute("""
        INSERT INTO quiz_preparation_jobs(
            user_id,subject_id,state,message,updated_at,retry_after,rate_limit_attempts)
        VALUES(?,?,?,'',?,'',0)
        ON CONFLICT(user_id,subject_id) DO UPDATE SET
          state=excluded.state,message='',updated_at=excluded.updated_at,
          retry_after='',rate_limit_attempts=0
    """,(uid,subject_id,state,stamp()))
    conn.commit()
    return state


def pause(conn,uid,subject_id):
    ensure_job_schema(conn)
    row=conn.execute("""
        SELECT state FROM quiz_preparation_jobs
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    if row and row["state"] in ("queued","running","cooldown"):
        conn.execute("""
            UPDATE quiz_preparation_jobs SET state='paused',updated_at=?
            WHERE user_id=? AND subject_id=?
        """,(stamp(),uid,subject_id))
        conn.commit()
    return "paused" if row and row["state"] in ("queued","running","cooldown") else (
        row["state"] if row else "not_started")


def local_worker_alive():
    """Whether this Flask process hosts an active local preparation worker."""
    return bool(_thread and _thread.is_alive())


def status(conn,uid,subject_id):
    ensure_job_schema(conn)
    row=conn.execute("""
        SELECT state,message,updated_at,retry_after,rate_limit_attempts FROM quiz_preparation_jobs
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    result = dict(row) if row else {"state":"not_started","message":"",
                                    "updated_at":"","retry_after":"",
                                    "rate_limit_attempts":0}
    # SQLite jobs survive a process restart. A local Flask host that did not
    # restart its worker must let the student resume instead of showing an
    # indefinitely disabled "AI is working" button. A dedicated worker is
    # tracked outside this Flask process; set QUIZ_WORKER_MODE=external there.
    external = os.getenv("QUIZ_WORKER_MODE", "local").lower() == "external"
    result["resume_available"] = (
        not external and result["state"] in ("queued", "running")
        and not local_worker_alive()
    )
    return result


def tick(project):
    """Process one bounded AI step; no unbounded Gemini call in HTTP route."""
    conn=project.db()
    try:
        ensure_job_schema(conn)
        ensure_quiz_runtime_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("""
            SELECT j.user_id,j.subject_id,j.rate_limit_attempts
            FROM quiz_preparation_jobs j
            JOIN subjects s ON s.id=j.subject_id AND s.user_id=j.user_id
            WHERE j.state IN ('queued','running')
               OR (j.state='cooldown' AND j.retry_after<=?)
            ORDER BY CASE j.state WHEN 'running' THEN 0 ELSE 1 END,
                     j.updated_at ASC LIMIT 1
        """, (stamp(),)).fetchone()
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
            retry_after=''
            attempts=0
        except QuizRateLimitError:
            conn.rollback()
            attempts=int(row['rate_limit_attempts'] or 0)+1
            # Limit automatic retry cycles, so a daily quota exhaustion does
            # not spin indefinitely. A manual resume resets this counter.
            if attempts>=3:
                new_state='paused'
                retry_after=''
                message=('Dịch vụ AI tiếp tục giới hạn API (HTTP 429) sau 3 lần chờ. '
                         'Đã tạm dừng để tránh gọi tốn quota; thử lại sau hoặc '
                         'kiểm tra hạn mức API.')
            else:
                delay=180*(2**(attempts-1))
                retry_after=(datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))+
                             timedelta(seconds=delay)).isoformat(timespec='seconds')
                new_state='cooldown'
                message=(f'Dịch vụ AI giới hạn API (HTTP 429). Tự thử lại sau '
                         f'{delay} giây; đã giữ nguyên Quiz và câu hỏi nháp.')
        except (LessonContextError,ValueError,RuntimeError) as error:
            retry_after=''
            attempts=0
            conn.rollback()
            new_state="error"
            message=str(getattr(error,"message",error))[:280]
        except Exception:
            retry_after=''
            attempts=0
            # Unexpected network/SDK errors must not leave a job 'running'
            # forever and trigger repeated Gemini calls on the next tick.
            conn.rollback()
            logging.exception("Unexpected Quiz preparation error for subject %s", sid)
            new_state="error"
            message="Quá trình tạo Quiz bị gián đoạn. Hãy thử Tiếp tục tạo Quiz."
        # Keep a pause request made during Gemini; never unpause implicitly.
        conn.execute("""
            UPDATE quiz_preparation_jobs
            SET state=?,message=?,updated_at=?,retry_after=?,rate_limit_attempts=?
            WHERE user_id=? AND subject_id=? AND state='running'
        """,(new_state,message,stamp(),retry_after,attempts,uid,sid))
        conn.commit()
        return True
    finally:
        conn.close()


def _serve(project):
    while True:
        try:
            worked=tick(project)
        except Exception:
            # A broken DB/worker error should be visible in server logs.
            logging.exception("Quiz preparation worker tick failed")
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
