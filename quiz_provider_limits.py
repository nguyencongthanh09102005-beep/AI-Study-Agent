"""Explicit signal for Gemini quota/rate limits during durable Quiz preparation.

Unlike an invalid question, HTTP 429 is temporary/provider-side and must not
silently discard the already verified questions or trigger a hot retry loop.
"""


class QuizRateLimitError(RuntimeError):
    """Exhausted Gemini fallbacks due to HTTP 429 during Quiz generation."""

    def __init__(self):
        super().__init__(
            "Dịch vụ AI đang giới hạn yêu cầu (HTTP 429). "
            "Quiz đã chuẩn bị được giữ nguyên; hệ thống sẽ tạm nghỉ "
            "trước khi tiếp tục."
        )


class QuizProviderBusyError(RuntimeError):
    """All available AI models are temporarily busy (HTTP 503) for this step."""

    def __init__(self):
        super().__init__(
            "Dịch vụ AI đang quá tải (HTTP 503). "
            "Câu Quiz đã kiểm chứng được giữ nguyên; hệ thống sẽ thử lại sau."
        )
