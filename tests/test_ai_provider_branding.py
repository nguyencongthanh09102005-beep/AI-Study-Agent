"""Product branding regression: keep AI provider identity backstage.

No remote AI calls or real credentials are used. User-facing templates, browser
scripts, Mobile UI and backend errors must describe the service as AI.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as project

ROOT=Path(__file__).resolve().parents[1]

# Text displayed to students/admins is not a developer configuration guide.
for group in ("templates/*.html", "static/js/*.js", "mobile/App.js"):
    for path in ROOT.glob(group):
        source=path.read_text(encoding="utf-8")
        assert "gemini" not in source.casefold(), (
            "External model/provider branding leaked to client:", path
        )

quiz=(ROOT/"study_session_quiz_runtime.py").read_text(encoding="utf-8")
manual=(ROOT/"manual_lesson_routes.py").read_text(encoding="utf-8")
assert "Gemini chưa tạo đủ" not in quiz
assert "Gemini đang chuẩn bị" not in quiz
assert "Gemini chưa tạo đủ" not in manual
assert "Gemini tạm thời không phản hồi" not in manual

# No credentials: display a clean user message, not a configuration key name.
with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
    content,error=project.gemini_generate("offline test")
    assert content is None and error
    assert "Gemini" not in error and "GEMINI_API_KEY" not in error
    assert "AI" in error

# A provider's HTTP error may contain model IDs, API key hints and vendor names;
# all of them must stay in server logs, never be exposed via the Chat/Quiz UI.
class FakeHTTPError:
    ok=False
    status_code=403
    def json(self):
        return {"error":{"message":"Google Gemini model=gemini-private-123: KEY_ERROR"}}

with patch.dict(os.environ, {
    "GEMINI_API_KEY":"dummy-fake-test-token",
    "GEMINI_MODEL":"gemini-private-123",
    "GEMINI_FALLBACK_MODELS":"",
}), patch.object(project.requests,"post",return_value=FakeHTTPError()):
    content,error=project.gemini_generate("offline test")
    assert content is None and error
    for secret in ("Gemini","Google","KEY_ERROR","gemini-private-123",
                   "GEMINI_API_KEY"):
        assert secret.casefold() not in error.casefold(), (secret,error)
    assert "AI" in error

# Missing provider and network fallback also stay vendor-neutral.
answer=project.local_ai_answer("Một câu hỏi", "", [])
assert "gemini" not in answer.casefold()
assert "AI" in answer

print("AI Study Agent branding PASS: UI and failure messages provider-neutral")
