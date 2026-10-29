"""Phase 7.2-7.4: durable, per-request Quiz preparation and scheduled access.

No unbounded background worker or timer-based server task: the browser drives
one bounded preparation step at a time; progress is durable in SQLite. Quiz
answers are never returned before the server grants an in-window attempt.
"""
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

STUDY_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def study_now():
    """The study planner stores naive Vietnam-local date/times."""
    return datetime.now(STUDY_TIMEZONE).replace(tzinfo=None)

from chapter_chat_context import LessonContextError
from chapter_tutor import prepared_sources
from study_session_chat_context import verified_study_session
from study_session_quiz import (
    ensure_session_quiz_schema, get_session_quiz_context, link_generated_quiz,
)


def ensure_quiz_runtime_schema(conn):
    ensure_session_quiz_schema(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_preparation_parts (
          task_id INTEGER NOT NULL,
          source_task_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          source_signature TEXT NOT NULL,
          questions_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(task_id,source_task_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_preparation_claims (
          task_id INTEGER PRIMARY KEY,
          user_id INTEGER NOT NULL,
          step_key TEXT NOT NULL,
          claimed_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS quiz_session_grants (
          quiz_id INTEGER NOT NULL,
          user_id INTEGER NOT NULL,
          started_at TEXT NOT NULL,
          valid_until TEXT NOT NULL,
          PRIMARY KEY(quiz_id,user_id)
        )
    """)


def ordered_tasks(conn, uid, subject_id):
    return conn.execute("""
        SELECT id,roadmap_session_id,study_at,duration,done
        FROM study_tasks WHERE user_id=? AND subject_id=?
          AND source='roadmap' AND roadmap_session_id IS NOT NULL
        ORDER BY roadmap_session_id,id
    """, (uid, subject_id)).fetchall()


def context_for_task(project, conn, uid, task_id):
    identity = verified_study_session(project, conn, uid, task_id)
    tasks = ordered_tasks(conn, uid, identity["subject_id"])
    ids = [int(t["id"]) for t in tasks]
    if task_id not in ids:
        raise LessonContextError("Buổi học chưa được đưa vào lịch.", 409)
    is_final = len(ids) >= 2 and ids[-1] == task_id
    if not is_final:
        return get_session_quiz_context(project, conn, uid, task_id), [], 15
    # The final quiz assesses ONLY the earlier sessions (not the last).
    if len(ids) - 1 > 60:
        raise LessonContextError(
            "Lộ trình có hơn 60 buổi trước bài tổng kết, không thể kiểm tra đủ "
            "mỗi buổi với 60 câu. Cần điều chỉnh lộ trình.", 409
        )
    contexts = [get_session_quiz_context(project, conn, uid, tid)
                for tid in ids[:-1]]
    missing = [i + 1 for i, item in enumerate(contexts) if not item["ready"]]
    if missing:
        raise LessonContextError(
            "Chưa đủ học liệu Admin duyệt cho các buổi trước: " +
            ", ".join(str(x) for x in missing[:15]), 409
        )
    # The final slot may have no materials itself; only the preceding 17
    # sessions' current source signatures authorize the comprehensive Quiz.
    signature = hashlib.sha256(json.dumps({
        "final_task": task_id, "final_session": identity["task_signature"],
        "prior": [(c["task_id"], c["source_signature"]) for c in contexts],
    }, sort_keys=True).encode("utf-8")).hexdigest()
    chapter = identity["chapter_number"]
    context = {
        "ready": True, "task_id": task_id, "subject_id": identity["subject_id"],
        "chapter_number": chapter, "session_title": identity["lesson"]["title"],
        "task_signature": identity["task_signature"],
        "source_signature": signature,
        "source_ids": sorted(set(i for c in contexts for i in c["source_ids"])),
        "source_names": list(dict.fromkeys(n for c in contexts
                                           for n in c["source_names"])),
    }
    return context, contexts, 60


def source_content(conn, context):
    """Only previously verified and currently approved source IDs; no syllabus
    header/teacher metadata and no student's private docs are passed to Gemini."""
    rows = []
    for source_id in context["source_ids"]:
        r = conn.execute("""
            SELECT id,original_name,extracted_text
            FROM shared_documents WHERE id=? AND is_syllabus=0
        """, (source_id,)).fetchone()
        if r and (r["extracted_text"] or "").strip():
            rows.append(r)
    query = " ".join(context.get("topics") or context.get("objectives") or [])
    excerpts = prepared_sources(rows, question=query)
    if not excerpts:
        raise LessonContextError("Chưa có nội dung học liệu được duyệt để ra đề.", 409)
    text = "\n".join(e["excerpt"][:4000] for e in excerpts)
    if len(text.strip()) < 40:
        raise LessonContextError("Học liệu quá ngắn để tạo câu hỏi học thuật.", 409)
    return text[:12000]


def _question_key(q):
    return " ".join(str(q.get("question") or "").casefold().split())


def saved_quiz(conn, uid, task_id, source_signature):
    return conn.execute("""
        SELECT q.id,q.title,q.payload
        FROM quiz_session_links l JOIN quizzes q ON q.id=l.quiz_id
        WHERE l.user_id=? AND l.task_id=? AND l.source_signature=?
          AND q.user_id=? AND q.subject_id=l.subject_id
        ORDER BY q.id DESC LIMIT 1
    """, (uid, task_id, source_signature, uid)).fetchone()


def _question_count_valid(questions, count):
    return (isinstance(questions, list) and len(questions) == count and
            len({_question_key(q) for q in questions}) == count and
            all(isinstance(q, dict) and
                isinstance(q.get("options"), list) and
                len(q["options"]) == 4 and
                type(q.get("answer")) is int and
                0 <= q["answer"] <= 3 for q in questions))


def _persist_quiz(project, conn, uid, context, questions, count):
    if not _question_count_valid(questions, count):
        raise LessonContextError("AI chưa tạo đủ câu hỏi chất lượng và không trùng nhau.", 409)
    old = saved_quiz(conn, uid, context["task_id"], context["source_signature"])
    if old:
        return old["id"]
    title = ("Tổng hợp cuối môn · " if count == 60 else "Kiểm tra buổi học · ")
    title += str(context["session_title"])[:145]
    quiz_id = conn.execute("""
        INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
        VALUES(?,?,NULL,?,?,?)
    """, (uid, context["subject_id"], title,
          json.dumps(questions, ensure_ascii=False), project.now())).lastrowid
    link_generated_quiz(conn, uid, quiz_id, context, project.now())
    return quiz_id


def _quota(index, count):
    n = 60 // count
    return n + (1 if index < 60 % count else 0)


def _progress(conn, project, uid, subject_id):
    tasks = ordered_tasks(conn, uid, subject_id)
    status = []
    for task in tasks:
        try:
            ctx, prior, count = context_for_task(project, conn, uid, task["id"])
            existing = saved_quiz(conn, uid, task["id"], ctx["source_signature"])
            if existing:
                status.append({"task_id": task["id"], "status": "ready",
                               "count": count, "quiz_id": existing["id"]})
            elif prior:
                parts = conn.execute("""
                    SELECT COUNT(*) FROM quiz_preparation_parts
                    WHERE task_id=? AND user_id=?
                """, (task["id"], uid)).fetchone()[0]
                status.append({"task_id": task["id"], "status": "pending",
                               "prepared_parts": parts, "total_parts": len(prior),
                               "count": count})
            else:
                status.append({"task_id": task["id"], "status": "pending",
                               "count": count})
        except LessonContextError as err:
            status.append({"task_id": task["id"], "status": "blocked",
                           "reason": err.message})
    return status


def preparation_status(conn, project, uid, subject_id):
    return _progress(conn, project, uid, subject_id)



def per_lesson_quiz_status(conn, project, uid, task_id):
    """Public-safe status for one verified room, never question/answer payload.

    Check the current syllabus and Admin-approved material every time. A
    prepared quiz is NOT the same as an open quiz: only quiz_access decides
    if the student may actually start or see questions.
    """
    ensure_quiz_runtime_schema(conn)
    try:
        context, preceding, count = context_for_task(project, conn, uid, task_id)
    except LessonContextError as err:
        return {"state": "blocked", "count": 0, "reason": err.message,
                "quiz_id": None}
    result = {
        "state": "unprepared", "quiz_id": None, "count": count,
        "is_final": bool(preceding), "reason": "",
        "study_at": "", "ends_at": "", "can_start": False,
        "attempt_count": 0, "best_score": None,
    }
    if not context.get("ready"):
        result.update(state="blocked",
                      reason=context.get("reason") or
                      "Chưa đủ học liệu chung được duyệt.")
        return result
    quiz = saved_quiz(conn, uid, task_id, context["source_signature"])
    if not quiz:
        if preceding:
            valid_parts = sum(
                1 for i, c in enumerate(preceding)
                if _part_valid(conn, uid, task_id, c,
                               _quota(i, len(preceding)))
            )
            result["prepared_parts"] = valid_parts
            result["total_parts"] = len(preceding)
        return result

    access = quiz_access(conn, project, uid, quiz["id"])
    result.update(
        quiz_id=int(quiz["id"]),
        can_start=bool(access.get("can_start")),
        study_at=access.get("study_at", ""),
        ends_at=access.get("ends_at", ""),
        reason=access.get("reason", ""),
        state=("active" if access.get("allowed") else
               "available" if access.get("can_start") else "locked"),
    )
    row = conn.execute("""
        SELECT COUNT(*) AS attempts,MAX(score) AS best_score
        FROM quiz_attempts WHERE quiz_id=? AND user_id=?
    """, (quiz["id"], uid)).fetchone()
    result["attempt_count"] = int(row["attempts"] or 0)
    result["best_score"] = row["best_score"]
    return result

def prepare_step(project, conn, uid, subject_id):
    """Do at most one bounded AI operation; safe to resume after interruption."""
    tasks = ordered_tasks(conn, uid, subject_id)
    if not tasks:
        raise LessonContextError(
            "Hãy đưa lộ trình vào Kế hoạch học trước khi chuẩn bị Quiz.", 409)
    for task in tasks:
        task_id = task["id"]
        ctx, prior, count = context_for_task(project, conn, uid, task_id)
        if not ctx["ready"]:
            raise LessonContextError(ctx.get("reason") or "Nguồn chưa sẵn sàng.", 409)
        if saved_quiz(conn, uid, task_id, ctx["source_signature"]):
            continue
        if prior:
            index = next((i for i, c in enumerate(prior)
                          if not _part_valid(conn, uid, task_id, c,
                                             _quota(i, len(prior)))), None)
            if index is None:
                all_questions = []
                for c in prior:
                    row = conn.execute("""
                        SELECT questions_json FROM quiz_preparation_parts
                        WHERE task_id=? AND user_id=? AND source_task_id=?
                          AND source_signature=?
                    """, (task_id, uid, c["task_id"],
                          c["source_signature"])).fetchone()
                    all_questions.extend(json.loads(row["questions_json"]))
                if not _question_count_valid(all_questions, 60):
                    raise LessonContextError(
                        "Có câu hỏi tổng hợp trùng hoặc thiếu. Cần chuẩn bị lại.", 409)
                _persist_quiz(project, conn, uid, ctx, all_questions, 60)
                conn.execute("DELETE FROM quiz_preparation_parts WHERE task_id=? AND user_id=?",
                             (task_id, uid))
                conn.commit()
                return {"done": False, "task_id": task_id, "status": "ready"}
            part_context = prior[index]
            count = _quota(index, len(prior))
            key = str(part_context["task_id"]) + ":" + part_context["source_signature"]
            source_ctx = part_context
        else:
            count = 15
            key = "quiz:" + ctx["source_signature"]
            source_ctx = ctx
        # Claim BEFORE calling Gemini to avoid two browser tabs generating
        # the same expensive Quiz. 15-minute lease; crash recovery on retry.
        claimed = datetime.now()
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""
            SELECT step_key,claimed_at FROM quiz_preparation_claims
            WHERE task_id=? AND user_id=?
        """, (task_id, uid)).fetchone()
        if row and row["step_key"] == key:
            try:
                age = (claimed - datetime.fromisoformat(row["claimed_at"])).total_seconds()
            except (TypeError, ValueError):
                age = 999999
            if age < 900:
                conn.rollback()
                raise LessonContextError(
                    "Gemini đang chuẩn bị buổi này ở một phiên khác.", 409)
        conn.execute("""
            INSERT INTO quiz_preparation_claims(task_id,user_id,step_key,claimed_at)
            VALUES(?,?,?,?)
            ON CONFLICT(task_id) DO UPDATE SET
              user_id=excluded.user_id,step_key=excluded.step_key,
              claimed_at=excluded.claimed_at
        """, (task_id, uid, key, claimed.isoformat(timespec="seconds")))
        conn.commit()
        try:
            source = source_content(conn, source_ctx)
            used_before = []
            if prior:
                for existing in conn.execute("""
                    SELECT questions_json FROM quiz_preparation_parts
                    WHERE task_id=? AND user_id=?
                """, (task_id, uid)):
                    try:
                        used_before.extend(
                            q.get("question", "") for q in
                            json.loads(existing["questions_json"]) if isinstance(q, dict)
                        )
                    except (ValueError, TypeError):
                        pass
            questions = project.build_quiz(
                source, count, session_mode=True,
                avoid_questions=used_before
            )
            previous_keys = {" ".join(q.casefold().split()) for q in used_before}
            if any(_question_key(q) in previous_keys for q in questions):
                raise LessonContextError(
                    "Câu hỏi bị trùng với buổi trước trong đề tổng hợp; "
                    "hãy thử tạo lại phần này.", 409)
            # The approved chapter for the verified lesson takes precedence
            # over a model's free-form chapter label. This matters especially
            # for the 60-question final exam spanning many prior lessons.
            verified_chapter = str(source_ctx.get("chapter") or "").strip()
            if verified_chapter:
                for question in questions:
                    if isinstance(question, dict):
                        question["chapter"] = verified_chapter[:120]
            if not _question_count_valid(questions, count):
                raise LessonContextError(
                    "Gemini chưa tạo đủ câu hỏi kiến thức hợp lệ. "
                    "Nguồn không bị thay đổi; bạn có thể thử chuẩn bị lại.", 409)
            # Revalidate source state after external request, not only before.
            new_ctx, new_prior, _ = context_for_task(project, conn, uid, task_id)
            if new_ctx["source_signature"] != ctx["source_signature"]:
                raise LessonContextError(
                    "Nguồn/lộ trình đã đổi trong lúc tạo. Vui lòng chuẩn bị lại.", 409)
            if prior:
                updated = next((x for x in new_prior
                                if x["task_id"] == source_ctx["task_id"]), None)
                if not updated or updated["source_signature"] != source_ctx["source_signature"]:
                    raise LessonContextError("Nguồn học liệu vừa đổi.", 409)
                conn.execute("""
                    INSERT INTO quiz_preparation_parts(
                        task_id,source_task_id,user_id,source_signature,questions_json,created_at)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(task_id,source_task_id) DO UPDATE SET
                        source_signature=excluded.source_signature,
                        questions_json=excluded.questions_json,
                        created_at=excluded.created_at
                """, (task_id, source_ctx["task_id"], uid,
                      source_ctx["source_signature"],
                      json.dumps(questions, ensure_ascii=False), project.now()))
            else:
                _persist_quiz(project, conn, uid, new_ctx, questions, 15)
            conn.execute("DELETE FROM quiz_preparation_claims WHERE task_id=? AND user_id=?",
                         (task_id, uid))
            conn.commit()
            return {"done": False, "task_id": task_id,
                    "status": "prepared", "question_count": count}
        except Exception:
            conn.rollback()
            conn.execute("DELETE FROM quiz_preparation_claims WHERE task_id=? AND user_id=?",
                         (task_id, uid))
            conn.commit()
            raise
    return {"done": True, "status": "ready"}


def _part_valid(conn, uid, task_id, context, count):
    row = conn.execute("""
        SELECT questions_json FROM quiz_preparation_parts
        WHERE task_id=? AND user_id=? AND source_task_id=?
          AND source_signature=?
    """, (task_id, uid, context["task_id"],
          context["source_signature"])).fetchone()
    if not row:
        return False
    try:
        return _question_count_valid(json.loads(row["questions_json"]), count)
    except (ValueError, TypeError):
        return False


def _lesson_window(conn, uid, task_id):
    task = conn.execute("""
        SELECT study_at,duration FROM study_tasks WHERE id=? AND user_id=?
    """, (task_id, uid)).fetchone()
    if not task:
        raise LessonContextError("Buổi học không còn trong lịch.", 409)
    try:
        start = datetime.fromisoformat(task["study_at"])
        duration = int(task["duration"])
        if start.tzinfo or duration < 1 or duration > 1440:
            raise ValueError()
    except (ValueError, TypeError):
        raise LessonContextError("Lịch học không có giờ hợp lệ.", 409)
    return start, start + timedelta(minutes=duration)


def quiz_access(conn, project, uid, quiz_id, at=None):
    """Server-side gate for all legacy Web/Mobile Quiz read + submit routes."""
    ensure_quiz_runtime_schema(conn)
    link = conn.execute("""
        SELECT * FROM quiz_session_links WHERE quiz_id=? AND user_id=?
    """, (quiz_id, uid)).fetchone()
    if not link:
        return {"linked": False, "allowed": True}
    # A deleted subject retains Quiz answers/scores as private archives.
    # Keep those answers locked even after its subject/task is unclassified.
    if link["subject_id"] is None:
        return {"linked": True, "allowed": False,
                "reason": "Quiz thuộc môn học đã xóa và được lưu trữ an toàn."}
    if link["task_id"] is None:
        return {"linked": True, "allowed": False, "reason": "Buổi học đã bị xóa."}
    try:
        ctx, _, count = context_for_task(project, conn, uid, link["task_id"])
    except LessonContextError as err:
        return {"linked": True, "allowed": False, "reason": err.message}
    if (ctx["source_signature"] != link["source_signature"] or
            ctx["task_signature"] != link["session_signature"]):
        return {"linked": True, "allowed": False,
                "reason": "Nguồn hoặc nội dung lộ trình đã thay đổi."}
    at = at or study_now()
    grant = conn.execute("""
        SELECT started_at,valid_until FROM quiz_session_grants
        WHERE quiz_id=? AND user_id=?
    """, (quiz_id, uid)).fetchone()
    if (grant and datetime.fromisoformat(grant["started_at"]) <= at
            < datetime.fromisoformat(grant["valid_until"])):
        return {"linked": True, "allowed": True, "count": count}
    start, end = _lesson_window(conn, uid, link["task_id"])
    return {"linked": True, "allowed": False, "count": count,
            "can_start": start <= at < end,
            "study_at": start.isoformat(timespec="minutes"),
            "ends_at": end.isoformat(timespec="minutes"),
            "reason": ("Chưa đến giờ mở bài kiểm tra." if at < start
                       else "Đã hết khung giờ kiểm tra.")}


def start_quiz(conn, project, uid, quiz_id, at=None):
    at = at or study_now()
    status = quiz_access(conn, project, uid, quiz_id, at)
    if not status["linked"]:
        raise LessonContextError("Đây không phải Quiz theo buổi.", 404)
    if status["allowed"]:
        return status
    if not status.get("can_start"):
        raise LessonContextError(status.get("reason") or "Quiz đang khóa.", 409)
    link = conn.execute("""
        SELECT task_id FROM quiz_session_links WHERE quiz_id=? AND user_id=?
    """, (quiz_id, uid)).fetchone()
    _, end = _lesson_window(conn, uid, link["task_id"])
    conn.execute("""
        INSERT INTO quiz_session_grants(quiz_id,user_id,started_at,valid_until)
        VALUES(?,?,?,?)
        ON CONFLICT(quiz_id,user_id) DO UPDATE SET
            started_at=excluded.started_at,valid_until=excluded.valid_until
    """, (quiz_id, uid, at.isoformat(timespec="seconds"),
          end.isoformat(timespec="seconds")))
    return quiz_access(conn, project, uid, quiz_id, at)
