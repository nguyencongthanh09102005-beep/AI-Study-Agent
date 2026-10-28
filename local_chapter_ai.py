"""Local multilingual embedding-based classification for course documents.

This module never invokes a remote generative AI API. The pre-trained encoder
runs locally after its weights have been downloaded and cached once.

Document excerpts are the ORIGINAL uploaded text, not generated quotations.
Only an administrator can publish links between documents and chapters.
"""
import hashlib
import math
import os
import re
from functools import lru_cache

DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MIN_SIMILARITY = 0.43
MAX_DOC_CHARS = 45000
MAX_CHUNKS = 100


def normalize(value):
    return " ".join(str(value or "").split())


def source_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@lru_cache(maxsize=1)
def load_model():
    """Load on demand; missing packages/downloads surface an explicit error."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Chưa cài thư viện AI cục bộ. Chạy: pip install -r requirements-ai.txt"
        ) from exc
    model_name = os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    try:
        return SentenceTransformer(model_name, device="cpu")
    except Exception as exc:
        raise RuntimeError(
            "Không tải được mô hình AI cục bộ. Kiểm tra Internet lần chạy đầu, "
            "dung lượng ổ đĩa và quyền truy cập Hugging Face. Không dùng Gemini."
        ) from exc


def document_chunks(text, max_chars=300):
    """Split extracted lines without losing the original evidence text."""
    items = []
    current = []
    length = 0
    for raw in (text or "")[:MAX_DOC_CHARS].replace("\r", "\n").split("\n"):
        line = normalize(raw)
        if not line:
            continue
        # Long paragraphs are still text from the real document, not model output.
        fragments = [line[i:i+max_chars] for i in range(0, len(line), max_chars)]
        for fragment in fragments:
            if current and length + len(fragment) + 1 > max_chars:
                items.append(" ".join(current))
                current, length = [], 0
            current.append(fragment)
            length += len(fragment) + 1
            if len(items) >= MAX_CHUNKS:
                break
        if len(items) >= MAX_CHUNKS:
            break
    if current and len(items) < MAX_CHUNKS:
        items.append(" ".join(current))
    return [x for x in items if len(x) >= 24]


def _float_dot(a, b):
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _norm_vector(vec):
    length = math.sqrt(sum(float(x) * float(x) for x in vec))
    if not length:
        return [0.0 for _ in vec]
    return [float(x) / length for x in vec]


def semantic_chapter_suggestions(document_text, chapters, encoder=None,
                                 min_similarity=MIN_SIMILARITY):
    """Return grounded unapproved semantic suggestions.

    chapters: list of {key,title,topics} from the official course syllabus.
    encoder: injected embedding model for deterministic unit testing.
    Similarity is cosine similarity; it is NOT a calibrated probability.
    """
    if not isinstance(chapters, list) or not chapters:
        return []
    if not isinstance(document_text, str) or not document_text.strip():
        return []
    passages = document_chunks(document_text)
    if not passages:
        return []
    legitimate = []
    seen = set()
    for row in chapters[:40]:
        key = str(row.get("key", "")).strip()
        if not key or key in seen:
            continue
        title = normalize(row.get("title", ""))
        topics = [normalize(s) for s in row.get("topics", [])[:10]]
        if not title:
            continue
        seen.add(key)
        legitimate.append({
            "key": key, "title": title,
            "profile": (title + ". " + ". ".join(topics))[:430],
        })
    if not legitimate:
        return []

    model = encoder if encoder is not None else load_model()
    texts = [row["profile"] for row in legitimate] + passages
    try:
        vectors = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    except TypeError:
        # Also support minimal custom encoders in controlled tests.
        vectors = model.encode(texts)
    except Exception as exc:
        raise RuntimeError("Mô hình AI cục bộ không thể mã hóa nội dung học liệu.") from exc
    vectors = [_norm_vector(v) for v in vectors]
    unit_vectors = vectors[:len(legitimate)]
    passage_vectors = vectors[len(legitimate):]
    output = []
    for row, query_vector in zip(legitimate, unit_vectors):
        scored = sorted((
            (_float_dot(query_vector, text_vector), passage)
            for passage, text_vector in zip(passages, passage_vectors)
        ), reverse=True)
        if not scored:
            continue
        score, excerpt = scored[0]
        # Threshold deliberately conservative. Admin still decides whether
        # the excerpt truly supports the chapter link.
        if score < min_similarity:
            continue
        output.append({
            "chapter_key": row["key"],
            "score": round(float(score), 4),
            "evidence": excerpt[:300],  # exact substring of the uploaded text
            "model": os.getenv("LOCAL_EMBEDDING_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL,
        })
    output.sort(key=lambda x: (-x["score"], x["chapter_key"]))
    return output
