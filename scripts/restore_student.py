"""Recover a student account accidentally promoted by the old create_admin.py.

Run locally in the project root, with Flask stopped:
    python scripts/restore_student.py --email student@gmail.com --admin-email student+admin@gmail.com

Retains the student's original user ID and all data; moves Admin to a new
account with a different login email. Passwords are prompted privately.
"""
import argparse
import getpass
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def restore_accounts(student_email, admin_email, student_name, student_password, admin_password):
    """One-time local recovery. Do not touch student-owned rows or user IDs."""
    student_email = str(student_email).strip().lower()
    admin_email = str(admin_email).strip().lower()
    student_name = str(student_name).strip()
    if (
        not student_name or student_email == admin_email
        or not all("@" in value and "." in value.split("@")[-1]
                   for value in (student_email, admin_email))
    ):
        raise ValueError("Cần hai email hợp lệ và KHÁC NHAU, cùng tên hiển thị sinh viên.")
    if (
        len(student_password) < 10 or len(admin_password) < 10
        or secrets.compare_digest(student_password, admin_password)
    ):
        raise ValueError("Hai mật khẩu phải khác nhau, mỗi mật khẩu ít nhất 10 ký tự.")

    app.init_db()
    conn = app.db()
    backup_file = None
    try:
        student = conn.execute(
            "SELECT id,role FROM users WHERE email=?", (student_email,)
        ).fetchone()
        if student is None:
            raise ValueError("Không tìm thấy tài khoản cần khôi phục trong database này.")
        if student["role"] != "admin":
            raise ValueError(
                "Tài khoản này không mang quyền Admin. Có thể đã khôi phục rồi; "
                "không thay đổi dữ liệu."
            )
        existing_admin = conn.execute(
            "SELECT id FROM users WHERE email=?", (admin_email,)
        ).fetchone()
        if existing_admin:
            raise ValueError(
                "Email Admin mới đã được sử dụng. Chọn email khác để tránh ghi đè."
            )

        # An SQLite online backup protects the account and all existing
        # student data before any change. data/*.db is gitignored.
        backup_file = app.DB_PATH.parent / (
            "study_agent_backup_before_account_recovery_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_" + secrets.token_hex(3) + ".db"
        )
        with sqlite3.connect(backup_file) as backup:
            conn.backup(backup)

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE users SET name=?,role='student',password_hash=? WHERE id=?",
            (student_name, app.generate_password_hash(student_password), student["id"])
        )
        conn.execute(
            "INSERT INTO users(name,email,password_hash,role,created_at) "
            "VALUES(?,?,?,?,?)",
            ("Quản trị viên", admin_email,
             app.generate_password_hash(admin_password), "admin", app.now())
        )
        conn.commit()
        return {
            "student_id": student["id"],
            "student_email": student_email,
            "admin_email": admin_email,
            "backup_path": str(backup_file)
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Giữ nguyên dữ liệu sinh viên khi tách tài khoản Admin dùng trùng email."
    )
    parser.add_argument("--email", required=True, help="Email sinh viên gốc")
    parser.add_argument("--admin-email", required=True, help="Email mới, riêng cho Admin")
    args = parser.parse_args()

    print("Hãy tắt Flask trước khi khôi phục để tránh ghi đồng thời.")
    print("Dữ liệu môn học, file cá nhân và tiến độ sẽ được giữ nguyên.")
    name = input("Tên hiển thị sinh viên (vd: Nguyễn Công Thành): ").strip()
    student_pw = getpass.getpass("Mật khẩu MỚI cho sinh viên (>=10 ký tự): ")
    confirm_student = getpass.getpass("Nhập lại mật khẩu sinh viên: ")
    admin_pw = getpass.getpass("Mật khẩu MỚI cho Admin (>=10 ký tự): ")
    confirm_admin = getpass.getpass("Nhập lại mật khẩu Admin: ")
    if not (
        secrets.compare_digest(student_pw, confirm_student)
        and secrets.compare_digest(admin_pw, confirm_admin)
    ):
        parser.error("Các mật khẩu nhập lại không trùng khớp.")
    try:
        result = restore_accounts(
            args.email, args.admin_email, name, student_pw, admin_pw
        )
    except (ValueError, sqlite3.Error, OSError) as exc:
        parser.error(str(exc))

    print("ĐÃ KHÔI PHỤC: Sinh viên", result["student_email"])
    print("ĐÃ TẠO RIÊNG: Admin", result["admin_email"])
    print("ID sinh viên cũ được giữ nguyên:", result["student_id"])
    print("Bản sao database trước khi khôi phục:", result["backup_path"])
    print("Khởi động Flask lại và đăng nhập đúng tab tương ứng.")


if __name__ == "__main__":
    main()
