"""recommendations.py - resource recommendations and the personalised study plan.

Resources are matched to the student's LEVEL on a topic (low mastery -> beginner
material, high mastery -> advanced practice), optionally biased to a preferred
format (video / article / practice).
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
LEVELS = ("beginner", "intermediate", "advanced")


def load_resources(path=None) -> list:
    with open(path or DATA_DIR / "resource_bank.json", encoding="utf-8") as f:
        return json.load(f)


def level_for(mastery: float) -> str:
    return "beginner" if mastery < 0.35 else "intermediate" if mastery < 0.65 else "advanced"


def _focus_label(mastery: float) -> str:
    return "easy-focused" if mastery < 0.35 else "mixed" if mastery < 0.60 else "hard-focused"


# -------------------------------------------------------------- recommendations
def recommend_resources(topic_id, mastery, resources=None, k=3, preferred_types=None,
                        exclude_ids=()) -> list:
    """Top-k resources for one topic, best level match first."""
    resources = resources if resources is not None else load_resources()
    target = LEVELS.index(level_for(mastery))
    pref = set(preferred_types or [])
    scored = []
    for r in resources:
        if r["topic_id"] != topic_id or r["id"] in exclude_ids:
            continue
        dist = abs(LEVELS.index(r["level"]) - target)
        score = {0: 3.0, 1: 1.0}.get(dist, 0.0) + (1.0 if r["type"] in pref else 0.0)
        if r.get("link_type") == "search":
            score -= 0.5          # a direct page beats a "search YouTube" fallback
        scored.append((score, -r["minutes"], r))  # shorter wins ties
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [r for _, _, r in scored[:k]]


def recommend_for_student(analysis: dict, resources=None, max_topics=3, per_topic=2,
                          preferred_types=None) -> list:
    """For the student's top weak topics: [{topic_id, name, mastery, level, resources}]"""
    resources = resources if resources is not None else load_resources()
    focus = analysis.get("weak_topics") or analysis.get("developing_topics") or []
    return [{"topic_id": t["topic_id"], "name": t["name"], "mastery": t["mastery"],
             "level": level_for(t["mastery"]),
             "resources": recommend_resources(t["topic_id"], t["mastery"], resources,
                                              per_topic, preferred_types)}
            for t in focus[:max_topics]]


# -------------------------------------------------------------------- study plan
def build_study_plan(analysis: dict, days=7, minutes_per_day=60, resources=None,
                     max_topics=4) -> dict:
    """Day-by-day plan. Root-cause (prerequisite) topics come first; time is split
    across focus topics in proportion to priority; the last day is a checkpoint."""
    resources = resources if resources is not None else load_resources()
    days = max(2, int(days))
    minutes_per_day = max(20, int(minutes_per_day))
    focus = list((analysis.get("weak_topics") or analysis.get("developing_topics") or [])[:max_topics])
    if not focus:
        retest = analysis.get("retest_topics") or []
        msg = ("No weak or developing topics found yet. Take more quizzes, or try harder practice "
               "sets to keep growing.")
        if retest:
            msg += " Re-test these topics, your last results are old: " + ", ".join(retest) + "."
        return {"focus_topics": [], "days": [], "total_minutes": 0, "message": msg}

    focus.sort(key=lambda t: (not t["root_cause_for"], -t["priority"]))  # prerequisites first
    slots = days - 1
    focus = focus[:slots]

    # largest-remainder allocation of learning days, at least one per topic
    weights = [max(t["priority"], 0.01) for t in focus]
    extra = slots - len(focus)
    quota = [extra * w / sum(weights) for w in weights]
    alloc = [1 + int(q) for q in quota]
    leftover = slots - sum(alloc)
    for i in sorted(range(len(focus)), key=lambda i: quota[i] - int(quota[i]), reverse=True)[:leftover]:
        alloc[i] += 1

    plan, day_no = [], 1
    for topic, n_days in zip(focus, alloc):
        recs = recommend_resources(topic["topic_id"], topic["mastery"], resources, k=max(n_days, 1))
        for i in range(n_days):
            learn = round(minutes_per_day * 0.40)
            practice = round(minutes_per_day * 0.45)
            review = minutes_per_day - learn - practice
            res = recs[i % len(recs)] if recs else None
            plan.append({
                "day": day_no, "topic_id": topic["topic_id"], "topic_name": topic["name"],
                "tasks": [
                    {"type": "learn", "minutes": learn,
                     "resource": res and {k_: res.get(k_) for k_ in ("id", "title", "type", "provider", "minutes", "link_type", "url")}},
                    {"type": "practice", "minutes": practice,
                     "questions": max(3, practice // 2), "target_difficulty": _focus_label(topic["mastery"])},
                    {"type": "review", "minutes": review,
                     "note": ("Write a one-page summary of the key ideas." if i == 0
                              else "Re-attempt the questions you got wrong last time.")}]})
            day_no += 1
    plan.append({"day": day_no, "topic_id": None, "topic_name": "Checkpoint",
                 "tasks": [{"type": "checkpoint", "minutes": minutes_per_day,
                            "questions": 10,
                            "note": "Mixed quiz across your focus topics; results update your mastery scores."
                                    + (" Also re-test: " + ", ".join(analysis["retest_topics"]) + "."
                                       if analysis.get("retest_topics") else "")}]})
    return {"focus_topics": [{"topic_id": t["topic_id"], "name": t["name"], "mastery": t["mastery"],
                              "why": ("Prerequisite for: " + ", ".join(t["root_cause_for"]))
                              if t["root_cause_for"] else f"Mastery {t['mastery']:.0%}"} for t in focus],
            "days": plan, "total_minutes": minutes_per_day * len(plan)}
