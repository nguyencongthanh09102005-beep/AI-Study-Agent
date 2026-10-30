"""Course-first study sessions grounded in the student's confirmed syllabus.

The PDF parser accepts common bullet and standalone-heading layouts.
It never invents academic chapters, specific exercise requirements or file access.
"""
import hashlib
import json
import re
from datetime import date, timedelta
from syllabus_learning import normalize_heading_prefix

PLAN_VERSION = 5

TOPIC_RE = re.compile(r"^(\d+(?:\.\d+){1,3})[.)]?\s+(.{3,200})$")
CHAPTER_RE = re.compile(
    r"^(?:\d{1,2}\s*[-–]\s*\d{1,2}\s+)?"
    r"(?:[•●▪◦*+\-–—]\s+)?"
    r"(?:chương|chapter|bài|lesson|unit|module)\s+(\d+)\b",
    re.I,
)
CLO_RE = re.compile(r"\bCLO\s*[-:]?\s*\d+\b", re.I)
BULLET_RE = re.compile(r"^[•●▪◦*+\-–—]\s*")
COURSE_END_RE = re.compile(
    r"^\d+\.\s+(?:KẾ HOẠCH GIẢNG DẠY|PHƯƠNG PHÁP GIẢNG DẠY|"
    r"PHƯƠNG PHÁP ĐÁNH GIÁ|TÀI LIỆU HỌC TẬP|TÀI LIỆU THAM KHẢO|"
    r"HƯỚNG DẪN SỬ DỤNG|CƠ CẤU ĐÁNH GIÁ)\b", re.I
)
SECTION_PATTERNS = (
    ("objectives", re.compile(r"^(?:mục tiêu(?: sau chương| chương| bài)?|yêu cầu cần đạt)\s*(?::\s*(.+))?$", re.I)),
    ("topics", re.compile(r"^(?:nội dung kiến thức|nội dung học|kiến thức trọng tâm)\s*(?::\s*(.+))?$", re.I)),
    ("resource_hints", re.compile(r"^(?:học liệu tham chiếu|tài liệu tham chiếu|tài liệu học tập|học liệu)\s*(?::\s*(.+))?$", re.I)),
    ("activities", re.compile(r"^(?:hoạt động học tập(?: đề xuất)?|hoạt động trên lớp)\s*(?::\s*(.+))?$", re.I)),
    ("exercises", re.compile(r"^(?:bài tập(?: thực hành)?|bài thực hành|thực hành)\s*(?::\s*(.+))?$", re.I)),
    ("quiz", re.compile(r"^(?:tự kiểm tra theo chương|kiểm tra cuối chương|quiz theo chương)\s*(?::\s*(.+))?$", re.I)),
    ("criteria", re.compile(r"^(?:tiêu chí(?: gợi ý)? để chuyển tiếp|tiêu chí đạt|yêu cầu đánh giá)\s*(?::\s*(.+))?$", re.I)),
)
STOPWORDS = {
    "chương", "bài", "môn", "học", "các", "một", "theo", "nội", "dung",
    "với", "trong", "được", "những", "của", "phần", "và", "từ", "cho",
    "giới", "thiệu", "sử", "dụng", "kiến", "thức", "thực", "hành",
    "dữ", "liệu", "giải", "thuật", "tổng", "quan", "cấu", "trúc",
}


# Repeated headers in the sample PDF can be standalone or appended after a
# valid sentence by a PDF text extractor. Strip only the known test-page marker,
# preserving the academic text on the same line.
TEST_PDF_HEADER_RE = re.compile(
    r"AI\s+STUDY\s+AGENT\s*/\s*ĐỀ\s+CƯƠNG\s+CHI\s+TIẾT\s+GIẢ\s+LẬP",
    re.I,
)


def normalized_lines(text):
    cleaned = []
    for source in (text or "").replace("\r", "\n").split("\n"):
        line = " ".join(TEST_PDF_HEADER_RE.sub("", source).split()).strip(" ;")
        if line:
            cleaned.append(line)
    return cleaned


