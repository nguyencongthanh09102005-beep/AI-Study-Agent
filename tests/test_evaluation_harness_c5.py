"""C5: never imply synthetic results measure genuine Gemini performance."""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evaluation.benchmark_agent_vs_gemini import DEFAULT_CASES, prompts, run_cases


def check():
    cases=json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    assert len(cases)>=4
    calls=[]
    def fake(prompt):
        calls.append(prompt)
        # The returned quote appears literally in this synthetic learning
        # excerpt only for BIG-O-01; invalid quotes are never counted.
        if "Vòng lặp duyệt tuần tự n phần tử" in prompt and "AES" not in prompt:
            body=json.dumps({"explanation":"Vòng lặp n lần có thể là O(n).",
                             "citations":[{
                                "source_key":"T1",
                                "quote":"Vòng lặp duyệt tuần tự n phần tử thực hiện tối đa n lần thao tác với thời gian O(n)."
                             }],
                             "practice":"Phân tích hai vòng lặp."},ensure_ascii=False)
        else:
            body=json.dumps({"explanation":"Không đủ thông tin.",
                             "citations":[{
                                "source_key":"T1",
                                "quote":"Trích dẫn không tồn tại trong dữ liệu nguồn."
                             }]},ensure_ascii=False)
        return body,None
    rows=run_cases(cases,fake)
    assert len(rows)==len(cases)
    assert len(calls)==2*len(cases)
    assert rows[0]["arms"]["agent"]["citation_verified"]
    assert rows[0]["arms"]["direct"]["citation_verified"]
    assert not rows[-1]["arms"]["agent"]["citation_verified"]
    direct,agent,source=prompts(cases[0])
    assert cases[0]["question"] in direct and cases[0]["question"] in agent
    assert cases[0]["source_excerpt"] in direct and cases[0]["source_excerpt"] in agent
    assert cases[0]["weak_topic"] in agent
    assert cases[0]["weak_topic"] not in direct
    assert source["key"]=="T1"
    args=[sys.executable,"evaluation/benchmark_agent_vs_gemini.py",
          "--cases",str(DEFAULT_CASES),"--max-cases","2"]
    env=os.environ.copy()
    # An empty explicit value prevents app.load_dotenv() from restoring a real
    # API key in the child process on developer machines.
    env["GEMINI_API_KEY"]=""
    print("C5: checking offline dry run...",flush=True)
    out=subprocess.run(args,capture_output=True,text=True,check=True,env=env,timeout=30)
    assert "DRY RUN: no API calls" in out.stdout
    assert "no benchmark result invented" in out.stdout
    print("C5: verifying --live refuses missing API key...",flush=True)
    no_key=subprocess.run(args+["--live"],capture_output=True,text=True,env=env,timeout=30)
    assert no_key.returncode!=0
    assert "GEMINI_API_KEY missing" in no_key.stderr or "GEMINI_API_KEY missing" in no_key.stdout
    print("C5 evaluation harness PASS: paired prompts, verified quotes, explicit live opt-in, no invented scores")


if __name__=="__main__":
    check()
