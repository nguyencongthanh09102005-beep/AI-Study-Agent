"""Smoke test that contrast stylesheet is served on every Web surface."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def verify():
    css_path = Path(project.__file__).resolve().parent / "static/css/readability.css"
    css = css_path.read_text(encoding="utf-8")
    assert "body.study-ui" in css
    assert "body.mock-auth-page" in css
    assert ".week-day.active" in css
    assert "#fff" in css  # selected-day label stays white on violet
    assert "quiz-action-card:not(.primary-action)" in css  # primary card stays white

    client = project.app.test_client()
    login = client.get("/login")
    assert login.status_code == 200
    assert "readability.css" in login.get_data(as_text=True)
    user_conn = project.db()
    uid = user_conn.execute(
        "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
        ("UI Tester", "contrast-test@example.local",
         project.generate_password_hash("secure-test-password"), project.now())
    ).lastrowid
    user_conn.commit()
    user_conn.close()
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["user_name"] = "UI Tester"
    for route in ["/dashboard", "/subjects", "/documents", "/quiz", "/study-plan", "/chat"]:
        response = client.get(route)
        assert response.status_code == 200, (route, response.status_code)
        html = response.get_data(as_text=True)
        assert 'css/readability.css' in html, route

    conn = project.db()
    conn.execute("UPDATE users SET role='admin' WHERE id=?", (uid,))
    conn.commit()
    conn.close()
    for route in ["/admin", "/admin/documents"]:
        response = client.get(route)
        assert response.status_code == 200, (route, response.status_code)
        assert 'css/readability.css' in response.get_data(as_text=True), route


if __name__ == "__main__":
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "study_agent_readability.db"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            verify()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Web readability style coverage QA passed")
