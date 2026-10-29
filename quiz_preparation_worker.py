"""Run a dedicated persistent Quiz preparation worker (non-serverless hosts).

Usage: python quiz_preparation_worker.py

Do not run this alongside the built-in local python app.py worker against
the same SQLite database. For an always-on production host use ONE worker
process and an ordinary WSGI web service; serverless platforms cannot
promise this process will remain alive after a request.
"""
import app as project
from quiz_preparation_jobs import run_forever

if __name__ == "__main__":
    project.init_db()
    print("AI Study Agent Quiz worker: resume queued jobs; Ctrl+C to stop.")
    run_forever(project)
