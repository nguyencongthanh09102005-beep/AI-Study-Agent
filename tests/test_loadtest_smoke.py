"""Offline regression checks for scripts/loadtest.py (no Flask or AI API calls)."""
import importlib.util
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("study_agent_loadtest", ROOT / "scripts" / "loadtest.py")
loadtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loadtest)


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload
        self.text = str(payload)

    def json(self):
        return self.payload


class FakeUser:
    def __init__(self, index):
        self.index = index
        self.email = f"test_{index}@example.local"
        self.calls = []

    def hit(self, method, path, body=None, timeout=30):
        self.calls.append((method, path, body))
        return 0.025, True, ""


class LoadtestTests(unittest.TestCase):
    def test_subject_list_contract_and_verified_chat_lookup(self):
        user = loadtest.VirtualUser("http://127.0.0.1:5000", 0, True)
        calls = []

        def stub(method, path, *, json_body=None, timeout=30):
            calls.append((method, path))
            if path == "/api/mobile/login":
                return FakeResponse(401, {})
            if path == "/api/mobile/register":
                return FakeResponse(201, {"user": {"id": 1}})
            if path == "/api/mobile/subjects" and method == "GET":
                return FakeResponse(200, [])
            if path == "/api/mobile/subjects" and method == "POST":
                return FakeResponse(201, {"subject": {"id": 42}})
            if path == "/api/mobile/chat/42":
                return FakeResponse(200, {"conversation_id": 77})
            raise AssertionError((method, path))

        try:
            user._call = stub
            user.setup(need_chat=True)
            self.assertEqual(user.subject_id, 42)
            self.assertEqual(user.conversation_id, 77)
            self.assertIn(("GET", "/api/mobile/subjects"), calls)
        finally:
            user.http.close()

    def test_parallel_sample_count_and_no_chat_warmup(self):
        users = [FakeUser(0), FakeUser(1)]
        scenario = ("Chat", "POST", "/api/chat",
                    lambda user, index: {"conversation_id": user.index + 10,
                                         "question": str(index)}, 2)
        rows, elapsed = loadtest.run_level(users, scenario, 3, 1, warmup=False)
        self.assertEqual(len(rows), 6)
        self.assertGreaterEqual(elapsed, 0)
        self.assertEqual([len(user.calls) for user in users], [3, 3])
        self.assertEqual({row[4] for row in rows}, {True})

    def test_failed_requests_do_not_fake_p95(self):
        rows = [(1, "Broken", 2, 0.5, False, "HTTP 500"),
                (1, "Broken", 2, 0.8, False, "timeout")]
        result = loadtest.summarize(rows, [2.0])
        self.assertEqual(result["loi_pct"], 100)
        self.assertEqual(result["thong_luong"], 0.0)
        self.assertTrue(math.isnan(result["p50_ms"]))
        self.assertEqual(loadtest.number(result["p95_ms"]), "N/A")

    def test_csv_export_is_reproducible(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            rows = [(1, "Dashboard", 1, 0.02, True, "")]
            summary = [dict(loadtest.summarize(rows, [0.05]),
                            kich_ban="Dashboard", nguoi_dung=1)]
            meta = {
                "thoi_diem_bat_dau": "2026-11-04T12:00:00",
                "base_url": "http://127.0.0.1:5000",
                "ghi_chu": "mock; no real performance metrics",
                "tham_so": {"chat": False},
            }
            loadtest.save_results(output, rows, summary, meta)
            for name in ("tonghop.md", "tonghop.csv", "chitiet.csv", "thongtin.json"):
                self.assertTrue((output / name).exists())


if __name__ == "__main__":
    unittest.main()
