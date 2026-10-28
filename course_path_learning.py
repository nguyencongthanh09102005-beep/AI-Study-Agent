"""Course-first study path derived from approved syllabus chapters.

This module never invents chapters, pages, CLO relationships or document content.
Only actual subject-owned/shared materials may be suggested.
"""
import hashlib
import json
import re
from datetime import date, timedelta

TOPIC_RE = re.compile(r"^(\d+(?:\.\d+){1,3})[.)]?\s+(.{3,200})$")
CHAPTER_RE = re.compile(r"^(?:chương|chapter|bài|lesson|unit|module)\s+(\d+)\b", re.I)
OBJECTIVE_RE = re.compile(r"^(?:mục tiêu(?: chương| bài)?|yêu cầu cần đạt)\s*[:：]\s*(.+)", re.I)
EXERCISE_RE = re.compile(r"^(?:bài tập|thực hành|bài thực hành)\s*[:：]\s*(.+)", re.I)
RESOURCE_RE = re.compile(r"^(?:tài liệu|học liệu|slide|giáo trình)\s*[:：]\s*(.+)", re.I)
CLO_RE = re.compile(r"\bCLO\s*[-:]?\s*\d+\b", re.I)
NON_TOPICS = {"mục tiêu", "đánh giá", "tài liệu", "tham khảo", "chuẩn đầu ra"}

STOPWORDS = {
    "chương", "bài", "môn", "học", "các", "một", "theo", "nội", "dung",
    "với", "trong", "được", "những", "của", "phần", "và", "từ", "cho",
    "giới", "thiệu", "sử", "dụng", "kiến", "thức", "thực", "hành",
    "dữ", "liệu", "giải", "thuật", "tổng", "quan", "cấu", "trúc",
}


def normalized_lines(text):
    return [" ".join(line.split()) for line in (text or "").replace("\r", "\n").split("\n") if line.strip()]


def unit_fingerprint(units):
    compact = json.dumps(units, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def parse_chapter_details(text, units):
    """Extract sections ONLY between approved source-evidence headings."""
    lines = normalized_lines(text)
    cursor = 0
    sections = []
    for unit in units:
        evidence = " ".join(str(unit.get("evidence", "")).split())
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
        chapter_match = CHAPTER_RE.match(section["evidence"])
        chapter_num = chapter_match.group(1) if chapter_match else ""
        topics, seen = [], set()
        objectives, exercises, resource_hints, clos = [], [], [], []
        for line in body:
            topic = TOPIC_RE.match(line)
            if topic and chapter_num and topic.group(1).startswith(chapter_num + "."):
                label = line[:220]
                if label.casefold() not in seen:
                    topics.append(label)
                    seen.add(label.casefold())
                continue
            # Stop considering administrative sections, but do not expand to other chapters.
            if re.match(r"^\d+\.\s+(?:phương pháp|tài liệu tham khảo|đánh giá|kế hoạch giảng dạy)\b", line, re.I):
                break
            objective = OBJECTIVE_RE.match(line)
            exercise = EXERCISE_RE.match(line)
            resource = RESOURCE_RE.match(line)
            if objective:
                objectives.append(objective.group(1)[:280])
            elif exercise:
                exercises.append(exercise.group(1)[:280])
            elif resource:
                resource_hints.append(resource.group(1)[:240])
            for clo in CLO_RE.findall(line):
                label = re.sub(r"\s+", "", clo.upper()).replace("-", "").replace(":", "")
                if label not in clos:
                    clos.append(label)
        result.append({
            "unit_id": index + 1,
            "chapter": section["title"],
            "evidence": section["evidence"],
            "topics": topics[:36],
            "objectives": objectives[:6],
            "exercises": exercises[:10],
            "resource_hints": resource_hints[:10],
            "clo_refs": clos[:12],
        })
    return result


def _terms(value):
    return {
        term for term in re.findall(r"[\wÀ-ỹ]+", (value or "").casefold(), re.U)
        if len(term) >= 4 and not term.isdigit() and term not in STOPWORDS
    }


def match_course_materials(section, documents):
    """Return only subject-scoped documents with topical evidence; do not fabricate a match."""
    search_terms = _terms(section["chapter"] + " " + " ".join(section["topics"][:8]))
    ranked = []
    for document in documents:
        content = (document.get("text") or "")[:18000]
        name = document.get("name") or ""
        # Require content-based evidence, not just a misleading filename.
        matches = search_terms & _terms(content)
        if len(matches) < 2:
            continue
        title_matches = search_terms & _terms(name)
        score = len(matches) + len(title_matches) * 2
        ranked.append((score, {
            "id": document["id"],
            "name": name[:180],
            "kind": document["kind"],
            "matched_terms": sorted(matches)[:6],
        }))
    ranked.sort(key=lambda x: (-x[0], x[1]["name"].casefold()))
    return [item for _, item in ranked[:3]]


def build_course_roadmap(chapters, documents, profile, weaknesses=None, start_date=None):
    """Produce independently verifiable, course-scoped sessions in syllabus order."""
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
    for chapter in chapters:
        topic_items = chapter["topics"]
        # Split large chapters into manageable chunks, no artificial topic invention.
        topic_chunks = [topic_items[i:i+3] for i in range(0, len(topic_items), 3)] or [[]]
        materials = match_course_materials(chapter, documents)
        relevant_weaknesses = [
            w["topic"][:140] for w in weaknesses
            if _terms(w.get("topic", "")) and
            len(_terms(w.get("topic", "")) & _terms(chapter["chapter"] + " " + " ".join(topic_items))) >= 2
        ][:3]
        for offset, chunk in enumerate(topic_chunks):
            chapter_last = offset == len(topic_chunks) - 1
            title = f'{chapter["chapter"]} — Buổi {offset + 1}/{len(topic_chunks)}'
            notes = chapter["objectives"][:2] if chapter["objectives"] else []
            if not notes:
                notes = [f"Nắm được: {x}" for x in chunk] if chunk else [f"Tìm hiểu nội dung {chapter['chapter']} từ đề cương."]
            activities = []
            if chunk:
                activities.append("Đọc các mục: " + "; ".join(chunk))
            else:
                activities.append("Đọc và ghi chú nội dung chương trong đề cương.")
            if chapter["exercises"] and chapter_last:
                activities.append("Bài tập trong đề cương: " + "; ".join(chapter["exercises"][:2]))
            else:
                activities.append("Gợi ý của hệ thống: viết tóm tắt và tự giải thích các khái niệm vừa học.")
            if relevant_weaknesses:
                activities.append("Ưu tiên ôn: " + "; ".join(relevant_weaknesses))
            sessions.append({
                "session_id": len(sessions)+1,
                "unit_id": chapter["unit_id"],
                "chapter": chapter["chapter"],
                "source_evidence": chapter["evidence"],
                "date": (base_date + timedelta(days=len(sessions))).isoformat(),
                "time": preferred_time,
                "duration": daily_minutes,
                "title": title[:180],
                "topics": chunk,
                "objectives": notes,
                "activities": activities,
                "materials": materials,
                "source_material_hints": chapter["resource_hints"],
                "quiz": {
                    "recommended_questions": 10,
                    "scope": chapter["chapter"],
                    "action": "quiz_chapter",
                    "available": False,  # Actual chapter-scoped Quiz is a later milestone.
                } if chapter_last else None,
                "weaknesses": relevant_weaknesses,
                "goal": goal,
                "clo_refs": chapter["clo_refs"],
            })
    return sessions
