"""F4: conservative validation of structured Gemini free-chat responses.

Does not prove factual accuracy, but refuses unparsed JSON and forged file
names instead of displaying them as sourced answers.
"""
import json
import re


def parse_free_chat_response(raw, personal_source_names, shared_source_names):
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Empty model response")
    value = raw.strip()
    fence = r"\x60{3}"
    match = re.fullmatch(fence + r"(?:json)?\s*(.*?)\s*" + fence, value,
                         flags=re.IGNORECASE | re.DOTALL)
    if match:
        value = match.group(1)
    try:
        data = json.loads(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid Gemini JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Gemini response must be an object")
    answer, mode, sources = data.get("answer"), data.get("mode"), data.get("sources")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Answer missing or not a string")
    if mode not in ("document", "shared", "general"):
        raise ValueError("Unknown provenance mode")
    if not isinstance(sources, list) or any(not isinstance(x, str) for x in sources):
        raise ValueError("Invalid sources field")
    permitted = (set(personal_source_names) if mode == "document" else
                 set(shared_source_names) if mode == "shared" else set())
    if any(x.strip() not in permitted for x in sources):
        raise ValueError("Source not present in current student's context")
    if mode != "general" and not sources:
        raise ValueError("Source-backed answer requires a real source name")
    if mode == "general" and sources:
        raise ValueError("Unsourced answer cannot cite a document")
    return answer.strip(), list(dict.fromkeys(x.strip() for x in sources)), mode
