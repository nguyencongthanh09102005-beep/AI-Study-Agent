"""C4: same official syllabus analysed once, reused across students, metrics truthful."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app as project
from shared_analysis_cache import ensure_schema


def check():
    original_db,original_dir=project.DB_PATH,project.UPLOAD_DIR
    original_gemini=project.gemini_generate
    syllabus="""ĐỀ CƯƠNG HỌC PHẦN
Chương 1. Giới thiệu cấu trúc dữ liệu và giải thuật
1.1. Tổng quan và các thuật toán
Chương 2. Danh sách liên kết và con trỏ
2.1. Node và con trỏ next
""".strip()
    calls=[]
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH=Path(folder)/"cached.sqlite"
            project.UPLOAD_DIR=Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_schema(conn)
            now=project.now()
            def make_user(name,role):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """,(name,name+"@cache.local","hash",role,now)).lastrowid
            a,b,admin=make_user("CacheA","student"),make_user("CacheB","student"),make_user("CacheAdmin","admin")
            shared=conn.execute("""
                INSERT INTO shared_subjects(
                    subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?, ?,1,?,?)
            """,(project._normalize_subject_key("CACHE101","Thuật toán"),
                 "CACHE101","Thuật toán",syllabus,now,now)).lastrowid
            subjects=[]
            for uid in (a,b):
                sid=conn.execute("""
                    INSERT INTO subjects(user_id,name,code,created_at,shared_subject_id)
                    VALUES(?,'Thuật toán','CACHE101',?,?)
                """,(uid,now,shared)).lastrowid
                subjects.append(sid)
            conn.commit()
            def client(uid):
                c=project.app.test_client()
                with c.session_transaction() as sess:
                    sess["user_id"]=uid
                return c
            ca,cb,manager=client(a),client(b),client(admin)
            no_access=ca.get("/admin/shared-cache-metrics")
            assert no_access.status_code==403
            initial=manager.get("/admin/shared-cache-metrics")
            assert initial.status_code==200
            assert initial.get_json()["cache_hit_count"]==0
            project.gemini_generate=lambda prompt:(
                calls.append(prompt) or json.dumps(
                    {"chapters":[{"evidence":"Chương 1. Giới thiệu cấu trúc dữ liệu và giải thuật"}]},
                    ensure_ascii=False
                ),None
            )
            with patch.dict(project.os.environ,{"GEMINI_API_KEY":"fake-test-key"}):
                for cli,sid in ((ca,subjects[0]),(cb,subjects[1])):
                    path=f"/subjects/{sid}/syllabus"
                    assert cli.get(path).status_code==200
                    with cli.session_transaction() as sess:
                        csrf=sess["syllabus_csrf_token"]
                    res=cli.post(path,data={"csrf_token":csrf,"action":"analyze"})
                    assert res.status_code==303
                    page=cli.get(path).get_data(as_text=True)
                    assert "Chương 1" in page and "Chương 2" in page
                    if cli is cb:
                        assert "Chương 2" in page  # Same verified chapters for both students.
            assert len(calls)==1,"Shared source should not call Gemini again"
            stats=manager.get("/admin/shared-cache-metrics").get_json()
            assert stats["cache_hit_count"]==1,stats
            assert stats["first_analysis_gemini_call_count"]==1
            assert stats["total_entries"]==1
            assert stats["entries"][0]["shared_subject_id"]==shared
            assert all("user_id" not in entry and "document_text" not in entry
                       for entry in stats["entries"])
            # Source edit invalidates the cache: no reuse of an old syllabus.
            revised=syllabus.replace("Chương 2. Danh sách liên kết và con trỏ",
                                     "Chương 2. Mảng và bộ nhớ")
            conn.execute("UPDATE shared_subjects SET syllabus_text=? WHERE id=?",
                         (revised,shared))
            conn.commit()
            with patch.dict(project.os.environ,{"GEMINI_API_KEY":"fake-test-key"}):
                path=f"/subjects/{subjects[1]}/syllabus"
                with cb.session_transaction() as sess:
                    csrf=sess["syllabus_csrf_token"]
                assert cb.post(path,data={
                    "csrf_token":csrf,"action":"analyze"
                }).status_code==303
            assert len(calls)==2
            stats=manager.get("/admin/shared-cache-metrics").get_json()
            assert stats["total_entries"]==2
            assert stats["cache_hit_count"]==1
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=original_db,original_dir
        project.gemini_generate=original_gemini
    print("C4 Shared cache PASS: one initial Gemini call, one real reuse, stale version invalidation and Admin ACL")


if __name__=="__main__":
    check()
