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


def verify_source_citations(raw, mode, allowed_names, evidence_map):
    """Require verbatim, source-scoped quotes for a sourced free Chat answer.

    This validates existence of a quote in the passages sent to the model,
    NOT whether every explanation is semantically true. Discard any forged
    quote/name rather than showing it as supported.
    """
    if mode == "general":
        return []
    content = str(raw or "").strip()
    if content.startswith("\x60" * 3):
        content = re.sub(r"^\x60{3}(?:json)?\s*", "", content, flags=re.I)
        content = re.sub(r"\s*\x60{3}$", "", content)
    try:
        doc = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise ValueError("Unparseable model evidence") from exc
    candidates = doc.get("citations")
    if not isinstance(candidates, list):
        raise ValueError("Source citations required")
    def norm(value):
        import unicodedata
        return " ".join(unicodedata.normalize("NFC", str(value or "")).split()).casefold()
    verified = []
    for item in candidates[:10]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("source") or "").strip()
        quote = " ".join(str(item.get("quote") or "").split())
        if not (name in allowed_names and 20 <= len(quote) <= 400):
            continue
        if not any(norm(quote) in norm(passage)
                   for passage in evidence_map.get(name, ())):
            continue
        if (name, quote) not in [(v["source"], v["quote"]) for v in verified]:
            verified.append({"source": name, "quote": quote})
    if not verified:
        raise ValueError("No verified quotation from selected course evidence")
    return verified
