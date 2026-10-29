"""Regression coverage for compact personal/shared document folders.

Data lives only in a disposable SQLite DB; no real student documents touched.
"""
import io
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def run():
    old_db,old_dir=project.DB_PATH,project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as tmp:
            project.DB_PATH=Path(tmp)/"docs.sqlite"
            project.UPLOAD_DIR=Path(tmp)/"uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            stamp=project.now()
            users={}
            for name,role in (("alice","student"),("bob","student"),("admin","admin")):
                users[name]=conn.execute("""
                    INSERT INTO users(name,email,password_hash,role,created_at)
                    VALUES(?,?,?,?,?)
                """,(name,name+"@local.test","hash",role,stamp)).lastrowid
            history=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử Đảng','HIS102',3,?)
            """,(users["alice"],stamp)).lastrowid
            ai=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Trí tuệ nhân tạo','AI101',3,?)
            """,(users["alice"],stamp)).lastrowid
            bobs=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Tài liệu Bob','BOB101',3,?)
            """,(users["bob"],stamp)).lastrowid
            conn.commit()
            common=project.ensure_shared_subject_for_user_subject(conn,users["alice"],history)
            shared_id=common["id"]
            conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,stored_name,
                  extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,'de_cuong_lsd.pdf','de-cuong-test.pdf','Chương 1',1,?,?)
            """,(shared_id,users["admin"],stamp))
            conn.execute("""
                INSERT INTO shared_documents(shared_subject_id,original_name,stored_name,
                  extracted_text,is_syllabus,created_by_user_id,created_at)
                VALUES(?,'bai_giang_chuong1.pdf','chapter-test.pdf','Kiến thức 1',0,?,?)
            """,(shared_id,users["admin"],stamp))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                  extracted_text,created_at)
                VALUES(?,?,'ghi_chu_lich_su.txt','alice-note.txt','Thực tế',?)
            """,(users["alice"],history,stamp))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                  extracted_text,created_at)
                VALUES(?,NULL,'chua_phan_loai.txt','alice-unassigned.txt','',?)
            """,(users["alice"],stamp))
            conn.execute("""
                INSERT INTO documents(user_id,subject_id,original_name,stored_name,
                  extracted_text,created_at)
                VALUES(?,?,'PRIVATE_BOB_SECRET.txt','bob-private.txt','Only Bob',?)
            """,(users["bob"],bobs,stamp))
            conn.commit()
            conn.close()

            alice=project.app.test_client()
            bob=project.app.test_client()
            guest=project.app.test_client()
            for client,uid in ((alice,users["alice"]),(bob,users["bob"])):
                with client.session_transaction() as sess:
                    sess["user_id"]=uid
                    sess["user_name"]="Tester"
            assert guest.get("/documents").status_code in (302,303)
            page=alice.get("/documents")
            assert page.status_code==200
            html=page.get_data(as_text=True)
            assert 'id="tabPersonalLibrary"' in html
            assert 'id="tabSharedLibrary"' in html
            assert 'id="personalLibraryPanel"' in html
            assert 'id="sharedLibraryPanel"' in html
            assert 'data-library-folder' in html
            assert "document_library.css" in html and "document_library.js" in html
            assert "Lịch sử Đảng" in html and "Trí tuệ nhân tạo" in html
            assert "Chưa phân loại" in html
            assert "ghi_chu_lich_su.txt" in html
            assert "de_cuong_lsd.pdf" in html and "bai_giang_chuong1.pdf" in html
            assert html.index("de_cuong_lsd.pdf") < html.index("bai_giang_chuong1.pdf")
            assert "Đề cương chuẩn" in html
            assert "0 tài liệu cá nhân" in html  # Empty AI course remains visible
            assert "PRIVATE_BOB_SECRET" not in html
            assert "Một tài liệu tốt hôm nay" not in html
            assert "nền tảng cho thành công ngày mai" not in html
            assert 'class="quote-card' not in html
            assert 'id="documentFileInput"' in html
            assert "Tóm tắt AI" in html and "Tạo Quiz" in html
            assert "Xóa tài liệu" in html and "Chuyển sang môn" in html
            assert "personal_document_file" not in html  # real URLs, not raw endpoint names
            assert "/documents/1/file?preview=1" in html
            assert "/shared-documents/1/file?preview=1" in html
            assert "ghi_chu_lich_su.txt" not in bob.get("/documents").get_data(as_text=True)
            assert "de_cuong_lsd.pdf" not in bob.get("/documents").get_data(as_text=True)
            assert bob.get("/shared-documents/1/file").status_code==403
            assert bob.get("/documents/1/file").status_code==404

            # Upload still works and newly owned file appears in its right course.
            result=alice.post("/documents",data={
                "subject_id":str(ai),
                "file":(io.BytesIO(b"AI102 embeddings practice"),"ai_practice.txt")
            },content_type="multipart/form-data")
            assert result.status_code in (302,303)
            doc_after=alice.get("/documents").get_data(as_text=True)
            assert "ai_practice.txt" in doc_after
            folders=doc_after.split('<details class="library-folder" ')[1:]
            ai_folder=[x for x in folders if
                       x.startswith('data-library-folder data-folder-name="Trí tuệ nhân tạo')]
            assert len(ai_folder)==2, len(ai_folder)  # private and shared course views
            assert 'data-library-file' in ai_folder[0]
            assert "ai_practice.txt" in ai_folder[0]
            assert "ai_practice.txt" not in ai_folder[1]
            conn=project.db()
            assert conn.execute("SELECT count(*) FROM documents WHERE user_id=?",
                                (users["alice"],)).fetchone()[0]==3
            conn.close()
    finally:
        project.DB_PATH,project.UPLOAD_DIR=old_db,old_dir
    print("Document folders PASS: grouped by course, privacy, quote removed, upload/actions kept")


if __name__=="__main__":
    run()
