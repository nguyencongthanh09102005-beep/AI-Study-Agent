"""Regression tests: old student account restored without losing user-owned data."""
import contextlib
import io
import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from scripts.create_admin import main as create_admin_main
from scripts.restore_student import restore_accounts


def verify():
    conn = project.db()
    cur = conn.execute(
        "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
        ("Sinh viên gốc", "student@example.com",
         project.generate_password_hash("old-student-password"), project.now())
    )
    uid = cur.lastrowid
    cur2 = conn.execute(
        """INSERT INTO subjects(user_id,name,code,created_at)
        VALUES(?,?,?,?)""", (uid, "Môn học của tôi", "STUD101", project.now())
    )
    subject_id = cur2.lastrowid
    conn.execute(
        """INSERT INTO documents(
            user_id,subject_id,original_name,stored_name,extracted_text,created_at
        ) VALUES(?,?,?,?,?,?)""",
        (uid, subject_id, "tai-lieu-rieng.txt", "private.txt",
         "Nội dung cá nhân quan trọng", project.now())
    )
    conn.commit()
    # Regression: even when local provisioner is invoked on a student email,
    # it must NEVER prompt for a new password or overwrite student's identity.
    old_hash = conn.execute(
        "SELECT password_hash FROM users WHERE id=?", (uid,)
    ).fetchone()[0]
    conn.close()
    with patch("sys.argv", ["create_admin.py", "--email", "student@example.com"]):
        with patch("getpass.getpass", side_effect=AssertionError(
            "Must not prompt for password when email belongs to student"
        )):
            with contextlib.redirect_stderr(io.StringIO()):
                try:
                    create_admin_main()
                except SystemExit as exc:
                    assert exc.code == 2
                else:
                    raise AssertionError("Admin provisioner incorrectly converted a student")
    conn = project.db()
    assert conn.execute(
        "SELECT role,password_hash FROM users WHERE id=?", (uid,)
    ).fetchone()["password_hash"] == old_hash
    assert conn.execute(
        "SELECT role FROM users WHERE id=?", (uid,)
    ).fetchone()["role"] == "student"

    # Simulate damage done by the previous provisioning script.
    conn.execute(
        "UPDATE users SET name=?,role='admin',password_hash=? WHERE id=?",
        ("Quản trị viên", project.generate_password_hash("lost-student-old-hash"), uid)
    )
    conn.commit()
    conn.close()

    try:
        restore_accounts(
            "student@example.com", "student@example.com",
            "Sinh viên", "student-long-password", "admin-long-password"
        )
        raise AssertionError("Same email must be rejected")
    except ValueError:
        pass

    recovered = restore_accounts(
        "student@example.com", "student+admin@example.com",
        "Tên sinh viên", "brand-new-student-password", "brand-new-admin-password"
    )
    assert recovered["student_id"] == uid
    backup = Path(recovered["backup_path"])
    assert backup.is_file()

    with sqlite3.connect(backup) as previous:
        backup_row = previous.execute(
            "SELECT role FROM users WHERE email='student@example.com'"
        ).fetchone()
        assert backup_row[0] == "admin"

    conn = project.db()
    user = conn.execute(
        "SELECT * FROM users WHERE email=?", ("student@example.com",)
    ).fetchone()
    admin = conn.execute(
        "SELECT * FROM users WHERE email=?", ("student+admin@example.com",)
    ).fetchone()
    assert user["id"] == uid
    assert user["name"] == "Tên sinh viên"
    assert user["role"] == "student"
    assert admin["role"] == "admin"
    assert admin["id"] != uid
    assert project.check_password_hash(user["password_hash"], "brand-new-student-password")
    assert project.check_password_hash(admin["password_hash"], "brand-new-admin-password")
    assert conn.execute(
        "SELECT COUNT(*) FROM subjects WHERE user_id=?", (uid,)
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM documents WHERE user_id=? AND subject_id=?",
        (uid, subject_id)
    ).fetchone()[0] == 1
    conn.close()

    student_client = project.app.test_client()
    login = student_client.post("/login", data={
        "email": "student@example.com", "password": "brand-new-student-password"
    })
    assert login.status_code in (302, 303)
    assert "/dashboard" in login.headers["Location"]
    assert student_client.get("/dashboard").status_code == 200
    assert "tai-lieu-rieng.txt" in student_client.get("/documents").get_data(as_text=True)
    assert student_client.get("/admin").status_code == 403

    admin_client = project.app.test_client()
    login = admin_client.post("/admin/login", data={
        "email": "student+admin@example.com", "password": "brand-new-admin-password"
    })
    assert login.status_code in (302, 303)
    assert "/admin" in login.headers["Location"]
    assert admin_client.get("/admin").status_code == 200

    # Recovery must not run twice and must not overwrite any unrelated user.
    try:
        restore_accounts(
            "student@example.com", "student+admin@example.com",
            "Tên khác", "another-student-password", "another-admin-password"
        )
        raise AssertionError("Second recovery should be rejected")
    except ValueError:
        pass


if __name__ == "__main__":
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "data" / "study_agent.db"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.DB_PATH.parent.mkdir()
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            verify()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Student+Admin restoration QA passed; original student ID/data preserved")
