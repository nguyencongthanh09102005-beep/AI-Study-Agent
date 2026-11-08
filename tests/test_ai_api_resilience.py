"""Offline AI API resilience regression.

All network calls and credentials are fixtures; no real provider usage.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project


class Reply:
    def __init__(self, status, message="", answer=None, error_status=None):
        self.status_code = status
        self.ok = status == 200
        self.text = message
        self._message = message
        self._answer = answer
        self._error_status = error_status

    def json(self):
        if self.ok:
            return {"candidates": [{"content": {"parts": [{"text": self._answer}]}}]}
        return {"error": {"message": self._message, "status": self._error_status}}


class InvalidJsonReply(Reply):
    def json(self):
        raise ValueError("HTML gateway error")


def check(responses, fallbacks="backup-model", primary_retries="2"):
    calls = []
    iterator = iter(responses)

    def fake_post(url, headers, json, timeout):
        calls.append((url, timeout))
        assert headers["x-goog-api-key"] == "unit-test-key"
        assert 0 < timeout <= 25
        assert json["contents"][0]["parts"][0]["text"] == "test-question"
        return next(iterator)

    settings = {
        "GEMINI_API_KEY": "unit-test-key",
        "GEMINI_MODEL": "primary-model",
        "GEMINI_FALLBACK_MODELS": fallbacks,
        "GEMINI_PRIMARY_RETRIES": primary_retries,
        "GEMINI_REQUEST_TIMEOUT": "25",
        "GEMINI_TOTAL_TIMEOUT": "35",
    }
    with patch.dict(os.environ, settings), \
         patch.object(project.requests, "post", side_effect=fake_post), \
         patch.object(project.time, "sleep") as slept:
        answer, error = project.gemini_generate("test-question")
    return answer, error, [url for url, _ in calls], slept.call_count


def run():
    # 503 high demand: go straight to fallback, without repeat/sleep.
    text, err, calls, sleeps = check([
        Reply(503, "model overloaded"), Reply(200, answer="Answer from backup"),
    ])
    assert text == "Answer from backup" and err is None
    assert len(calls) == 2 and "primary-model" in calls[0]
    assert "backup-model" in calls[1] and sleeps == 0

    # Minute-rate-limited primary: another model may still be available.
    text, err, calls, sleeps = check([
        Reply(429, "Requests per minute exceeded"), Reply(200, answer="Backup"),
    ])
    assert (text, err, len(calls), sleeps) == ("Backup", None, 2, 0)

    # A daily quota is not cured by spending more calls on the same project.
    text, err, calls, sleeps = check([
        Reply(429, "Requests per day exceeded", error_status="quota_exceeded"),
    ])
    assert text is None and "HTTP 429" in err and "hạn mức" in err
    assert len(calls) == 1 and sleeps == 0

    # A deleted/misconfigured primary model can still use a valid fallback.
    text, err, calls, sleeps = check([
        Reply(404, "model_not_found"), Reply(200, answer="Recovered model"),
    ])
    assert text == "Recovered model" and err is None and len(calls) == 2

    text, err, calls, sleeps = check([
        Reply(404, "model_not_found"), Reply(404, "model_not_found"),
    ])
    assert text is None and "Mô hình AI" in err and len(calls) == 2
    assert "primary-model" not in err and "backup-model" not in err

    # Invalid key means no model can work; never leak provider details.
    text, err, calls, sleeps = check([
        Reply(403, "private key or Project X forbidden"),
    ])
    assert text is None and "cấp quyền" in err and len(calls) == 1
    assert "Project X" not in err

    # If all models are down, show a status-specific, provider-neutral notice.
    text, err, calls, sleeps = check([
        Reply(503, "service overloaded"), Reply(503, "service overloaded"),
    ])
    assert text is None and "HTTP 503" in err and len(calls) == 2
    assert "service overloaded" not in err and sleeps == 0

    # Plain-text / HTML error bodies must never produce a 500 while parsing.
    text, err, calls, sleeps = check([
        InvalidJsonReply(429, "<html>429</html>"),
        Reply(200, answer="Recovered after non-JSON error"),
    ])
    assert text == "Recovered after non-JSON error" and len(calls) == 2

    # Without any backup, bounded retry (not an unlimited hot loop).
    text, err, calls, sleeps = check([
        Reply(503, "busy"), Reply(200, answer="Retry succeeded"),
    ], fallbacks="", primary_retries="1")
    assert text == "Retry succeeded" and len(calls) == 2 and sleeps == 1

    print("AI API resilience PASS: 503/429/404 recovery, quota, auth, bounded retry")


if __name__ == "__main__":
    run()
