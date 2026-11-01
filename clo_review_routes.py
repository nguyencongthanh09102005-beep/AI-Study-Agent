"""C2: explainable CLO coverage and evidence, never an automatic official grade.

Only student-confirmed syllabi and user-confirmed CLO/chapter links are used.
Quiz evidence is computed from the most recent saved attempt per quiz with
chapter-labelled questions. Exercise feedback is counted as activity, not points.
"""
import json
import re
import secrets
import hmac
import sys

from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from course_path_learning import parse_chapter_details, CLO_RE
from syllabus_learning import syllabus_hash
from syllabus_routes import _source, ensure_syllabus_schema
from quiz_learning_analysis import summarize_quiz_attempt
from chapter_exercise_routes import ensure_exercise_schema

clo_review_bp = Blueprint("clo_review", __name__)


def ensure_clo_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clo_mapping_reviews(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
            syllabus_hash TEXT NOT NULL,
            mappings_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,subject_id)
        )
    """)


def _valid_clos(source):
    # Limit defensive parsing; never invent CLO codes missing from the PDF.
    values = []
    for match in CLO_RE.finditer(source or ""):
        found = "CLO" + re.search(r"\d+", match.group()).group()
        if found not in values and len(values) < 30:
            values.append(found)
    return values


def _syllabus(project, conn, uid, subject_id):
    subject = conn.execute(
        "SELECT * FROM subjects WHERE id=? AND user_id=?",
        (subject_id,uid),
    ).fetchone()
    if not subject:
        return None
    role=conn.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
    if not role or role["role"] != "student":
        return None
    ensure_syllabus_schema(conn)
    ensure_clo_schema(conn)
    ensure_exercise_schema(conn)
    _, source, source_name = _source(project,conn,uid,subject_id)
    fingerprint=syllabus_hash(source) if source else ""
    confirmed=conn.execute("""
        SELECT units_json,status,source_hash FROM syllabus_reviews
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    if not confirmed or confirmed["status"] != "confirmed" or confirmed["source_hash"] != fingerprint:
        return {"subject":subject,"stale":True}
    sections=parse_chapter_details(source,json.loads(confirmed["units_json"]))
    allowed=_valid_clos(source)
    saved=conn.execute("""
        SELECT syllabus_hash,mappings_json FROM clo_mapping_reviews
        WHERE user_id=? AND subject_id=?
    """,(uid,subject_id)).fetchone()
    mapping_confirmed=bool(saved and saved["syllabus_hash"]==fingerprint)
    if mapping_confirmed:
        try:
            raw=json.loads(saved["mappings_json"])
        except (ValueError,TypeError):
            raw={}
        mapping={
            str(i+1):[code for code in raw.get(str(i+1),[]) if code in allowed]
            for i in range(len(sections))
        }
    else:
        mapping={
            str(i+1):[code for code in section["clo_refs"] if code in allowed]
            for i,section in enumerate(sections)
        }
    return {"subject":subject,"stale":False,"sections":sections,
            "allowed":allowed,"mapping":mapping,
            "mapping_confirmed":mapping_confirmed,
            "source_hash":fingerprint,"source_name":source_name}


