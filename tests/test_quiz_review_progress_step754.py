"""7.5.4: compare actual, owner-scoped pre/post Quiz results without Gemini."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project
from quiz_review_progress import save_review_baseline, compare_review_attempt


def question(title, topic, answer=0):
    return {"question":title,"topic":topic,"chapter":"Chương 1",
            "options":["A","B","C","D"],"answer":answer}


def run():
    with TemporaryDirectory() as folder:
        old_db,old_upload=project.DB_PATH,project.UPLOAD_DIR
        try:
            project.DB_PATH=Path(folder)/"review754.sqlite"
            project.UPLOAD_DIR=Path(folder)/"files"
            project.UPLOAD_DIR.mkdir()
            project.init_db()
            conn=project.db()
            uid=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Người học','review754@test.local','hash','student',?)
            """,(project.now(),)).lastrowid
            other=conn.execute("""
                INSERT INTO users(name,email,password_hash,role,created_at)
                VALUES('Người khác','review754-other@test.local','hash','student',?)
            """,(project.now(),)).lastrowid
            sid=conn.execute("""
                INSERT INTO subjects(user_id,name,code,credits,created_at)
                VALUES(?,'Lịch sử','HIST754',3,?)
            """,(uid,project.now())).lastrowid
            source=[question("Lịch sử A","Cương lĩnh"),question("Lịch sử B","Phong trào")]
            source[0]["chapter"]="CHƯƠNG 01: TỔNG QUAN LỊCH SỬ ĐẢNG"
            prior=conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Quiz buổi 1',?,?)
            """,(uid,sid,json.dumps(source,ensure_ascii=False),project.now())).lastrowid
            conn.commit();conn.close()
            client=project.app.test_client()
            with client.session_transaction() as sess:
                sess["user_id"]=uid
            attempted=client.post("/api/quiz/submit",json={
                "quiz_id":prior,"answers":[1,2],"request_id":"review754before"})
            assert attempted.status_code==200,attempted.get_data(as_text=True)
            assert attempted.get_json()["score"]==0
            conn=project.db()
            review_q=[question("Cương lĩnh mới","Cương lĩnh"),
                      question("Phong trào mới","Phong trào"),
                      question("Bài khác","Kiến thức chưa học")]
            review=conn.execute("""
                INSERT INTO quizzes(user_id,subject_id,document_id,title,payload,created_at)
                VALUES(?,?,NULL,'Ôn điểm yếu · Lịch sử',?,?)
            """,(uid,sid,json.dumps(review_q,ensure_ascii=False),
                 project.now())).lastrowid
            save_review_baseline(conn,uid,sid,review,project.now())
            again=save_review_baseline(conn,uid,sid,review,project.now())
            assert again is None
            # Future attempts cannot alter the preserved snapshot.
            snapshot_before=conn.execute("SELECT snapshot_json FROM quiz_review_baselines WHERE quiz_id=?",
                                         (review,)).fetchone()[0]
            conn.commit();conn.close()
            result=client.post("/api/quiz/submit",json={
                "quiz_id":review,"answers":[0,0,0],"request_id":"review754after"})
            assert result.status_code==200,result.get_data(as_text=True)[:1500]
            comparison=result.get_json()["review_comparison"]
            assert comparison["comparable_topics"]==2,comparison
            assert {v["topic"] for v in comparison["topics"]}=={"Cương lĩnh","Phong trào"}
            assert all(v["before_percent"]==0 for v in comparison["topics"])
            assert all(v["after_percent"]==100 for v in comparison["topics"])
            assert all(v["delta_percent"]==100 for v in comparison["topics"])
            saved=client.get(f"/api/quiz/{review}/analysis")
            assert saved.status_code==200
            assert saved.get_json()["review_comparison"]==comparison
            conn=project.db()
            assert conn.execute("SELECT snapshot_json FROM quiz_review_baselines WHERE quiz_id=?",
                                (review,)).fetchone()[0]==snapshot_before
            # No false claim of improvement when the Gemini questions do not
            # match targeted weak topics.
            no_match=compare_review_attempt(
                conn,uid,review,[question("Không liên quan","Khác")],[0])
            assert no_match["comparable_topics"]==0
            assert compare_review_attempt(conn,other,review,review_q,[0]*3) is None
            conn.close()
            with client.session_transaction() as sess:
                sess["user_id"]=other
            assert client.get(f"/api/quiz/{review}/analysis").status_code==404
        finally:
            project.DB_PATH,project.UPLOAD_DIR=old_db,old_upload
    print("7.5.4 before/after snapshot, related topics, history and access PASS")


if __name__=="__main__":
    run()
