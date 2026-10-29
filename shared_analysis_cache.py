"""C4: versioned course-wide syllabus analysis cache and honest reuse counters.

No student documents, answers, goals or conversation data are ever cached here.
Only shared subject syllabus units that match the current source are reusable.
Counters measure actual reuse; they do not claim total API cost savings.
"""
import json
from flask import Blueprint, jsonify, redirect, session, url_for
from syllabus_learning import extract_syllabus_units, syllabus_hash

shared_analysis_bp = Blueprint("shared_analysis", __name__)
CACHE_VERSION = 1


def ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shared_syllabus_analysis_cache(
            shared_subject_id INTEGER NOT NULL REFERENCES shared_subjects(id) ON DELETE CASCADE,
            source_hash TEXT NOT NULL,
            parser_version INTEGER NOT NULL,
            units_json TEXT NOT NULL,
            generated_with_gemini INTEGER NOT NULL DEFAULT 0,
            first_elapsed_ms INTEGER NOT NULL DEFAULT 0,
            cache_hits INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_reused_at TEXT DEFAULT '',
            PRIMARY KEY(shared_subject_id,source_hash,parser_version)
        )
    """)


def cached_units(conn, shared_id, text, stamp):
    """Read safely and increment metrics only when verified material is reused."""
    ensure_schema(conn)
    fingerprint = syllabus_hash(text)
    row=conn.execute("""
        SELECT units_json FROM shared_syllabus_analysis_cache
        WHERE shared_subject_id=? AND source_hash=? AND parser_version=?
    """,(shared_id,fingerprint,CACHE_VERSION)).fetchone()
    if not row:
        return None
    try:
        parsed=json.loads(row["units_json"])
    except (ValueError,TypeError):
        return None
    # Revalidate against source, not merely the cache row or model assertion.
    if not parsed or parsed != extract_syllabus_units(text):
        return None
    conn.execute("""
        UPDATE shared_syllabus_analysis_cache
        SET cache_hits=cache_hits+1,last_reused_at=?
        WHERE shared_subject_id=? AND source_hash=? AND parser_version=?
    """,(stamp,shared_id,fingerprint,CACHE_VERSION))
    conn.commit()
    return parsed


def save_units(conn, shared_id, text, units, used_gemini, elapsed_ms, stamp):
    ensure_schema(conn)
    if not units or units != extract_syllabus_units(text):
        return False  # Never cache invented or stale metadata.
    conn.execute("""
        INSERT INTO shared_syllabus_analysis_cache(
            shared_subject_id,source_hash,parser_version,units_json,
            generated_with_gemini,first_elapsed_ms,created_at)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(shared_subject_id,source_hash,parser_version) DO NOTHING
    """,(shared_id,syllabus_hash(text),CACHE_VERSION,
         json.dumps(units,ensure_ascii=False),int(bool(used_gemini)),
         max(0,min(120000,int(elapsed_ms))),stamp))
    conn.commit()
    return True


@shared_analysis_bp.route("/admin/shared-cache-metrics",methods=["GET"])
def metrics():
    import app as project
    uid=session.get("user_id")
    if not uid:
        return redirect(url_for("login",tab="admin"))
    conn=project.db()
    try:
        admin=conn.execute("SELECT role FROM users WHERE id=?",(uid,)).fetchone()
        if not admin or admin["role"] != "admin":
            return jsonify({"error":"Không có quyền truy cập."}),403
        ensure_schema(conn)
        rows=conn.execute("""
            SELECT c.shared_subject_id,ss.code AS subject_code,ss.name AS subject_name,
                   c.parser_version,c.generated_with_gemini,
                   c.first_elapsed_ms,c.cache_hits,c.created_at,c.last_reused_at
            FROM shared_syllabus_analysis_cache c JOIN shared_subjects ss
              ON ss.id=c.shared_subject_id
            ORDER BY c.created_at DESC,c.shared_subject_id DESC LIMIT 100
        """).fetchall()
        records=[dict(row) for row in rows]
        return jsonify({
            "method":"Versioned cache for official course syllabus chapter extraction; "
                     "reuse counts are observed, not hypothetical latency savings.",
            "entries":records,
            "total_entries":len(records),
            "cache_hit_count":sum(x["cache_hits"] for x in records),
            "first_analysis_gemini_call_count":sum(x["generated_with_gemini"] for x in records),
            "note":"Values exclude all personal documents and include only 100 most recent cache versions. "
                   "Compare real latency separately in a controlled benchmark."
        })
    finally:
        conn.close()