def summarize_clo_evidence(conn, uid, subject_id, details):
    """Read-only aggregation. No invented mastery threshold or inferred CLO tags."""
    chapters={}
    for i,chapter in enumerate(details["sections"],1):
        chapters[i]={"chapter":chapter["chapter"],"correct":0,"total":0,
                     "quizzes":0,"submissions":0,"reviewed":0}
    # The latest attempt for each Quiz avoids double-counting retakes.
    rows=conn.execute("""
        SELECT q.id AS quiz_id,q.payload,qa.answers_json
        FROM quiz_attempts qa JOIN quizzes q
          ON q.id=qa.quiz_id AND q.user_id=qa.user_id
        WHERE q.user_id=? AND q.subject_id=?
        ORDER BY qa.id DESC LIMIT 250
    """,(uid,subject_id)).fetchall()
    from learning_streams import academic_quiz
    seen=set()
    for row in rows:
        # CLO achievement is based solely on verified course-session Quiz
        # and academic review evidence, never optional uploaded PDFs.
        if not academic_quiz(conn, uid, row["quiz_id"]):
            continue
        if row["quiz_id"] in seen:
            continue
        seen.add(row["quiz_id"])
        try:
            report=summarize_quiz_attempt(json.loads(row["payload"]),
                                          json.loads(row["answers_json"]))
        except (ValueError,TypeError):
            continue
        for chapter in report["chapters"]:
            found=re.match(r"^Chương\s+(\d+)$",chapter["name"],re.I)
            if not found:
                continue
            i=int(found.group(1))
            if i in chapters:
                chapters[i]["correct"]+=chapter["correct"]
                chapters[i]["total"]+=chapter["total"]
                chapters[i]["quizzes"]+=1
    exercises=conn.execute("""
        SELECT chapter_number,COUNT(*) AS submissions,
               SUM(CASE WHEN feedback_status='reviewed' THEN 1 ELSE 0 END) AS reviewed
        FROM chapter_exercise_attempts
        WHERE user_id=? AND subject_id=? AND syllabus_hash=?
        GROUP BY chapter_number
    """,(uid,subject_id,details["source_hash"])).fetchall()
    for x in exercises:
        if x["chapter_number"] in chapters:
            chapters[x["chapter_number"]]["submissions"]=x["submissions"]
            chapters[x["chapter_number"]]["reviewed"]=x["reviewed"] or 0
    output=[]
    for code in details["allowed"]:
        linked=[i for i in chapters if code in details["mapping"].get(str(i),[])]
        count=sum(chapters[i]["total"] for i in linked)
        right=sum(chapters[i]["correct"] for i in linked)
        reviewed=sum(chapters[i]["reviewed"] for i in linked)
        submitted=sum(chapters[i]["submissions"] for i in linked)
        if not details["mapping_confirmed"]:
            state="Chưa xác nhận liên kết"
            reason="Cần kiểm tra và xác nhận CLO gắn với từng chương trước khi diễn giải."
        elif not linked:
            state="Chưa có chương liên kết"
            reason="CLO có trong đề cương nhưng chưa được gắn với chương nào."
        elif count<5:
            state="Chưa đủ minh chứng Quiz"
            reason="Cần ít nhất 5 câu đã trả lời có nhãn chương phù hợp để tham khảo."
        elif right/count<0.7:
            state="Nên ôn lại"
            reason="Các lượt Quiz gần nhất theo chương liên quan cho thấy tỷ lệ đúng dưới 70%."
        else:
            state="Có tín hiệu tích cực"
            reason="Tỷ lệ đúng Quiz theo chương liên quan từ 70% trở lên; chưa phải xác nhận đạt CLO."
        output.append({
            "code":code,"chapters":[{"number":i,**chapters[i]} for i in linked],
            "quiz_correct":right,"quiz_total":count,"submitted":submitted,
            "reviewed":reviewed,"state":state,"reason":reason,
        })
    return output


def _csrf():
    session.setdefault("clo_mapping_csrf",secrets.token_hex(24))
    return session["clo_mapping_csrf"]


@clo_review_bp.route("/subjects/<int:subject_id>/clo",methods=["GET","POST"])
def overview(subject_id):
    project=sys.modules[current_app.import_name]
    uid=session.get("user_id")
    if not uid:
        return redirect(url_for("login"))
    conn=project.db()
    try:
        details=_syllabus(project,conn,uid,subject_id)
        if not details:
            return "Không có quyền xem môn học.",404
        if details["stale"]:
            if request.method=="POST":
                return "Đề cương chưa được xác nhận hoặc đã thay đổi.",409
            return redirect(url_for("syllabus.review",subject_id=subject_id),code=303)
        if request.method=="POST":
            if not hmac.compare_digest(str(request.form.get("csrf_token") or ""),_csrf()):
                return "Phiên biểu mẫu không hợp lệ.",403
            mapping={}
            for i in range(1,len(details["sections"])+1):
                values=request.form.getlist("clo_"+str(i))
                if len(values)>30 or len(set(values))!=len(values) or any(
                    v not in details["allowed"] for v in values
                ):
                    return "Mã CLO không nằm trong đề cương đã xác nhận.",400
                mapping[str(i)]=values
            conn.execute("""
                INSERT INTO clo_mapping_reviews(user_id,subject_id,syllabus_hash,mappings_json,updated_at)
                VALUES(?,?,?,?,?)
                ON CONFLICT(user_id,subject_id) DO UPDATE SET
                  syllabus_hash=excluded.syllabus_hash,
                  mappings_json=excluded.mappings_json,
                  updated_at=excluded.updated_at
            """,(uid,subject_id,details["source_hash"],
                 json.dumps(mapping,ensure_ascii=False),project.now()))
            conn.commit()
            return redirect(url_for("clo_review.overview",subject_id=subject_id),code=303)
        evidence=summarize_clo_evidence(conn,uid,subject_id,details)
        return render_template("clo_overview.html",page="subjects",details=details,
                               evidence=evidence,csrf_token=_csrf())
    finally:
        conn.close()
