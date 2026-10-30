"""Select chapter-relevant verbatim text from the WHOLE extracted file.

One upload may be a long textbook. Avoid sending the first N characters only:
scan all overlapping passages locally and pick distinct high-scoring passages
from chapters in the *approved syllabus*. The AI sees only the chosen excerpts,
and its evidence must be inside those exact excerpts.
"""
import re
import unicodedata

EXCERPT_VERSION = "chapter-fulltext-v2"
EXCERPT_LIMIT = 5600
PASSAGE_SIZE = 1750
OVERLAP = 160
STOP = {
    "chương", "bài", "phần", "nội", "dung", "và", "của", "các",
    "trong", "theo", "cho", "một", "được", "học", "là", "về",
    "những", "kiến", "thức", "tài", "liệu", "môn", "giới", "thiệu",
    "khái", "niệm", "người", "sinh", "viên", "tổng", "quan",
}


def _words(text):
    clean = unicodedata.normalize("NFC", str(text or "")).casefold()
    return set(re.findall(r"[^\W_]+", clean, flags=re.UNICODE)) - STOP


def _phrases(text, size=PASSAGE_SIZE, overlap=OVERLAP):
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [(0, text)]
    step = size - overlap
    result = []
    for start in range(0, len(text), step):
        part = text[start:start + size]
        if part.strip():
            result.append((start, part))
        if start + size >= len(text):
            break
    return result


def select_chapter_excerpts(text, chapters, max_chars=EXCERPT_LIMIT):
    """Return verbatim passages chosen from anywhere in the file.

    Allocate a passage per matching chapter before filling with other good
    passages, so a file containing several distant chapters retains coverage.
    No match: sample beginning/middle/end as *unverified* inspection context,
    never claim chapter support from the sampling alone.
    """
    candidates = _phrases(text)
    if not candidates:
        return ""
    if len(text) <= max_chars:
        return str(text).strip()
    descriptors = []
    for chapter in chapters.values():
        title = str(chapter.get("title") or "")
        topics = " ".join(str(t) for t in (chapter.get("topics") or [])[:8])
        words = {w for w in _words(title + " " + topics) if len(w) >= 3}
        if words:
            descriptors.append(words)
    scored = []
    termsets = [_words(p) for _, p in candidates]
    for query in descriptors:
        matches = sorted(
            ((len(query & words), index) for index, words in enumerate(termsets)),
            key=lambda pair: (-pair[0], candidates[pair[1]][0]),
        )
        if matches and matches[0][0] >= 2:
            scored.append(matches[0])
    selected = []
    for score, index in sorted(scored, key=lambda x: -x[0]):
        if index not in selected:
            selected.append(index)
    general = sorted(
        ((max((len(q & words) for q in descriptors), default=0), index)
         for index, words in enumerate(termsets)),
        key=lambda pair: (-pair[0], candidates[pair[1]][0]),
    )
    selected.extend(i for _, i in general if i not in selected)
    if not any(score >= 2 for score, _ in general):
        selected = list(dict.fromkeys(
            [0, len(candidates)//2, len(candidates)-1] + selected
        ))
    pieces = []
    length = 0
    for index in selected:
        snippet = candidates[index][1].strip()
        room = max_chars - length
        if room < 160:
            break
        if len(snippet) > room:
            snippet = snippet[:room].strip()
        if snippet:
            pieces.append(snippet)
            length += len(snippet) + 2
    return "\n\n".join(pieces)
