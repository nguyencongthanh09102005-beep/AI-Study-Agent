"""Regression test for admin-only common course materials, isolated from real data."""
import sys
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def verify_common_library():
    admin = project.app.test_client()
    alice = project.app.test_client()
    bob = project.app.test_client()
    stranger = project.app.test_client()
    anonymous = project.app.test_client()

    conn = project.db()
    conn.execute(
        "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
        ("Admin QA", "admin-ci@study.local",
         project.generate_password_hash("secure-admin-123"), "admin", project.now()),
    )
    conn.commit()
    conn.close()

    assert anonymous.get("/admin").status_code in (302, 303)
    assert anonymous.post("/admin/subjects", data={"name": "Hacked", "code": "ZZ"}).status_code in (302, 303)
    assert anonymous.get("/shared-documents/1/file").status_code in (302, 303)

    admin_login = admin.post("/admin/login", data={
        "email": "admin-ci@study.local", "password": "secure-admin-123",
    })
    assert admin_login.status_code in (302, 303)
    assert "/admin" in admin_login.headers["Location"]
    admin_page = admin.get("/admin")
    assert admin_page.status_code == 200
    assert "Quản lý môn học chung" in admin_page.get_data(as_text=True)
    with admin.session_transaction() as sess:
        token = sess["admin_csrf_token"]

    no_csrf = admin.post("/admin/subjects", data={"code": "CLOUD101", "name": "Đám mây"})
    assert no_csrf.status_code == 400
    created = admin.post("/admin/subjects", data={
        "csrf_token": token, "code": "CLOUD101",
        "name": "Điện toán đám mây", "description": "Bài học chung",
    })
    assert created.status_code in (302, 303)
    conn = project.db()
    shared_id = conn.execute(
        "SELECT id FROM shared_subjects WHERE subject_key='code:cloud101'"
    ).fetchone()["id"]
    conn.close()

    uploaded = admin.post("/admin/documents", data={
        "csrf_token": token, "shared_subject_id": str(shared_id),
        "is_syllabus": "1",
        "file": (BytesIO(
            "Đề cương Điện toán đám mây: IaaS, PaaS, SaaS và quản lý tài nguyên."
            .encode("utf-8")
        ), "de_cuong_cloud.txt"),
    }, content_type="multipart/form-data")
    assert uploaded.status_code in (302, 303), uploaded.get_data(as_text=True)
    conn = project.db()
    row = conn.execute(
        "SELECT * FROM shared_documents WHERE shared_subject_id=?", (shared_id,)
    ).fetchone()
    assert row and row["is_syllabus"] == 1
    assert "IaaS" in row["extracted_text"]
    doc_id = row["id"]
    assert conn.execute(
        "SELECT syllabus_text FROM shared_subjects WHERE id=?", (shared_id,)
    ).fetchone()["syllabus_text"].startswith("Đề cương")
    assert conn.execute(
        "SELECT content FROM shared_knowledge WHERE id=?", (row["knowledge_id"],)
    ).fetchone()["content"] == row["extracted_text"]
    conn.close()

    def register(client, email, code):
        response = client.post("/register", data={
            "name": "Sinh viên QA", "email": email, "password": "123456789",
            "confirm_password": "123456789", "role": "admin",
        })
        assert response.status_code in (302, 303)
        assert client.get("/admin").status_code == 403
        subject = client.post("/api/mobile/subjects", json={
            "name": "Điện toán đám mây" if code == "CLOUD101" else "Môn khác",
            "code": code, "credits": 3, "target_score": 8.0,
        })
        assert subject.status_code == 201, subject.get_data(as_text=True)
        return subject.get_json()["subject"]["id"]

    alice_sub = register(alice, "alice-ci@study.local", "CLOUD101")
    bob_sub = register(bob, "bob-ci@study.local", "CLOUD101")
    outsider_sub = register(stranger, "outsider-ci@study.local", "UNRELATED222")

    for client, subject_id in ((alice, alice_sub), (bob, bob_sub)):
        response = client.get("/documents")
        assert response.status_code == 200
        assert "de_cuong_cloud.txt" in response.get_data(as_text=True)
        assert client.get(f"/shared-documents/{doc_id}/file").status_code == 200
        mobile = client.get(f"/api/mobile/subjects/{subject_id}")
        assert mobile.status_code == 200
        assert any(d["id"] == doc_id for d in mobile.get_json()["shared_documents"])
        mobile_doc = client.get(f"/api/mobile/shared-documents/{doc_id}")
        assert mobile_doc.status_code == 200
        assert "IaaS" in mobile_doc.get_json()["document"]["extracted_text"]
        detail = client.get(f"/subjects/{subject_id}")
        assert detail.status_code == 200
        assert "de_cuong_cloud.txt" in detail.get_data(as_text=True)
        conn = project.db()
        user_id = conn.execute(
            "SELECT user_id FROM subjects WHERE id=?", (subject_id,)
        ).fetchone()["user_id"]
        backbone = project.get_course_learning_backbone(conn, user_id, subject_id)
        assert "IaaS" in backbone["shared_context"]
        assert backbone["syllabus_source"] == "shared"
        conn.close()

    assert "de_cuong_cloud.txt" not in stranger.get("/documents").get_data(as_text=True)
    assert stranger.get(f"/shared-documents/{doc_id}/file").status_code == 403
    assert stranger.get(f"/api/mobile/shared-documents/{doc_id}").status_code == 403
    assert stranger.get(f"/api/mobile/subjects/{outsider_sub}").get_json()["shared_documents"] == []
    assert stranger.post("/admin/documents", data={
        "csrf_token": token, "shared_subject_id": str(shared_id),
        "file": (BytesIO(b"attack"), "attack.txt"),
    }).status_code == 403
    assert admin.get(f"/shared-documents/{doc_id}/file").status_code == 200

    deleted = admin.post(f"/admin/documents/{doc_id}/delete", data={"csrf_token": token})
    assert deleted.status_code in (302, 303)
    assert alice.get(f"/shared-documents/{doc_id}/file").status_code == 404
    assert "de_cuong_cloud.txt" not in alice.get("/documents").get_data(as_text=True)
    conn = project.db()
    assert conn.execute(
        "SELECT syllabus_text FROM shared_subjects WHERE id=?", (shared_id,)
    ).fetchone()["syllabus_text"] == ""
    assert conn.execute("SELECT COUNT(*) FROM shared_knowledge WHERE shared_subject_id=?", (shared_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT role FROM users WHERE email='alice-ci@study.local'").fetchone()[0] == "student"
    conn.close()

    # Edit permissions and duplicate course-key safety.
    assert admin.get("/admin").status_code == 200
    html = admin.get("/admin").get_data(as_text=True)
    assert f"/admin/subjects/{shared_id}/edit" in html
    assert f"/admin/subjects/{shared_id}/delete" in html
    assert "data-edit-subject" in html
    assert alice.post(f"/admin/subjects/{shared_id}/edit", data={
        "csrf_token": token, "code": "HACKED", "name": "No",
    }).status_code == 403
    assert alice.post(f"/admin/subjects/{shared_id}/delete", data={
        "csrf_token": token, "confirm_code": "CLOUD101",
    }).status_code == 403
    assert anonymous.post(f"/admin/subjects/{shared_id}/delete", data={
        "csrf_token": token, "confirm_code": "CLOUD101",
    }).status_code in (302, 303)
    assert admin.post(f"/admin/subjects/{shared_id}/edit", data={
        "code": "CLOUD202", "name": "Đám mây 2",
    }).status_code == 400
    assert admin.post(f"/admin/subjects/{shared_id}/delete", data={
        "confirm_code": "CLOUD101",
    }).status_code == 400
    # The unrelated student course has already created a distinct shared stub.
    collision = admin.post(f"/admin/subjects/{shared_id}/edit", data={
        "csrf_token": token, "code": "UNRELATED222", "name": "Tên trùng",
    }, follow_redirects=True)
    assert "Mã môn này đã được dùng" in collision.get_data(as_text=True)
    conn = project.db()
    assert conn.execute(
        "SELECT code FROM shared_subjects WHERE id=?", (shared_id,)
    ).fetchone()["code"] == "CLOUD101"
    # Insert a private student document and Quiz to prove they survive deleting
    # a shared subject, even when that shared catalog is linked to the course.
    alice_id = conn.execute(
        "SELECT user_id FROM subjects WHERE id=?", (alice_sub,)
    ).fetchone()["user_id"]
    personal_file = project.UPLOAD_DIR / "alice_personal.txt"
    personal_file.write_text("Tài liệu cá nhân của Alice", encoding="utf-8")
    conn.execute(
        """INSERT INTO documents (
          user_id,subject_id,original_name,stored_name,extracted_text,created_at
        ) VALUES(?,?,?,?,?,?)""",
        (alice_id, alice_sub, "alice_personal.txt", "alice_personal.txt",
         "Tài liệu cá nhân của Alice", project.now())
    )
    conn.commit()
    conn.close()

    renamed = admin.post(f"/admin/subjects/{shared_id}/edit", data={
        "csrf_token": token, "code": "CLOUD202", "name": "Điện toán đám mây nâng cao",
        "description": "Môn nâng cao sau khi sửa mã",
    })
    assert renamed.status_code in (302, 303)
    conn = project.db()
    row = conn.execute(
        "SELECT code,name,subject_key FROM shared_subjects WHERE id=?", (shared_id,)
    ).fetchone()
    assert row["code"] == "CLOUD202"
    assert row["name"] == "Điện toán đám mây nâng cao"
    assert row["subject_key"] == "code:cloud202"
    assert conn.execute(
        "SELECT shared_subject_id FROM subjects WHERE id=?", (alice_sub,)
    ).fetchone()["shared_subject_id"] is None
    assert conn.execute(
        "SELECT COUNT(*) FROM documents WHERE user_id=? AND subject_id=?",
        (alice_id, alice_sub)
    ).fetchone()[0] == 1
    conn.close()

    # Upload into the renamed catalog. Old-code courses no longer see it.
    upload2 = admin.post("/admin/documents", data={
        "csrf_token": token, "shared_subject_id": str(shared_id),
        "file": (BytesIO("Bài giảng chung mã mới CLOUD202".encode("utf-8")),
                 "bai_giang_moi.txt"),
    }, content_type="multipart/form-data")
    assert upload2.status_code in (302, 303)
    conn = project.db()
    file2 = conn.execute(
        "SELECT id,stored_name FROM shared_documents WHERE shared_subject_id=?",
        (shared_id,)
    ).fetchone()
    assert file2
    doc2_id, doc2_stored = file2["id"], file2["stored_name"]
    conn.close()
    assert "bai_giang_moi.txt" not in alice.get("/documents").get_data(as_text=True)
    assert "bai_giang_moi.txt" not in bob.get("/documents").get_data(as_text=True)
    # Old-code stub created on demand must NOT reappear as an Admin course.
    old_catalog = admin.get("/admin").get_data(as_text=True)
    assert 'data-code="CLOUD101"' not in old_catalog
    assert 'data-code="UNRELATED222"' not in old_catalog
    assert alice.get(f"/shared-documents/{doc2_id}/file").status_code == 403
    new_subject = register(project.app.test_client(), "unused-ci@study.local", "CLOUD202")
    # The student with new code receives new materials automatically.
    new_client = project.app.test_client()
    login = new_client.post("/login", data={
        "email": "unused-ci@study.local", "password": "123456789",
    })
    assert login.status_code in (302, 303)
    assert "bai_giang_moi.txt" in new_client.get("/documents").get_data(as_text=True)
    assert new_client.get(f"/shared-documents/{doc2_id}/file").status_code == 200

    # Deleting shared catalog invalidates shared file access, not personal files.
    bad_confirm = admin.post(f"/admin/subjects/{shared_id}/delete", data={
        "csrf_token": token, "confirm_code": "WRONG",
    })
    assert bad_confirm.status_code == 400
    deleted_course = admin.post(f"/admin/subjects/{shared_id}/delete", data={
        "csrf_token": token, "confirm_code": "CLOUD202",
    })
    assert deleted_course.status_code in (302, 303)
    conn = project.db()
    assert conn.execute(
        "SELECT COUNT(*) FROM shared_subjects WHERE id=?", (shared_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM shared_documents WHERE shared_subject_id=?", (shared_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM shared_knowledge WHERE shared_subject_id=?", (shared_id,)
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM subjects WHERE id IN (?,?,?)",
        (alice_sub, bob_sub, new_subject)
    ).fetchone()[0] == 3
    assert conn.execute(
        "SELECT COUNT(*) FROM documents WHERE user_id=? AND subject_id=?",
        (alice_id, alice_sub)
    ).fetchone()[0] == 1
    conn.close()
    assert personal_file.exists()
    assert not (project.UPLOAD_DIR / doc2_stored).exists()
    assert new_client.get(f"/shared-documents/{doc2_id}/file").status_code == 404
    assert "bai_giang_moi.txt" not in new_client.get("/documents").get_data(as_text=True)
    conn = project.db()
    placeholder = conn.execute(
        "SELECT admin_managed FROM shared_subjects WHERE subject_key='code:cloud202'"
    ).fetchone()
    assert placeholder and placeholder["admin_managed"] == 0
    conn.close()
    # Even after student revisits a deleted code, Admin catalog stays empty.
    assert 'data-code="CLOUD202"' not in admin.get("/admin").get_data(as_text=True)


if __name__ == "__main__":
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as directory:
            project.DB_PATH = Path(directory) / "shared_qa.db"
            project.UPLOAD_DIR = Path(directory) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            verify_common_library()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Admin + Shared Knowledge cross-account QA passed")
