"""Offline regression for uncluttered Study Plan Web UI and existing task actions."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


def verify():
    conn = project.db()
    now = project.now()
    user = conn.execute(
        "INSERT INTO users(name,email,password_hash,created_at) VALUES(?,?,?,?)",
        ("UI Demo", "planner-ui-ci@example.com",
         project.generate_password_hash("secure-test-password"), now)
    ).lastrowid
    subject = conn.execute(
        "INSERT INTO subjects(user_id,name,code,created_at) VALUES(?,?,?,?)",
        (user, "Điện toán đám mây", "CLOUD-UI", now)
    ).lastrowid
    monday = datetime.now().date() - timedelta(days=datetime.now().weekday())
    first = (monday + timedelta(days=1)).strftime("%Y-%m-%dT19:00")
    second = (monday + timedelta(days=2)).strftime("%Y-%m-%dT20:00")
    task1 = conn.execute(
        """INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,note,done,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (user, subject, "Ôn chương IaaS", first, 45, "Ghi chú cá nhân", 1, now)
    ).lastrowid
    task2 = conn.execute(
        """INSERT INTO study_tasks(user_id,subject_id,title,study_at,duration,note,done,created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (user, subject, "Làm quiz PaaS", second, 45, "", 0, now)
    ).lastrowid
    conn.execute(
        "INSERT INTO reminders(user_id,subject_id,title,due_at,created_at) VALUES(?,?,?,?,?)",
        (user, subject, "Ôn trước ngày thi", second, now)
    )
    conn.commit()
    conn.close()

    client = project.app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"], sess["user_name"] = user, "UI Demo"

    res = client.get("/study-plan")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'id="weekDays"' in html
    assert 'id="plannerViewTabs"' in html
    assert 'id="aiPlannerForm"' in html
    assert 'id="toggleEditPlan"' in html
    assert 'id="addTaskButton"' in html
    assert 'id="taskForm"' in html
    assert 'id="reminderModal"' in html
    assert 'id="scheduleFilterEmpty"' in html
    assert 'id="compactTaskList"' not in html
    assert 'id="compactTaskTitle"' not in html
    assert 'id="task-compact-list"' not in html
    assert 'quote-card compact' not in html
    assert 'class="planner-progress-summary"' not in html  # class contains soft-card too
    assert "planner-progress-summary" in html
    assert "1 / 2 buổi học đã hoàn thành" in html
    assert 'aria-valuenow="50"' in html
    for tid in (task1, task2):
        assert html.count(f'data-task-id="{tid}"') == 1
        assert f"/study-plan/tasks/{tid}/toggle" in html
        assert f"/study-plan/tasks/{tid}/delete" in html
    assert "Ôn chương IaaS" in html
    assert "Ghi chú cá nhân" in html
    assert "Mục tiêu & deadline" in html
    assert "Ôn trước ngày thi" in html
    assert "Gợi ý từ Study Agent" in html
    assert "study_plan_cleanup.css" in html

    # Action semantics must remain functional after template/layout cleanup.
    check = client.post(f"/study-plan/tasks/{task2}/toggle")
    assert check.status_code in (302, 303)
    assert 'aria-valuenow="100"' in client.get("/study-plan").get_data(as_text=True)
    deleted = client.post(f"/study-plan/tasks/{task2}/delete")
    assert deleted.status_code in (302, 303)
    conn = project.db()
    assert conn.execute(
        "SELECT COUNT(*) FROM study_tasks WHERE user_id=?", (user,)
    ).fetchone()[0] == 1
    conn.close()

    # Empty list must retain a usable message driven by JS.
    conn = project.db()
    conn.execute("DELETE FROM study_tasks WHERE user_id=?", (user,))
    conn.commit()
    conn.close()
    empty_html = client.get("/study-plan").get_data(as_text=True)
    assert 'id="scheduleFilterEmpty"' in empty_html
    assert 'id="compactTaskList"' not in empty_html


if __name__ == "__main__":
    old_db, old_upload = project.DB_PATH, project.UPLOAD_DIR
    try:
        with TemporaryDirectory() as folder:
            project.DB_PATH = Path(folder) / "study_plan_test.db"
            project.UPLOAD_DIR = Path(folder) / "uploads"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            verify()
    finally:
        project.DB_PATH, project.UPLOAD_DIR = old_db, old_upload
    print("Study Plan clarity UI tests passed")
