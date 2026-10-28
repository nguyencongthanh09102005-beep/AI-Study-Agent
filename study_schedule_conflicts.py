"""Detect overlapping study sessions and suggest an *optional* free time.

Never edits existing records. Works across all subjects for one student, including
manual, AI and roadmap tasks. Adjacent ranges are not conflicts.
"""
from datetime import datetime, timedelta


def _interval(row):
    try:
        start = datetime.fromisoformat(str(row["study_at"]))
        duration = int(row["duration"])
        if start.tzinfo is not None or not 1 <= duration <= 1440:
            return None
        return start, start + timedelta(minutes=duration)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def _next_free_slot(start, duration, busy):
    """Same-day 15-minute-spaced suggestion, not an automatic reschedule."""
    midnight = datetime.combine(start.date() + timedelta(days=1), datetime.min.time())
    candidate = start
    while candidate + duration <= midnight:
        colliding = [end for occupied_start, end in busy
                     if candidate < end and occupied_start < candidate + duration]
        if not colliding:
            return candidate.isoformat(timespec="minutes")
        # Allow a short break after the latest conflicting lesson.
        candidate = max(colliding) + timedelta(minutes=15)
        remainder = candidate.minute % 15
        if remainder or candidate.second or candidate.microsecond:
            candidate = candidate.replace(second=0, microsecond=0)
            candidate += timedelta(minutes=(15 - remainder) % 15)
        if candidate >= midnight:
            break
    return ""


def find_study_conflicts(rows):
    """Return {task_id: {with_titles, with_ids, suggested_at}} for overlaps.

    The caller must scope rows to a single user; this helper never fetches data.
    """
    intervals = []
    for row in rows:
        span = _interval(row)
        if span is None:
            continue
        intervals.append({
            "id": int(row["id"]),
            "title": str(row["title"] or "Buổi học"),
            "start": span[0], "end": span[1],
        })
    overlaps = {}
    for i, left in enumerate(intervals):
        for right in intervals[i + 1:]:
            if left["start"] < right["end"] and right["start"] < left["end"]:
                overlaps.setdefault(left["id"], []).append(right)
                overlaps.setdefault(right["id"], []).append(left)

    results = {}
    for lesson in intervals:
        others = overlaps.get(lesson["id"])
        if not others:
            continue
        duration = lesson["end"] - lesson["start"]
        busy = [(row["start"], row["end"]) for row in intervals
                if row["id"] != lesson["id"]]
        results[lesson["id"]] = {
            "with_ids": [r["id"] for r in others],
            "with_titles": [r["title"] for r in others],
            "suggested_at": _next_free_slot(lesson["start"], duration, busy),
        }
    return results
