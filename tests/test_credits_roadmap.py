"""Credit-aware roadmap regression: exactly 5 lessons/credit, exam included."""
from datetime import date
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from course_path_learning import build_course_roadmap, PLAN_VERSION


def chapter(i, topics=3, periods=6):
    return {
        "unit_id": i, "chapter": f"Chương {i}. Nội dung {i}",
        "evidence": f"Chương {i}. Nội dung {i}",
        "topics": [f"{i}.{j}. Tiểu mục chuyên môn {i}-{j}"
                   for j in range(1, topics + 1)],
        "objectives": [f"Hiểu chương {i}"],
        "exercises": [f"Bài tập chương {i}"],
        "resource_hints": [], "class_activities": [], "quiz_description": [],
        "passing_criteria": [], "quiz_count_from_syllabus": None,
        "passing_percent_from_syllabus": None, "teaching_periods": periods,
        "clo_refs": [],
    }


def test():
    chapters = [chapter(i, topics=3 + i % 2, periods=3 + i)
                for i in range(1, 7)]
    base = {"goal": "Học tốt", "daily_minutes": 45,
            "preferred_time": "19:00", "credits": 3}
    plan = build_course_roadmap(chapters, [], base, start_date=date(2026, 11, 1))
    assert len(plan) == 15
    assert [x["session_id"] for x in plan] == list(range(1, 16))
    assert all(x["planner_version"] == PLAN_VERSION for x in plan)
    assert {x["unit_id"] for x in plan[:-1]} == set(range(1, 7))
    for ch in chapters:
        covered = {t for s in plan[:-1] if s["unit_id"] == ch["unit_id"]
                   for t in s["topics"]}
        assert covered == set(ch["topics"]), (ch["unit_id"], covered)
    assert plan[-1]["title"] == "Ôn tập tổng hợp và kiểm tra cuối môn"
    assert plan[-1]["topics"] == []
    assert plan[-1]["quiz"]["recommended_questions"] == 60
    assert plan[-1]["duration"] >= 90
    assert plan[0]["duration"] == 45
    assert plan[-1]["session_id"] == 15
    assert "15 câu" not in plan[-1]["title"]
    assert all(not s["title"].startswith("Ôn tập tổng hợp")
               for s in plan[:-1])

    for credit in (1, 2, 3, 4, 6, 12):
        # Keep 2 chapters so every credit tier has room for a final exam.
        selected = [chapter(1), chapter(2)]
        p = build_course_roadmap(
            selected, [], {**base, "credits": credit},
            start_date=date(2026, 11, 1))
        assert len(p) == 5 * credit, (credit, len(p))
        assert p[-1]["quiz"]["recommended_questions"] == 60
        assert {x["unit_id"] for x in p[:-1]} == {1, 2}
        assert [x["session_id"] for x in p] == list(range(1, 5*credit + 1))

    # One credit gives 4 learning slots + one final, which cannot
    # faithfully represent six distinct source-grounded chapters.
    try:
        build_course_roadmap(chapters, [], {**base, "credits": 1})
    except ValueError as error:
        assert "6 chương" in str(error)
        assert "4 buổi" in str(error)
    else:
        raise AssertionError("Cannot silently drop two academic chapters")

    for credit in (0, -1, 13, "abc"):
        try:
            build_course_roadmap(chapters, [], {**base, "credits": credit})
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid credit value accepted: {credit}")

    # If course metadata has not been supplied (old direct call), preserve
    # backwards compatibility rather than pretending a credit count.
    old = build_course_roadmap(
        [chapter(1)], [], {"daily_minutes": 45, "preferred_time": "19:00"})
    assert len(old) == 2

    print("Credit-based 5 sessions/credit, 6-chapter coverage and final exam OK")


if __name__ == "__main__":
    test()
