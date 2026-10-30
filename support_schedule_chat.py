"""Conversational Support for student calendar actions.

A restricted Vietnamese intent parser proposes candidate operations; no model
text ever writes the timetable. Every add/move requires server validation,
CSRF, a short-lived explicit proposal and a separate confirm click.
"""
import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, jsonify, request, session
from werkzeug.utils import secure_filename

from adaptive_review_schedule import local_now
from chat_schedule_actions import (
    ScheduleProblem, _check_csrf, _conflicts, _datetime, _snapshot,
    _tasks, _user, _project,
)

support_chat_bp = Blueprint("support_chat", __name__)


@support_chat_bp.errorhandler(ScheduleProblem)
def error(exc):
    return jsonify({"error": exc.message, "suggested_at": exc.suggestion}), exc.status


def _schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS support_chat_messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)


def _csrf():
    session.setdefault("chat_schedule_csrf", secrets.token_urlsafe(32))
    return session["chat_schedule_csrf"]


def _fold(text):
    raw = unicodedata.normalize("NFD", str(text or "").lower())
    return re.sub(r"[^a-z0-9 ]+", " ", "".join(
        ch for ch in raw if not unicodedata.combining(ch)
    ).replace("đ", "d")).strip()


def _subjects(conn, uid):
    return [dict(r) for r in conn.execute(
        "SELECT id,name FROM subjects WHERE user_id=? ORDER BY name,id",
        (uid,)
    )]


def _match_subject(sentence, subjects):
    folded = _fold(sentence)
    matches = []
    for sub in subjects:
        tokens = [w for w in _fold(sub["name"]).split() if len(w) > 2]
        full = " ".join(tokens)
        if (full and full in folded) or (len(tokens) >= 2 and
                " ".join(tokens[:2]) in folded):
            matches.append(sub)
    return sorted(matches, key=lambda x: -len(_fold(x["name"])))[0] if matches else None


