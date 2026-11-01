"""C1 integration: real chapter syllabus, personal revision history, verified AI citations."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from chapter_material_routes import ensure_chapter_material_schema
from chapter_exercise_routes import ensure_exercise_schema
from syllabus_learning import syllabus_hash
from syllabus_routes import ensure_syllabus_schema


def check():
    old_db,old_upload = project.DB_PATH,project.UPLOAD_DIR
    old_gemini = project.gemini_generate
    syllabus = """ĐỀ CƯƠNG CHI TIẾT
Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán
Thời lượng: 6 tiết | Liên kết chuẩn đầu ra: CLO1
Mục tiêu sau chương
Giải thích độ phức tạp thời gian theo Big O.
Nội dung kiến thức
• 1.1. Khái niệm dữ liệu và thuật toán
• 1.2. Độ phức tạp thuật toán Big O
Bài tập
BT01: Phân tích độ phức tạp của vòng lặp tuyến tính.
Chương 2. Danh sách liên kết
Thời lượng: 6 tiết | Liên kết chuẩn đầu ra: CLO2
Mục tiêu sau chương
Cài đặt danh sách liên kết đơn.
Nội dung kiến thức
• 2.1. Duyệt danh sách
Bài tập
BT02: Nêu cách thêm một node.
"""
    quote = "Vòng lặp tuyến tính duyệt qua n phần tử có độ phức tạp O(n)."
    source = ("Giáo trình thuật toán. Chương 1. " + quote + "\n" +
              "Độ phức tạp O lớn biểu diễn tốc độ tăng của chi phí tính toán.")
    with TemporaryDirectory() as folder:
        try:
            project.DB_PATH = Path(folder)/"practice.sqlite"
            project.UPLOAD_DIR = Path(folder)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            ensure_syllabus_schema(conn)
            ensure_chapter_material_schema(conn)
            ensure_exercise_schema(conn)
            now=project.now()
            def create_user(name,role):
                return conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """,(name,name+"@test.local","hash",role,now)).lastrowid
            uid=create_user("C1Student","student")
            other=create_user("C1Other","student")
            admin=create_user("C1Admin","admin")
            def subject_for(uid,code):
                return conn.execute("""
                    INSERT INTO subjects(user_id,name,code,credits,created_at)
                    VALUES(?,?,?,?,?)
                """,(uid,"Cấu trúc dữ liệu",code,3,now)).lastrowid
            subject=subject_for(uid,"CTDL-C1")
            other_subject=subject_for(other,"CTDL-C1")
            sid=conn.execute("""
                INSERT INTO shared_subjects(
                  subject_key,code,name,syllabus_text,admin_managed,created_at,updated_at)
                VALUES(?,?,?,?,1,?,?)
            """,(project._normalize_subject_key("CTDL-C1","Cấu trúc dữ liệu"),
                 "CTDL-C1","Cấu trúc dữ liệu",syllabus,now,now)).lastrowid
            conn.execute("UPDATE subjects SET shared_subject_id=? WHERE id IN (?,?)",
                         (sid,subject,other_subject))
            document=conn.execute("""
                INSERT INTO shared_documents(
                  shared_subject_id,original_name,stored_name,extracted_text,
                  is_syllabus,created_by_user_id,created_at)
                VALUES(?,?,?,?,0,?,?)
            """,(sid,"slide-chuong-1.txt","slide-c1.txt",source,admin,now)).lastrowid
            hash_=syllabus_hash(syllabus.strip())
            conn.execute("""
                INSERT INTO shared_document_chapters(
                  document_id,shared_subject_id,chapter_key,syllabus_hash,
                  confirmed_by,confirmed_at)
                VALUES(?,?,'1',?,?,?)
            """,(document,sid,hash_,admin,now))
            for student,course in ((uid,subject),(other,other_subject)):
                conn.execute("""
                    INSERT INTO syllabus_reviews(
                      user_id,subject_id,source_hash,source_kind,
                      units_json,status,updated_at)
                    VALUES(?,?,?,'shared',?,'confirmed',?)
                """,(student,course,hash_,
                  json.dumps([
                    {"title":"Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán",
                     "evidence":"Chương 1. Tổng quan cấu trúc dữ liệu và thuật toán"},
                    {"title":"Chương 2. Danh sách liên kết",
                     "evidence":"Chương 2. Danh sách liên kết"}],ensure_ascii=False),now))
            conn.commit()
            conn.close()

            def client(uid):
                c=project.app.test_client()
                with c.session_transaction() as sess:
                    sess["user_id"]=uid
                return c
            student,peer,teacher,guest=client(uid),client(other),client(admin),project.app.test_client()
            url=f"/subjects/{subject}/chapters/1/exercises"
            assert guest.get(url).status_code in (302,303)
            assert teacher.get(url).status_code == 403
            assert peer.get(url).status_code == 404
            page=student.get(url)
            assert page.status_code == 200,page.get_data(as_text=True)[:650]
            html=page.get_data(as_text=True)
            assert "BT01:" in html and "BT02:" not in html
            assert "Nộp và nhờ AI nhận xét" in html
            assert "slide-chuong-1.txt" not in html or "Chương 1" in html
            assert student.post(f"/subjects/{subject}/chapters/1").status_code == 405
            with student.session_transaction() as sess:
                token=sess["chapter_exercise_csrf"]
            body={"csrf_token":token,"exercise_index":"0",
                  "answer":"Vòng lặp chạy từ 0 đến n-1 nên có n thao tác và là O(n)."}
            assert student.post(url,data={**body,"csrf_token":"fake"}).status_code==403
            assert student.post(url,data={**body,"exercise_index":"42"}).status_code==400
            assert student.post(url,data={**body,"answer":"ngắn"}).status_code==400
            saved=student.post(url,data={**body,"action":"save"})
            assert saved.status_code == 303
            conn=project.db()
            first=conn.execute(
                "SELECT * FROM chapter_exercise_attempts WHERE user_id=?",(uid,)
            ).fetchone()
            assert first and first["feedback_status"]=="saved"
            first_id=first["id"]
            conn.close()
            # Peer owns a separate record; cannot request feedback for someone else's.
            peer.get(f"/subjects/{other_subject}/chapters/1/exercises")
            with peer.session_transaction() as sess:
                other_token=sess["chapter_exercise_csrf"]
            assert peer.post(
                f"/subjects/{other_subject}/chapters/1/exercises",
                data={"csrf_token":other_token,"action":"retry",
                      "attempt_id":str(first_id)}
            ).status_code == 404
            peer_history = peer.get(
                f"/subjects/{other_subject}/chapters/1/exercises"
            ).get_data(as_text=True)
            assert "Vòng lặp chạy từ 0 đến n-1" not in peer_history

            calls=[]
            def mocked_gemini(prompt):
                calls.append(prompt)
                return json.dumps({
                    "explanation":"Cách giải đã dùng số lần lặp, nhưng cần nói rõ giả định.",
                    "citations":[{"source_key":"T1","quote":quote}],
                    "practice":"Thử đổi vòng lặp thành hai vòng lồng nhau."
                },ensure_ascii=False),None
            project.gemini_generate=mocked_gemini
            assessed=student.post(url,data={
                "csrf_token":token,"action":"retry","attempt_id":str(first_id)})
            assert assessed.status_code==303
            assert len(calls)==1
            assert "Vòng lặp chạy từ 0" in calls[0]
            seen=student.get(url).get_data(as_text=True)
            assert "Cách giải đã dùng số lần lặp" in seen
            assert quote in seen
            assert "Thử đổi vòng lặp" in seen
            assert "chấm điểm chính thức" in seen or "điểm chính thức" in seen
            # Repeated feedback request never recharges Gemini.
            assert student.post(url,data={
                "csrf_token":token,"action":"retry","attempt_id":str(first_id)
            }).status_code==303
            assert len(calls)==1
            # The next attempt remains distinct, old answer/review remains visible.
            revised=student.post(url,data={**body,"answer":"Sau khi sửa, vòng lặp đơn n lần là O(n); có thể chứng minh từ số thao tác.","action":"save"})
            assert revised.status_code==303
            show=student.get(url).get_data(as_text=True)
            assert "Sau khi sửa" in show and "Vòng lặp chạy từ 0" in show
            conn=project.db()
            assert conn.execute("SELECT count(*) FROM chapter_exercise_attempts WHERE user_id=?",
                                (uid,)).fetchone()[0]==2
            # Incorrect citations cannot be displayed as verified feedback.
            project.gemini_generate=lambda p:(json.dumps({
                "explanation":"Tuyệt đối đúng.","citations":[
                    {"source_key":"T1","quote":"Một tài liệu hoàn toàn không tồn tại trong nguồn."}]
            },ensure_ascii=False),None)
            c=student.post(url,data={**body,"answer":"Đây là bài làm cần AI phản hồi có dẫn chứng đáng tin cậy.","action":"evaluate"})
            assert c.status_code==303
            assert "Tuyệt đối đúng." not in student.get(url).get_data(as_text=True)
            assert conn.execute("""
                SELECT feedback_status FROM chapter_exercise_attempts
                WHERE user_id=? ORDER BY id DESC LIMIT 1
            """,(uid,)).fetchone()[0]=="unavailable"
            # Admin can revoke chapter mapping; saved work persists, AI is blocked.
            conn.execute("DELETE FROM shared_document_chapters WHERE document_id=?",(document,))
            conn.commit()
            blocked=student.get(url).get_data(as_text=True)
            assert "Chưa có học liệu chung" in blocked
            assert "Sau khi sửa" in blocked
            # After syllabus replacement, historical answers still persist
            # but must not be evaluated as if they were from the new syllabus.
            conn.execute("UPDATE shared_subjects SET syllabus_text=? WHERE id=?",
                         (syllabus.replace("BT01:", "BT01 mới:"),sid))
            conn.commit()
            assert student.post(url,data={
                "csrf_token":token,"action":"retry","attempt_id":str(first_id)
            }).status_code==409
            assert conn.execute("SELECT count(*) FROM chapter_exercise_attempts WHERE user_id=?",
                                (uid,)).fetchone()[0]==3
            conn.close()
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
            project.gemini_generate=old_gemini
    print("C1 chapter practice PASS: syllabus ownership, CSRF, revisions, verified citations, revocation")


if __name__=="__main__":
    check()
