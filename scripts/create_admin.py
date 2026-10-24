"""Create or update an admin account OFFLINE on your own Flask machine.

Run: python scripts/create_admin.py --email admin@example.com --name "Study Admin"
Password is prompted securely; it is never stored in source code or CLI history.
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def main():
    parser = argparse.ArgumentParser(description="Provision a local AI Study Agent admin")
    parser.add_argument("--email", required=True, help="Administrator email")
    parser.add_argument("--name", default="Quản trị viên", help="Displayed administrator name")
    args = parser.parse_args()
    email = args.email.strip().lower()
    name = args.name.strip()
    if not name or "@" not in email or "." not in email.split("@")[-1]:
        parser.error("Vui lòng nhập tên và email hợp lệ.")

    # Refuse to silently promote an existing student account: its password,
    # name and role must not be overwritten while its learning data is linked
    # to the original user ID.
    app.init_db()
    conn = app.db()
    try:
        existing = conn.execute(
            "SELECT role FROM users WHERE email=?", (email,)
        ).fetchone()
    finally:
        conn.close()
    if existing and existing["role"] != "admin":
        parser.error(
            "Email này đã thuộc tài khoản sinh viên. KHÔNG chuyển vai trò "
            "hoặc ghi đè mật khẩu của sinh viên. Hãy dùng email Admin khác. "
            "Nếu đã bị chuyển trước đó, chạy scripts/restore_student.py."
        )

    password = getpass.getpass("Mật khẩu Admin (tối thiểu 10 ký tự): ")
    confirm = getpass.getpass("Nhập lại mật khẩu Admin: ")
    if len(password) < 10 or password != confirm:
        parser.error("Mật khẩu cần tối thiểu 10 ký tự và xác nhận trùng khớp.")

    conn = app.db()
    try:
        old = conn.execute("SELECT id,role FROM users WHERE email=?", (email,)).fetchone()
        if old and old["role"] != "admin":
            # Recheck immediately before UPDATE to avoid accidental privilege
            # promotion if the account changed after the first lookup.
            parser.error("Email đang thuộc sinh viên; không được ghi đè tài khoản.")
        if old:
            conn.execute(
                "UPDATE users SET name=?,password_hash=? WHERE id=? AND role='admin'",
                (name, app.generate_password_hash(password), old["id"])
            )
            print("Đã đổi mật khẩu tài khoản Admin:", email)
        else:
            conn.execute(
                "INSERT INTO users(name,email,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                (name, email, app.generate_password_hash(password), "admin", app.now())
            )
            print("Đã tạo tài khoản Admin:", email)
        conn.commit()
    finally:
        conn.close()
    print("Đăng nhập tại /login và chọn tab Quản trị viên.")


if __name__ == "__main__":
    main()