def _date_time(message):
    text = unicodedata.normalize("NFD", str(message or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).replace("đ","d")
    # User examples: "31/10 đến 9h tối", "7h tối ngày 1/11".
    match_date = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\b", text)
    if not match_date:
        return None
    day, month = int(match_date[1]), int(match_date[2])
    if match_date[3]:
        year = int(match_date[3])
        inferred = False
    else:
        year = local_now().year
        inferred = True
    match_time = re.search(
        r"\b(\d{1,2})(?:\s*(?:h|gio|:)\s*(\d{1,2})?)?\s*"
        r"(sang|trua|chieu|toi|dem)\b", text
    )
    if not match_time:
        match_time = re.search(r"\b(\d{1,2})\s*(?:h|gio|:)\s*(\d{1,2})?\b", text)
    if not match_time:
        return None
    hour = int(match_time[1])
    minute = int(match_time[2] or 0)
    period = match_time[3] if match_time.lastindex and match_time.lastindex >= 3 else ""
    if hour > 23 or minute > 59:
        return None
    if period in ("toi", "dem", "chieu") and hour < 12:
        hour += 12
    elif period == "sang" and hour == 12:
        hour = 0
    if hour > 23:
        return None
    try:
        chosen = datetime(year, month, day, hour, minute)
        if inferred and chosen <= local_now():
            chosen = chosen.replace(year=year+1)
        return chosen, inferred
    except ValueError:
        return None


def _self_study_topic(raw):
    # Extract an optional title after "môn" rather than allowing an
    # instruction to create an arbitrary study subject.
    found = re.search(
        r"\b(?:môn|mon)\s+(.+?)(?=\s+(?:vào|vao|lúc|luc|ngày|ngay|đến|den)\b|\d{1,2}[/-]\d{1,2}|$)",
        raw, re.I
    )
    if found:
        name = found[1].strip(" .,!?:")[:90]
        if name:
            return name
    found = re.search(r"(?:tự học|tu hoc)\s+(.+?)(?=\s+(?:vào|vao|lúc|luc|ngày|ngay)\b|$)", raw, re.I)
    return (found[1].strip(" .,!?:")[:90] if found else "")


def _reply(conn, uid, user_text, answer):
    project = _project()
    _schema(conn)
    stamp = project.now()
    conn.executemany(
        "INSERT INTO support_chat_messages(user_id,role,content,created_at) VALUES(?,?,?,?)",
        [(uid, "user", user_text, stamp), (uid, "assistant", answer, stamp)]
    )
    conn.commit()


@support_chat_bp.route("/api/chat/support", methods=["GET"])
def history():
    uid = _user()
    conn = _project().db()
    try:
        _schema(conn)
        rows = conn.execute("""
            SELECT role,content,created_at FROM (
                SELECT id,role,content,created_at FROM support_chat_messages
                WHERE user_id=? ORDER BY id DESC LIMIT 40
            ) ORDER BY id ASC
        """, (uid,)).fetchall()
        return jsonify({"messages":[dict(r) for r in rows],
                        "subjects":_subjects(conn, uid), "csrf_token":_csrf()})
    finally:
        conn.close()


@support_chat_bp.route("/api/chat/support/message", methods=["POST"])
def message():
    uid = _user()
    _check_csrf()
    body = request.get_json(silent=True) or {}
    raw = str(body.get("message") or "").strip()
    if not raw or len(raw) > 400:
        raise ScheduleProblem("Hãy nhập yêu cầu ngắn hơn 400 ký tự.")
    normalized = _fold(raw)
    conn = _project().db()
    try:
        subjects = _subjects(conn, uid)
        if any(p in normalized for p in ("ra soat", "trung lich", "trung gio", "kiem tra lich", "dung lich")):
            answer = "Tui sẽ rà soát mọi buổi học sắp tới. Nếu có trùng giờ, bạn sẽ được xem và xác nhận đề xuất."
            result = {"intent":"review"}
        elif (any(p in normalized for p in ("tu hoc", "hoc them", "them buoi", "tao buoi"))):
            parsed = _date_time(raw)
            topic = _self_study_topic(raw)
            if not parsed or not topic:
                answer = "Hãy cho biết nội dung tự học, ngày và giờ. Ví dụ: Cho buổi tự học môn Figma vào 7h tối ngày 1/11."
                result = {"intent":"question"}
            else:
                when, inferred = parsed
                subject = _match_subject(topic, subjects)
                answer = ("Tui đã chuẩn bị buổi tự học. Bạn có thể chọn hoặc tải tài liệu và xem trước khi xác nhận."
                          + (" Chủ nhật là ngày nghỉ mặc định; bạn vẫn được chủ động chọn." if when.weekday()==6 else ""))
                result = {"intent":"create","topic":topic,
                          "subject_id":subject["id"] if subject else None,
                          "study_at":when.isoformat(timespec="minutes"),
                          "duration":60,"inferred_year":inferred,
                          "sunday":when.weekday()==6}
        elif any(p in normalized for p in ("doi", "doi gio", "doi lich", "dieu chinh", "chuyen", "dời", "sua lich")):
            parsed = _date_time(raw)
            if not parsed:
                answer = "Hãy nêu tên môn, ngày và giờ muốn đổi. Ví dụ: Đổi lịch sử Đảng ngày 31/10 đến 9h tối."
                result = {"intent":"question"}
            else:
                when, inferred = parsed
                subject = _match_subject(raw, subjects)
                rows = _tasks(conn, uid)
                date = when.date().isoformat()
                candidates = [
                    dict(row) for row in rows if not row["done"]
                    and str(row["study_at"]).startswith(date)
                    and (not subject or row["subject_id"] == subject["id"])
                ]
                # Show exact title/time to disambiguate same-day lessons.
                choices = []
                for row in candidates[:15]:
                    choices.append({"id":row["id"],"title":row["title"],
                                    "subject_id":row["subject_id"],
                                    "study_at":row["study_at"],
                                    "duration":row["duration"]})
                answer = ("Chọn buổi học cần đổi và xác nhận giờ mới."
                          if choices else
                          "Tui chưa tìm thấy buổi học chưa hoàn thành đúng ngày và môn được nhắc đến.")
                result = {"intent":"reschedule" if choices else "question",
                          "candidates":choices,
                          "study_at":when.isoformat(timespec="minutes"),
                          "inferred_year":inferred}
        else:
            answer = ("Tui hỗ trợ rà soát lịch, đổi thời gian buổi học và thêm buổi tự học. "
                      "Bạn có thể bấm gợi ý hoặc nhắn ngày, giờ cụ thể.")
            result = {"intent":"question"}
        _reply(conn, uid, raw, answer)
        return jsonify({"reply":answer,**result})
    finally:
        conn.close()


@support_chat_bp.route("/api/chat/support/documents", methods=["GET"])
def documents():
    uid = _user()
    conn = _project().db()
    try:
        raw = request.args.get("subject_id")
        subject_id = int(raw) if raw and raw.isdigit() else None
        if subject_id and not conn.execute(
            "SELECT 1 FROM subjects WHERE id=? AND user_id=?",
            (subject_id,uid)
        ).fetchone():
            raise ScheduleProblem("Môn học không thuộc tài khoản.",403)
        rows = conn.execute("""
            SELECT id,original_name,subject_id
            FROM documents WHERE user_id=?
            AND (subject_id=? OR subject_id IS NULL)
            ORDER BY id DESC LIMIT 80
        """, (uid, subject_id)).fetchall()
        return jsonify({"documents":[dict(row) for row in rows]})
    finally:
        conn.close()


@support_chat_bp.route("/api/chat/support/upload", methods=["POST"])
def upload():
    uid = _user()
    _check_csrf()
    project = _project()
    file = request.files.get("file")
    if not file or not file.filename or not project.allowed_file(file.filename):
        raise ScheduleProblem("Chỉ hỗ trợ tệp PDF, DOCX, TXT hoặc MD.")
    raw_subject = request.form.get("subject_id")
    subject_id = int(raw_subject) if raw_subject and raw_subject.isdigit() else None
    conn = project.db()
    target = None
    try:
        if subject_id and not conn.execute(
            "SELECT 1 FROM subjects WHERE id=? AND user_id=?",
            (subject_id,uid)
        ).fetchone():
            raise ScheduleProblem("Môn học không thuộc tài khoản.",403)
        original = secure_filename(file.filename)
        if not original:
            raise ScheduleProblem("Tên file không hợp lệ.")
        stored = f"{uid}_support_{secrets.token_hex(12)}_{original}"
        project.UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
        target = Path(project.UPLOAD_DIR) / stored
        file.save(target)
        content = project.extract_text(target)
        if not content.strip():
            raise ScheduleProblem("Không đọc được văn bản trong file này. PDF scan cần OCR trước.")
        id_ = conn.execute("""
            INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                                  extracted_text,created_at)
            VALUES(?,?,?,?,?,?)
        """, (uid,subject_id,original,stored,content,project.now())).lastrowid
        conn.commit()
        return jsonify({"document":{"id":id_,"original_name":original,
                                     "subject_id":subject_id}}),201
    except Exception:
        conn.rollback()
        if target:
            target.unlink(missing_ok=True)
        raise
    finally:
        conn.close()


def _data(conn, uid, payload):
    topic = str(payload.get("topic") or "").strip()[:90]
    if not topic or len(topic) < 2:
        raise ScheduleProblem("Nội dung tự học cần ít nhất 2 ký tự.")
    duration = payload.get("duration",60)
    if isinstance(duration,bool) or not str(duration).isdigit() or not 15 <= int(duration) <= 180:
        raise ScheduleProblem("Thời lượng phải từ 15 đến 180 phút.")
    start = _datetime(payload.get("study_at"))
    # Manual choices may occur on Sunday or outside suggested 19:00–22:00;
    # warn on the confirmation card but never silently override the user.
    subject = payload.get("subject_id")
    subject_id = int(subject) if str(subject or "").isdigit() else None
    if subject_id and not conn.execute(
        "SELECT 1 FROM subjects WHERE id=? AND user_id=?",
        (subject_id,uid)
    ).fetchone():
        raise ScheduleProblem("Môn tự học không thuộc tài khoản.",403)
    document = payload.get("document_id")
    doc_id = int(document) if str(document or "").isdigit() else None
    if doc_id:
        doc = conn.execute(
            "SELECT subject_id FROM documents WHERE id=? AND user_id=?",
            (doc_id,uid)
        ).fetchone()
        if not doc or doc["subject_id"] not in (None,subject_id):
            raise ScheduleProblem("Tài liệu không thuộc môn tự học đang chọn.",403)
    rows = _tasks(conn, uid)
    collisions, suggestion = _conflicts(rows, -1, start, int(duration))
    if collisions:
        raise ScheduleProblem("Trùng giờ với: "+", ".join(
            row["title"][:60] for row in collisions[:3]),409,suggestion)
    return {"topic":topic,"subject_id":subject_id,"document_id":doc_id,
            "duration":int(duration),"study_at":start.isoformat(timespec="minutes"),
            "sunday":start.weekday()==6,
            "outside_evening":not(19 <= start.hour and
                                 start+timedelta(minutes=int(duration)) <=
                                 start.replace(hour=22, minute=0)),
            "snapshot":_snapshot(rows)}


@support_chat_bp.route("/api/chat/support/create/preview", methods=["POST"])
def create_preview():
    uid = _user()
    _check_csrf()
    session.pop("support_create_proposal",None)
    payload = request.get_json(silent=True) or {}
    conn = _project().db()
    try:
        data = _data(conn,uid,payload)
        nonce = secrets.token_urlsafe(24)
        session["support_create_proposal"] = {
            **data,"uid":uid,"nonce":nonce,
            "created":local_now().isoformat(timespec="seconds")
        }
        return jsonify({"proposal_id":nonce,"title":"Tự học "+data["topic"],
                        "study_at":data["study_at"],"duration":data["duration"],
                        "subject_id":data["subject_id"],
                        "document_id":data["document_id"],
                        "sunday":data["sunday"],
                        "outside_evening":data["outside_evening"],
                        "message":"Chưa tạo lịch. Hãy kiểm tra và xác nhận."})
    finally:
        conn.close()


@support_chat_bp.route("/api/chat/support/create/confirm", methods=["POST"])
def create_confirm():
    uid = _user()
    _check_csrf()
    body = request.get_json(silent=True) or {}
    proposal = session.pop("support_create_proposal",None)
    if not proposal or not secrets.compare_digest(
        str(body.get("proposal_id") or ""), str(proposal.get("nonce") or "")
    ) or proposal["uid"] != uid:
        raise ScheduleProblem("Đề xuất không còn hiệu lực. Hãy xem trước lần nữa.",409)
    if local_now() - datetime.fromisoformat(proposal["created"]) > timedelta(minutes=15):
        raise ScheduleProblem("Đề xuất đã hết hạn. Hãy xem lại.",409)
    project = _project()
    conn = project.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = _data(conn,uid,proposal)
        if current["snapshot"] != proposal["snapshot"]:
            raise ScheduleProblem("Thời khóa biểu hoặc tài liệu đã thay đổi. Hãy xem trước lại.",409)
        subject_id = current["subject_id"]
        if not subject_id:
            # A private-only subject has no Admin syllabus. Create it only at
            # explicit confirmation, never on merely typing a prompt.
            found = conn.execute("""
                SELECT id FROM subjects WHERE user_id=? AND LOWER(name)=LOWER(?)
                ORDER BY id LIMIT 1
            """,(uid,current["topic"])).fetchone()
            if found:
                subject_id = found["id"]
            else:
                subject_id = conn.execute("""
                    INSERT INTO subjects(user_id,name,code,description,credits,created_at)
                    VALUES(?,?,'','Môn tự học cá nhân',0,?)
                """,(uid,current["topic"],project.now())).lastrowid
        doc_id = current["document_id"]
        if doc_id:
            row = conn.execute(
                "SELECT subject_id FROM documents WHERE id=? AND user_id=?",
                (doc_id,uid)
            ).fetchone()
            if not row or row["subject_id"] not in (None,subject_id):
                raise ScheduleProblem("Tài liệu đã thay đổi. Hãy chọn lại.",409)
            if row["subject_id"] is None:
                conn.execute("UPDATE documents SET subject_id=? WHERE id=? AND user_id=?",
                             (subject_id,doc_id,uid))
        title = ("Tự học "+current["topic"])[:160]
        task_id = conn.execute("""
            INSERT INTO study_tasks(
                user_id,subject_id,title,study_at,duration,note,done,source,created_at
            ) VALUES(?,?,?,?,?,'Tự học cá nhân · tạo từ Chat AI Hỗ trợ',0,'manual',?)
        """,(uid,subject_id,title,current["study_at"],
             current["duration"],project.now())).lastrowid
        if doc_id:
            from manual_lesson_routes import attach_document
            attach_document(conn,uid,task_id,subject_id,doc_id,project.now())
        conn.commit()
        return jsonify({"success":True,"task_id":task_id,"subject_id":subject_id,
                        "title":title,"study_at":current["study_at"],
                        "document_id":doc_id})
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
