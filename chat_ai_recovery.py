"""Retry a citation-checked chat answer once when a real model responds
but fails JSON/provenance validation. Never turn failed citations into claims.
No API calls are made unless the injected generator is called by a real Chat.
"""
import time


RETRY_INSTRUCTIONS = """
LẦN TRẢ LỜI TRƯỚC KHÔNG ĐẠT KIỂM CHỨNG. Hãy tạo lại ĐÚNG một JSON hợp lệ
theo cấu trúc đã yêu cầu, không dùng code fence và không thêm chữ bên ngoài.
Nếu trả lời dựa trên học liệu, citations.quote phải được CHÉP NGUYÊN VĂN
từ một đoạn LIÊN TIẾP dài 20-180 ký tự trong đúng NGUỒN đã cung cấp.
Giữ nguyên dấu tiếng Việt, dấu câu và tên nguồn/source_key; không viết lại
hay diễn đạt lại câu trích dẫn. Chỉ dùng nguồn đang được phép; không lấy
thông tin trong lịch sử chat làm bằng chứng. Nếu tài liệu không hỗ trợ
câu hỏi, hãy tuân thủ quy tắc thiếu nguồn có sẵn, tuyệt đối không bịa.
""".strip()


def generate_verified(prompt, generate, validate, *, label="Chat",
                      max_first_call_seconds=18):
    """Return (validated value, error). Only retry if the model emitted
    an unverified response; no retry on timeouts, empty replies or API errors.
    """
    start = time.monotonic()
    last_error = None
    for attempt in range(2):
        request_prompt = (
            prompt if attempt == 0 else prompt + "\n\n" + RETRY_INSTRUCTIONS
        )
        raw, provider_error = generate(request_prompt)
        if not raw:
            return None, provider_error or last_error or "AI không phản hồi."
        try:
            checked = validate(raw)
        except (ValueError, TypeError) as exc:
            checked = None
            last_error = str(exc)[:200]
        if checked:
            return checked, None
        last_error = last_error or "Không có dẫn chứng được xác minh."
        print(f"{label} source/JSON verification failed (attempt {attempt + 1}): "
              f"{last_error}")
        # A slow first call must not trigger another potentially long call.
        if attempt == 0 and time.monotonic() - start > max_first_call_seconds:
            break
    return None, last_error