def unit_fingerprint(units):
    compact = json.dumps(units, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _clean_bullet(line):
    return BULLET_RE.sub("", line).strip()


def _boilerplate(line):
    low = line.casefold()
    # Repeated PDF page header/footer: never treat them as lesson content.
    return (low.startswith(("ai study agent /", "chỉ dùng kiểm thử",
                            "tài liệu giả lập •", "kết thúc tài liệu giả lập"))
            or bool(re.fullmatch(r"trang\s+\d+(?:\s*/\s*\d+)?", low)))


def _collect_value(bucket, value, limit=8):
    value = value.strip(" \t;")[:350]
    if value and value not in bucket and len(bucket) < limit:
        bucket.append(value)


def parse_chapter_details(text, units):
    """Extract only evidence-backed subtopics and learning activities per chapter."""
    lines = normalized_lines(text)
    cursor, sections = 0, []
    for unit in units:
        evidence = " ".join(str(unit.get("evidence") or "").split())
        position = next((i for i in range(cursor, len(lines))
                         if lines[i].casefold() == evidence.casefold()), -1)
        if position < 0:
            raise ValueError("Không tìm thấy chương đã xác nhận trong đề cương hiện tại.")
        sections.append({"title": unit["title"], "evidence": evidence, "start": position})
        cursor = position + 1

    result = []
    for index, section in enumerate(sections):
        end = sections[index+1]["start"] if index+1 < len(sections) else len(lines)
        body = lines[section["start"]+1:end]
        chapter_match = CHAPTER_RE.match(normalize_heading_prefix(section["evidence"]))
        chapter_num = chapter_match.group(1) if chapter_match else ""
        values = {name: [] for name, _ in SECTION_PATTERNS}
        clos = []
        lesson_periods = 0
        current = None
        for raw in body:
            line = _clean_bullet(raw)
            if not line or _boilerplate(line):
                continue
            if COURSE_END_RE.match(line):
                break
            # A different chapter heading is a hard boundary, even if not approved.
            if CHAPTER_RE.match(normalize_heading_prefix(line)):
                break

            if line.casefold().startswith("thời lượng:"):
                period = re.search(r"(\d+)\s*tiết", line, re.I)
                lesson_periods = int(period.group(1)) if period else 0
                for clo in CLO_RE.findall(line):
                    label = re.sub(r"[\s:-]+", "", clo.upper())
                    if label not in clos:
                        clos.append(label)
                current = None
                continue

            matched_section = None
            for name, pattern in SECTION_PATTERNS:
                m = pattern.fullmatch(line)
                if m:
                    matched_section = name
                    current = name
                    if m.group(1):
                        _collect_value(values[name], m.group(1))
                    break
            if matched_section:
                continue

            topic = TOPIC_RE.match(line)
            if topic and chapter_num and topic.group(1).startswith(chapter_num + "."):
                _collect_value(values["topics"], line, limit=48)
                current = "topics"
                continue

            if current in values:
                # Do not turn an unrelated numbered administrative section into a lesson.
                if re.match(r"^\d+\.\s+", line):
                    current = None
                    continue
                _collect_value(values[current], line, limit=20)

        # Source metadata is descriptive; no learning evidence may be hallucinated.
        quiz_text = " ".join(values["quiz"])
        count_match = re.search(r"(\d{1,2})\s*câu", quiz_text, re.I)
        quiz_count = int(count_match.group(1)) if count_match else None
        criterion_text = " ".join(values["criteria"])
        passing_match = re.search(r"(\d{1,3})\s*%", criterion_text)
        passing_pct = int(passing_match.group(1)) if passing_match else None
        result.append({
            "unit_id": index + 1,
            "chapter": section["title"],
            "evidence": section["evidence"],
            "topics": values["topics"][:36],
            "objectives": values["objectives"][:6],
            "exercises": values["exercises"][:10],
            "resource_hints": values["resource_hints"][:10],
            "class_activities": values["activities"][:10],
            "quiz_description": values["quiz"][:5],
            "passing_criteria": values["criteria"][:5],
            "quiz_count_from_syllabus": quiz_count if quiz_count and 1 <= quiz_count <= 30 else None,
            "passing_percent_from_syllabus": passing_pct if passing_pct and 1 <= passing_pct <= 100 else None,
            "teaching_periods": lesson_periods,
            "clo_refs": clos[:12],
        })
    return result


def _terms(value):
    return {
        term for term in re.findall(r"[\wÀ-ỹ]+", (value or "").casefold(), re.U)
        if len(term) >= 4 and not term.isdigit() and term not in STOPWORDS
    }


def personal_course_documents(conn, user_id, subject_id, exclude_document_id,
                              active_syllabus_text, limit=50):
    """Select private learning files, excluding exact copies of the active syllabus.

    Re-uploaded identical files are shown once. All original files remain stored.
    """
    rows = conn.execute("""
        SELECT id,original_name,extracted_text FROM documents
        WHERE user_id=? AND subject_id=? AND id!=COALESCE(?, -1)
        ORDER BY id DESC LIMIT ?
    """, (user_id, subject_id, exclude_document_id, limit)).fetchall()
    normalized_source = " ".join((active_syllabus_text or "").split()).casefold()
    seen, results = set(), []
    for row in rows:
        body = row["extracted_text"] or ""
        normalized_body = " ".join(body.split()).casefold()
        if not normalized_body or (normalized_source and
                                   normalized_body == normalized_source):
            continue
        dedup_key = (row["original_name"].strip().casefold(), normalized_body)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        results.append({
            "id": row["id"],
            "name": row["original_name"],
            "text": body,
            "kind": "personal",
        })
    return results


def match_course_materials(section, documents):
    """Only return genuinely subject-scoped files with topical text evidence."""
    search_terms = _terms(section["chapter"] + " " + " ".join(section["topics"][:8]))
    from chapter_fulltext_retrieval import _phrases
    ranked = []
    for document in documents:
        # Require topical overlap inside one local passage; combining a term
        # on page 1 with an unrelated term on page 180 is not evidence.
        content = document.get("text") or ""
        name = document.get("name") or ""
        best_matches = set()
        for _, passage in _phrases(content):
            matches = search_terms & _terms(passage)
            if len(matches) > len(best_matches):
                best_matches = matches
        matches = best_matches
        if len(matches) < 2:
            continue
        title_matches = search_terms & _terms(name)
        ranked.append((len(matches) + 2 * len(title_matches), {
            "id": document["id"],
            "name": name[:180],
            "kind": document["kind"],
            "matched_terms": sorted(matches)[:6],
        }))
    ranked.sort(key=lambda x: (-x[0], x[1]["name"].casefold()))
    return [item for _, item in ranked[:3]]


def _credit_session_allocations(chapters, learning_slots):
    """Assign every confirmed chapter at least one evidence-backed learning slot.

    Distribute additional practice using available subtopics and teaching
    periods, not by splitting every two subheadings into a new date.
    """
    if learning_slots < len(chapters):
        raise ValueError(
            f"Lộ trình có {len(chapters)} chương nhưng chỉ có "
            f"{learning_slots} buổi học nội dung (đã dành 1 buổi kiểm tra "
            "cuối môn). Không thể bỏ sót chương; hãy kiểm tra lại tín chỉ "
            "hoặc đề cương."
        )
    weights = [
        max(1, len(chapter.get("topics") or []),
            (int(chapter.get("teaching_periods") or 0) + 2) // 3)
        for chapter in chapters
    ]
    allocations = [1] * len(chapters)
    for _ in range(learning_slots - len(chapters)):
        index = max(
            range(len(chapters)),
            key=lambda i: (weights[i] / (allocations[i] + 1), -i)
        )
        allocations[index] += 1
    return allocations


def _learning_chunks(topics, slots):
    """Every slot has real chapter content; extra slots explicitly review it."""
    if not topics:
        return [[] for _ in range(slots)]
    if len(topics) >= slots:
        base, extra = divmod(len(topics), slots)
        sizes = [base + (1 if i < extra else 0) for i in range(slots)]
        result, offset = [], 0
        for size in sizes:
            result.append(topics[offset:offset + size])
            offset += size
        return result
    return [[topic] for topic in topics] + [topics[:] for _ in
                                                range(slots - len(topics))]


def build_course_roadmap(chapters, documents, profile, weaknesses=None, start_date=None):
    """Schedule concrete syllabus units in verified order; quiz is only a suggestion."""
    if not chapters:
        raise ValueError("Đề cương chưa có chương hợp lệ.")
    goal = (profile.get("goal") or "").strip()[:160]
    daily_minutes = max(15, min(180, int(profile.get("daily_minutes") or 45)))
    preferred_time = (profile.get("preferred_time") or "19:00").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", preferred_time):
        preferred_time = "19:00"
    base_date = start_date or date.today()
    weaknesses = weaknesses or []
    sessions = []
    # When the course has an explicit credit count, the university-sized
    # roadmap has exactly 5 sessions per credit INCLUDING the final exam.
    # Legacy direct callers without credits keep their old chunking behavior.
    has_credits = "credits" in profile
    if has_credits:
        try:
            credits = int(profile["credits"])
        except (TypeError, ValueError) as error:
            raise ValueError("Số tín chỉ phải là số nguyên hợp lệ.") from error
        if not 1 <= credits <= 12:
            raise ValueError("Số tín chỉ để lập lộ trình phải từ 1 đến 12.")
        target_sessions = credits * 5
        allocations = _credit_session_allocations(chapters, target_sessions - 1)
    else:
        chunk_size = (1 if daily_minutes < 35 else 2 if daily_minutes < 75
                      else 3 if daily_minutes < 120 else 4)
        allocations = [
            max(1, (len(chapter["topics"]) + chunk_size - 1) // chunk_size)
            for chapter in chapters
        ]
    for chapter, slots in zip(chapters, allocations):
        topic_items = chapter["topics"]
        topic_chunks = _learning_chunks(topic_items, slots) if has_credits else (
            [topic_items[i:i+chunk_size]
             for i in range(0, len(topic_items), chunk_size)] or [[]]
        )
        materials = match_course_materials(chapter, documents)
        relevant_weaknesses = [
            w["topic"][:140] for w in weaknesses
            if _terms(w.get("topic", "")) and
            len(_terms(w.get("topic", "")) & _terms(
                chapter["chapter"] + " " + " ".join(topic_items))) >= 2
        ][:3]
        for index, chunk in enumerate(topic_chunks):
            chapter_last = index == len(topic_chunks) - 1
            objectives = chapter["objectives"][:2] or (
                ["Nắm được: " + "; ".join(chunk)] if chunk else
                ["Đọc toàn bộ nội dung chương theo đề cương."]
            )
            activities = []
            if has_credits and topic_items and index >= len(topic_items):
                activities.append("Củng cố và vận dụng lại các tiểu mục: " +
                                  "; ".join(chunk))
            elif chunk:
                activities.append("Đọc và thực hành các tiểu mục: " + "; ".join(chunk))
            else:
                activities.append("Đề cương không tách rõ tiểu mục; cần xem chương gốc.")
            if chapter_last and chapter["exercises"]:
                activities.extend("Bài tập từ đề cương: " + entry
                                  for entry in chapter["exercises"][:3])
            elif chapter["class_activities"]:
                activities.append("Hoạt động từ đề cương: "
                                  + chapter["class_activities"][0])
            else:
                activities.append("Gợi ý của hệ thống: giải thích lại các khái niệm vừa học.")
            if relevant_weaknesses:
                activities.append("Ưu tiên ôn: " + "; ".join(relevant_weaknesses))
            quiz_count = chapter["quiz_count_from_syllabus"] or 10
            sessions.append({
                "planner_version": PLAN_VERSION,
                "session_id": len(sessions) + 1,
                "unit_id": chapter["unit_id"],
                "chapter": chapter["chapter"],
                "source_evidence": chapter["evidence"],
                "date": (base_date + timedelta(days=len(sessions))).isoformat(),
                "time": preferred_time,
                "duration": daily_minutes,
                "title": (f'{chapter["chapter"]} — Buổi {index+1}/{len(topic_chunks)}')[:180],
                "topics": chunk,
                "objectives": objectives,
                "activities": activities,
                "materials": materials,
                "source_material_hints": chapter["resource_hints"],
                "quiz": ({
                    "recommended_questions": quiz_count,
                    "question_count_from_syllabus": bool(chapter["quiz_count_from_syllabus"]),
                    "description": chapter["quiz_description"],
                    "passing_criteria": chapter["passing_criteria"],
                    "passing_percent_from_syllabus": chapter["passing_percent_from_syllabus"],
                    "scope": chapter["chapter"],
                    "action": "quiz_chapter",
                    "available": False,
                } if chapter_last else None),
                "weaknesses": relevant_weaknesses,
                "goal": goal,
                "clo_refs": chapter["clo_refs"],
            })
    if has_credits:
        # The last slot is a review/exam slot, NOT a new knowledge chapter.
        # Keep unit_id bound to a confirmed chapter for existing room/ACL
        # checks; the final Quiz engine obtains sources from ALL prior slots.
        last = chapters[-1]
        sessions.append({
            "planner_version": PLAN_VERSION,
            "session_id": len(sessions) + 1,
            "unit_id": last["unit_id"],
            "chapter": last["chapter"],
            "source_evidence": last["evidence"],
            "date": (base_date + timedelta(days=len(sessions))).isoformat(),
            "time": preferred_time,
            "duration": max(daily_minutes, 90),
            "title": "Ôn tập tổng hợp và kiểm tra cuối môn",
            "topics": [],
            "objectives": ["Hệ thống hóa kiến thức đã học từ tất cả các chương."],
            "activities": ["Ôn tập kiến thức các buổi trước.",
                           "Làm bài kiểm tra tổng hợp 60 câu."],
            "materials": [],
            "source_material_hints": [],
            "quiz": {
                "recommended_questions": 60,
                "question_count_from_syllabus": False,
                "description": [],
                "passing_criteria": [],
                "passing_percent_from_syllabus": None,
                "scope": "Tất cả các buổi học trước",
                "action": "quiz_final",
                "available": False,
            },
            "weaknesses": [],
            "goal": goal,
            "clo_refs": [],
        })
        assert len(sessions) == target_sessions
    return sessions
