"""Glue between the database and the AI engine: what a student has done -> what to show next."""
import math
from functools import lru_cache

from ..ai_engine import analyze_student, load_topics
from ..ai_engine.quiz_engine import get_bank
from ..ai_engine.recommendations import load_resources
from ..config import LEVEL_BASE, LEVELS, PASS_RATIO, QUIZ_MAX, QUIZ_MIN, TIME_PER_QUESTION, TOPIC_COMPLEXITY


@lru_cache(maxsize=1)
def topics() -> dict:
    return load_topics()


@lru_cache(maxsize=1)
def resources() -> list:
    return load_resources()


def subject_names() -> list:
    seen = []
    for m in topics().values():
        if m["subject"] not in seen:
            seen.append(m["subject"])
    return seen


def module_ids(subject: str) -> list:
    return [t for t, m in topics().items() if m["subject"] == subject]


def pass_mark(total: int) -> int:
    """Smallest score that passes a quiz of `total` questions."""
    return max(1, math.ceil(PASS_RATIO * total - 1e-9))


def grade_attempt(score: int, total: int) -> dict:
    """Single grading rule, judged against the questions actually served in that attempt.

    Use this both when saving a submission and when summarising history, so the stored
    score/total and the pass decision can never disagree (quiz sets may vary in size)."""
    if total <= 0:
        return {"score": 0, "total": 0, "pass_mark": 0, "passed": False}
    score = max(0, min(int(score), int(total)))
    need = pass_mark(total)
    return {"score": score, "total": total, "pass_mark": need, "passed": score >= need}


def question_counts(topic_id: str) -> dict:
    counts = {d: 0 for d in LEVELS}
    for q in get_bank().for_topic(topic_id):
        if q["difficulty"] in counts:
            counts[q["difficulty"]] += 1
    return counts


def target_size(topic_id: str, difficulty: str) -> int:
    """Desired quiz length: level base x topic complexity, clamped to [QUIZ_MIN, QUIZ_MAX]."""
    raw = round(LEVEL_BASE[difficulty] * TOPIC_COMPLEXITY.get(topic_id, 1.0))
    return max(QUIZ_MIN, min(QUIZ_MAX, raw))


def quiz_size(topic_id: str, difficulty: str) -> int:
    """Nominal quiz length for display/planning: the target, or the whole pool if smaller.

    With dynamic selection the real length of an attempt is whatever was served and recorded
    as `total`; grading must use that total, not this value."""
    return min(target_size(topic_id, difficulty), question_counts(topic_id)[difficulty])


def attempts_for(db, student_id: int) -> list:
    rows = db.execute("SELECT topic_id, correct, difficulty, timestamp FROM attempts "
                      "WHERE student_id = ? ORDER BY id", (student_id,)).fetchall()
    return [dict(r) for r in rows]


def analysis_for(db, student_id: int) -> dict:
    return analyze_student(attempts_for(db, student_id))


def results_summary(db, student_id: int) -> dict:
    """{(topic_id, difficulty): {best_score, best_total, best_pass_mark, passed, tries}}.

    Every attempt is graded against its own `total`; `passed` is derived from the scores
    (not the stored flag), and best_score/best_total always come from one single attempt."""
    out = {}
    rows = db.execute("SELECT topic_id, difficulty, score, total FROM quiz_results "
                      "WHERE student_id = ? AND difficulty != 'practice' ORDER BY id", (student_id,))
    for r in rows:
        g = grade_attempt(r["score"], r["total"])
        if g["total"] == 0:
            continue                       # malformed/empty attempt: not countable
        cur = out.get((r["topic_id"], r["difficulty"]))
        if cur is None:
            cur = out[(r["topic_id"], r["difficulty"])] = {
                "best_score": g["score"], "best_total": g["total"],
                "best_pass_mark": g["pass_mark"], "passed": False, "tries": 0}
        cur["tries"] += 1
        cur["passed"] = cur["passed"] or g["passed"]
        # compare ratios by cross-multiplication (different totals, no float error); ties -> latest
        if g["score"] * cur["best_total"] >= cur["best_score"] * g["total"]:
            cur["best_score"], cur["best_total"] = g["score"], g["total"]
            cur["best_pass_mark"] = g["pass_mark"]
    return out


def levels_for(topic_id: str, summary: dict) -> list:
    """The easy/medium/hard rows for one module, with lock state."""
    counts = question_counts(topic_id)
    levels, prev_passed = [], True
    for d in LEVELS:
        if counts[d] == 0:
            continue                       # a level with no questions does not exist (yet)
        s = summary.get((topic_id, d))
        n = quiz_size(topic_id, d)
        # "questions"/"pass_mark" are the nominal plan; each attempt is graded on its own total
        levels.append({"difficulty": d, "questions": n, "pool": counts[d],
                       "time_limit_seconds": TIME_PER_QUESTION * n,
                       "pass_mark": pass_mark(n),
                       "unlocked": prev_passed,
                       "passed": bool(s and s["passed"]),
                       "best_score": s["best_score"] if s else None,
                       "best_total": s["best_total"] if s else None,
                       "best_pass_mark": s["best_pass_mark"] if s else None,
                       "tries": s["tries"] if s else 0})
        prev_passed = bool(s and s["passed"])
    return levels


def module_view(topic_id: str, summary: dict, analysis_topics: dict) -> dict:
    meta = topics()[topic_id]
    levels = levels_for(topic_id, summary)
    done = sum(1 for l in levels if l["passed"])
    a = analysis_topics.get(topic_id)
    return {"topic_id": topic_id, "name": meta["name"], "subject": meta["subject"],
            "prerequisites": [{"topic_id": p, "name": topics()[p]["name"]} for p in meta.get("prerequisites", [])],
            "levels": levels, "levels_passed": done, "levels_total": len(levels),
            "completed": bool(levels) and done == len(levels),
            "mastery": a["mastery"] if a else None,
            "status": a["status"] if a else "not_started",
            "trend": a["trend"] if a else None}
