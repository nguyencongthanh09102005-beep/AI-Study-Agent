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

    password = getpass.getpass("Mật khẩu Admin (tối thiểu 10 ký tự): ")
    confirm = getpass.getpass("Nhập lại mật khẩu Admin: ")
    if len(password) < 10 or password != confirm:
        parser.error("Mật khẩu cần tối thiểu 10 ký tự và xác nhận trùng khớp.")

    app.init_db()
    conn = app.db()
    try:
        old = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if old:
            # Only someone with LOCAL database access can invoke this script.
            conn.execute(
                "UPDATE users SET name=?,password_hash=?,role='admin' WHERE id=?",
                (name, app.generate_password_hash(password), old["id"])
            )
            print("Đã cập nhật tài khoản thành Admin:", email)
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
