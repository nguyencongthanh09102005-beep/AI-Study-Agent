"""Mobile roadmap scheduling and private self-study attachments, no external AI.

Use disposable SQLite to verify parity, safe ownership and no silent replacement.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from course_path_learning import build_course_roadmap, parse_chapter_details, unit_fingerprint
from course_path_routes import ensure_roadmap_schema
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema


def run():
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH=Path(folder)/"mobile-parity.sqlite"
            project.UPLOAD_DIR=Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_syllabus_schema(conn)
            ensure_roadmap_schema(conn)
            now=project.now()
            def user(name):
                return conn.execute(
                    "INSERT INTO users(name,email,password_hash,role,created_at) "
                    "VALUES(?,?,?,'student',?)",
                    (name, name+"@example.local","hash",now),
                ).lastrowid
            uid,other=user("mobile-uid"),user("mobile-other")
            def subject(owner,code):
                return conn.execute(
                    "INSERT INTO subjects(user_id,name,code,credits,created_at)"
                    " VALUES(?,?,?,?,?)",
                    (owner,"Môn "+code,code,3,now),
                ).lastrowid
            sid=subject(uid,"PARITY")
            another=subject(uid,"SECOND")
            foreign=subject(other,"OTHER")
            content=("Chương 1. Kiến thức cơ bản\n"
                     "1.1. Khái niệm và ứng dụng\n"
                     "Chương 2. Thực hành\n"
                     "2.1. Các bước thực hành")
            def doc(owner,course,name,body=content):
                return conn.execute(
                    "INSERT INTO documents(user_id,subject_id,original_name,stored_name,"
                    "extracted_text,created_at) VALUES(?,?,?,?,?,?)",
                    (owner,course,name,name,body,now),
                ).lastrowid
            syllabus_doc=doc(uid,sid,"outline.txt")
            personal_doc=doc(uid,sid,"study-private.txt")
            wrong_doc=doc(uid,another,"wrong-course.txt")
            foreign_doc=doc(other,foreign,"other-user.txt")
            conn.execute("UPDATE subjects SET personal_syllabus_document_id=? WHERE id=?",
                         (syllabus_doc,sid))
            units=[
                {"title":"Chương 1. Kiến thức cơ bản","evidence":"Chương 1. Kiến thức cơ bản"},
                {"title":"Chương 2. Thực hành","evidence":"Chương 2. Thực hành"},
            ]
            hash_value=syllabus_hash(content)
            conn.execute(
                "INSERT INTO syllabus_reviews"
                "(user_id,subject_id,source_hash,source_kind,units_json,status,updated_at)"
                " VALUES(?,?,?,?,?,'confirmed',?)",
                (uid,sid,hash_value,"personal",json.dumps(units,ensure_ascii=False),now),
            )
            sessions=build_course_roadmap(
                parse_chapter_details(content,units), [],
                {"goal":"Học tốt","daily_minutes":45,"preferred_time":"09:00","credits":3},
            )
            assert sessions
            conn.execute(
                "INSERT INTO course_roadmaps"
                "(user_id,subject_id,source_hash,units_hash,sessions_json,updated_at)"
                " VALUES(?,?,?,?,?,?)",
                (uid,sid,hash_value,unit_fingerprint(units),
                 json.dumps(sessions,ensure_ascii=False),now),
            )
            legacy=conn.execute(
                "INSERT INTO study_tasks"
                "(user_id,subject_id,title,study_at,duration,note,done,source,created_at)"
                "VALUES(?,?,?,'2026-11-12T19:00',45,'old note',0,'manual',?)",
                (uid,sid,"Giữ nguyên lịch",now),
            ).lastrowid
            conn.commit()
            conn.close()

            client=project.app.test_client()
            outsider=project.app.test_client()
            with client.session_transaction() as state:
                state["user_id"]=uid
                state["user_name"]="Mobile"
            with outsider.session_transaction() as state:
                state["user_id"]=other
                state["user_name"]="Other"

            path=f"/api/mobile/subjects/{sid}/roadmap/schedule"
            assert client.get(f"/api/mobile/subjects/{sid}/roadmap").get_json()["ready"]
            assert client.post(path,json={}).status_code==400
            assert outsider.post(path,json={"confirm":True}).status_code==404
            result=client.post(path,json={"confirm":True})
            assert result.status_code==200, result.get_json()
            assert result.get_json()["summary"]["created"]==len(sessions)
            retry=client.post(path,json={"confirm":True})
            assert retry.status_code==200
            assert retry.get_json()["summary"]["created"]==0
            conn=project.db()
            old=conn.execute("SELECT title,study_at,note FROM study_tasks WHERE id=?",
                             (legacy,)).fetchone()
            assert (old["title"],old["study_at"],old["note"])==(
                "Giữ nguyên lịch","2026-11-12T19:00","old note")
            row=conn.execute(
                "SELECT id FROM study_tasks WHERE user_id=? AND source='roadmap' LIMIT 1",
                (uid,),
            ).fetchone()
            official_id=row["id"]
            assert client.put(f"/api/mobile/tasks/{official_id}",json={
                "subject_id":another,"title":"Chuyển sang môn khác",
                "study_at":"2026-12-03T09:00","duration":45,
            }).status_code==400

            day=(datetime.now()+timedelta(days=2)).strftime("%Y-%m-%dT19:00")
            task_data={"subject_id":sid,"title":"Tự học theo tài liệu",
                       "study_at":day,"duration":45,"note":"Luyện bài"}
            for wrong in [wrong_doc,foreign_doc,987654321]:
                res=client.post("/api/mobile/tasks",json={**task_data,"document_id":wrong})
                assert res.status_code==400, (wrong,res.get_json())

            linked=client.post("/api/mobile/tasks",json={
                **task_data,"document_id":personal_doc
            })
            assert linked.status_code==201,linked.get_json()
            manual_id=linked.get_json()["task"]["id"]
            assert conn.execute(
                "SELECT document_id FROM manual_lesson_documents WHERE task_id=?",
                (manual_id,),
            ).fetchone()["document_id"]==personal_doc
            listing=client.get("/api/mobile/study-plan")
            assert listing.status_code==200
            body=listing.get_json()
            manual=next(t for t in body["tasks"] if t["id"]==manual_id)
            assert manual["document_id"]==personal_doc
            assert manual["personal_document_name"]=="study-private.txt"
            assert manual["roadmap_label"]==""
            assert any(t["roadmap_label"] for t in body["tasks"]
                       if t["source"]=="roadmap"), body["tasks"][:2]
            assert outsider.get("/api/mobile/study-plan").status_code==200
            assert all(t["id"]!=manual_id for t in
                       outsider.get("/api/mobile/study-plan").get_json()["tasks"])
            assert outsider.put(f"/api/mobile/tasks/{manual_id}",json=task_data).status_code==404
            assert client.put(f"/api/mobile/tasks/{manual_id}",json={
                **task_data,"subject_id":another
            }).status_code==400
            assert client.put(f"/api/mobile/tasks/{manual_id}",json={
                **task_data,"document_id":wrong_doc
            }).status_code==400
            assert client.put(f"/api/mobile/tasks/{manual_id}",json={
                **task_data,"study_at":"2026-12-08T20:00",
                "document_id":personal_doc,
            }).status_code==200
            conn.execute(
                "UPDATE course_roadmaps SET units_hash='stale' WHERE user_id=? AND subject_id=?",
                (uid,sid),
            )
            conn.commit()
            blocked=client.post(path,json={"confirm":True})
            assert blocked.status_code==409,blocked.get_json()
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("Mobile roadmap/plan parity PASS: confirm, idempotent, ACL, attachments, stale")


if __name__=="__main__":
    run()
