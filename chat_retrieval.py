"""Relevant passages from the *entire stored text*, shared across all free Chat UIs.

Query-time, deterministic keyword retrieval: no additional AI calls, no vector
index or silent first-N-character truncation. Selection is not proof of truth:
returned excerpts must be corroborated by verbatim model citations.
"""
import re
import unicodedata

STOP = {
    "của", "những", "các", "trong", "được", "theo", "cho", "với",
    "mình", "tui", "bạn", "hãy", "giúp", "giải", "thích", "chương",
    "môn", "học", "bài", "này", "kia", "gì", "như", "nào", "đâu",
    "tài", "liệu", "trang", "khái", "niệm", "là", "và", "một",
}
WINDOW = 2300
OVERLAP = 260


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", str(text or "")).split())


def tokens(text):
    return {t for t in re.findall(r"[^\W_]+", normalize(text).casefold(), re.U)
            if len(t) > 1 and t not in STOP}


def passages(text, size=WINDOW, overlap=OVERLAP):
    """Cover every stored character with overlapping windows, no tail loss."""
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    result = []
    step = size - overlap
    for start in range(0, len(text), step):
        part = text[start:start+size]
        if part.strip():
            result.append(part)
        if start + size >= len(text):
            break
    return result


def retrieve(rows, question, max_chars=9000, max_passages=5):
    """Rows: {name,text}; return selected (name, verbatim_excerpt) tuples.

    Rank *all* chunks in all records, not just the first pages or latest files.
    For overview questions, sample beginning/middle/end before other matches.
    """
    query = tokens(question)
    overview = any(word in normalize(question).casefold() for word in (
        "tóm tắt", "tổng quan", "toàn bộ", "bao quát", "nội dung chính",
        "các chương", "môn này học gì",
    ))
    candidates = []
    for doc_index, row in enumerate(rows):
        name = str(row["name"] or "").strip()[:180]
        body = str(row["text"] or "")
        for part_index, part in enumerate(passages(body)):
            found = tokens(part) & query
            score = len(found) * 10 + sum(
                1 for term in found if normalize(question).casefold().count(term) > 1
            )
            candidates.append((score, doc_index, part_index, name, part))
    if not candidates:
        return []
    selected = []
    if overview:
        # A summary must not be based exclusively on opening paragraphs.
        by_doc = {}
        for entry in candidates:
            by_doc.setdefault(entry[1], []).append(entry)
        for doc_rows in by_doc.values():
            for pos in (0, len(doc_rows)//2, len(doc_rows)-1):
                item = doc_rows[pos]
                if item not in selected:
                    selected.append(item)
    ranked = sorted(candidates, key=lambda v: (-v[0], v[1], v[2]))
    selected.extend(x for x in ranked if x not in selected)
    result, used, length = [], set(), 0
    for _, _, _, name, part in selected:
        key = (name, part)
        if key in used:
            continue
        room = max_chars-length
        if room < 180:
            break
        snippet = part[:min(WINDOW, room)]
        if not snippet.strip():
            continue
        result.append((name, snippet))
        length += len(snippet)
        used.add(key)
        if len(result) >= max_passages:
            break
    return result


def evidence_from_context(context, names, kind):
    """Reconstruct the exact snippets supplied to Gemini, never whole files."""
    mapping = {}
    context = str(context or "")
    names = list(dict.fromkeys(str(x) for x in (names or [])))
    if kind == "document":
        marker = re.compile(r"(?:^|\n\n)FILE: ([^\n]+)\n", re.U)
        matches = list(marker.finditer(context))
        for index, match in enumerate(matches):
            name = match.group(1)
            if name in names:
                end = matches[index+1].start() if index+1 < len(matches) else len(context)
                mapping.setdefault(name, []).append(context[match.end():end].strip())
    elif kind == "shared":
        marker = re.compile(
            r"(?:^|\n\n)(?:ĐỀ CƯƠNG CHUẨN CỦA MÔN:|"
            r"ĐỀ CƯƠNG CÁ NHÂN FALLBACK \(([^\n]+)\):|"
            r"KIẾN THỨC CHUNG - ([^\n]+?) \([^\n]*\):)\n", re.U,
        )
        matches = list(marker.finditer(context))
        for index, match in enumerate(matches):
            name = ("Đề cương chuẩn của môn" if not match.group(1) and
                    not match.group(2) else (match.group(1) or match.group(2)))
            if name in names:
                end = matches[index+1].start() if index+1 < len(matches) else len(context)
                mapping.setdefault(name, []).append(context[match.end():end].strip())
    return mapping
