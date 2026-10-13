"""analyzer.py - topic-wise performance, weak-topic detection and prioritisation.

Input  : a list of attempt dicts for ONE student, e.g.
         {"topic_id": "trees", "correct": 1, "difficulty": "hard",
          "timestamp": "2026-10-01T10:30:00"}          # difficulty/timestamp optional
         `topic_id` may also be a topic NAME ("Stacks & Queues"); `correct` must be 0/1 or
         true/false (blank/NaN/other values are dropped, never counted as wrong).
Output : plain dicts / lists (JSON-serialisable), ready for the API and dashboard.

Mastery model (simple, explainable, no training data needed):
  * recency   : each attempt's weight halves every HALF_LIFE_DAYS
  * difficulty: a correct hard answer earns more credit, a wrong easy answer costs more
  * shrinkage : a prior of PRIOR_STRENGTH pseudo-attempts at 0.5 pulls tiny samples
                towards "unknown" instead of declaring 1/3 correct as "weak"
  * confidence: effective (recency-weighted) attempts / (effective + CONF_K)
  * status    : insufficient_data (<MIN_ATTEMPTS), stale (no attempt for STALE_DAYS),
                weak / developing / strong otherwise
Known limit: MCQ guessing (25% chance) is not modelled; the prior and thresholds absorb most of it.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

DIFF_WEIGHT = {"easy": 0.8, "medium": 1.0, "hard": 1.25}
PRIOR_MEAN, PRIOR_STRENGTH = 0.5, 2.0
HALF_LIFE_DAYS = 30.0
STALE_DAYS = 90
MIN_ATTEMPTS = 3
CONF_K = 5
WEAK_BELOW, STRONG_FROM = 0.50, 0.75
AT_RISK_MASTERY = 0.45
AT_RISK_MIN_TOPICS = 2          # don't label a student at-risk from a single tested topic

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------- helpers
def load_topics(path: str | Path | None = None) -> dict:
    """topic_id -> {name, subject, prerequisites}"""
    with open(path or DATA_DIR / "topics.json", encoding="utf-8") as f:
        return json.load(f)


def _slug(v) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(v or "").strip().lower()).strip("_")


def _topic_index(meta: dict) -> dict:
    """Accept ids AND display names ('Stacks & Queues' -> stacks_queues)."""
    idx = {}
    for tid, m in meta.items():
        idx[_slug(tid)] = tid
        idx[_slug(m.get("name", ""))] = tid
    return idx


def _to_dt(ts):
    if ts is None or ts == "":
        return None
    if isinstance(ts, datetime):
        dt = ts
    else:
        try:
            dt = datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_bool(v):
    """True/False for clear values, None for anything ambiguous (NaN, blank, 2, 'maybe')."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return None
        return bool(v) if v in (0, 1) else None
    s = str(v).strip().lower()
    if s in {"1", "1.0", "true", "yes", "y", "correct"}:
        return True
    if s in {"0", "0.0", "false", "no", "n", "wrong", "incorrect"}:
        return False
    return None


def clean_attempts(attempts, topics_meta=None):
    """Validate/normalise raw rows. Returns (rows, dropped_count, unknown_topic_names)."""
    idx = _topic_index(topics_meta) if topics_meta else None
    rows, dropped, unknown = [], 0, set()
    for a in attempts or []:
        if not isinstance(a, dict):
            dropped += 1
            continue
        raw = a.get("topic_id") or a.get("topic")
        topic = _slug(raw)
        correct = _to_bool(a.get("correct"))
        if not topic or correct is None or a.get("skipped"):
            dropped += 1
            continue
        if idx is not None:
            if topic not in idx:
                dropped += 1
                unknown.add(str(raw))
                continue
            topic = idx[topic]
        diff = str(a.get("difficulty") or "medium").strip().lower()
        rows.append({"topic": topic, "correct": correct,
                     "diff": diff if diff in DIFF_WEIGHT else "medium",
                     "ts": _to_dt(a.get("timestamp"))})
    return rows, dropped, sorted(unknown)


# ------------------------------------------------------ topic-wise performance
def topic_performance(attempts, now=None, topics_meta=None):
    """Per-topic stats. Returns (perf_dict, dropped_rows, unknown_topic_names)."""
    now = _to_dt(now) or datetime.now(timezone.utc)
    rows, dropped, unknown = clean_attempts(attempts, topics_meta)
    grouped = defaultdict(list)
    for i, r in enumerate(rows):
        grouped[r["topic"]].append((r["ts"] or _EPOCH, i, r))

    perf = {}
    for topic, items in grouped.items():
        items.sort(key=lambda x: (x[0], x[1]))
        num = den = eff_n = 0.0
        for _, _, r in items:
            age = max((now - r["ts"]).total_seconds() / 86400, 0) if r["ts"] else 0
            rec = 0.5 ** (age / HALF_LIFE_DAYS)
            dw = DIFF_WEIGHT[r["diff"]]
            credit = rec * (dw if r["correct"] else 2 - dw)
            eff_n += rec
            den += credit
            num += credit if r["correct"] else 0
        mastery = (num + PRIOR_MEAN * PRIOR_STRENGTH) / (den + PRIOR_STRENGTH)

        n = len(items)
        correct_n = sum(1 for _, _, r in items if r["correct"])
        dated = [t for t, _, _ in items if t != _EPOCH]
        last = max(dated) if dated else None
        days_since = (now - last).days if last else None

        trend = "stable"
        if n >= 4:
            half = n // 2
            early = sum(r["correct"] for _, _, r in items[:half]) / half
            late = sum(r["correct"] for _, _, r in items[half:]) / (n - half)
            trend = "improving" if late - early > 0.15 else "declining" if early - late > 0.15 else "stable"

        if n < MIN_ATTEMPTS:
            status = "insufficient_data"
        elif days_since is not None and days_since > STALE_DAYS:
            status = "stale"          # old evidence: don't call it weak OR strong, re-test instead
        elif mastery < WEAK_BELOW:
            status = "weak"
        elif mastery < STRONG_FROM:
            status = "developing"
        else:
            status = "strong"

        perf[topic] = {"topic_id": topic, "attempts": n,
                       "accuracy": round(correct_n / n, 3),
                       "mastery": round(mastery, 3),
                       "confidence": round(eff_n / (eff_n + CONF_K), 3),
                       "status": status, "trend": trend,
                       "last_attempt": last.isoformat() if last else None,
                       "priority": 0.0, "root_cause_for": []}
    return perf, dropped, unknown


# ------------------------------------------------------------- prioritisation
def _prioritise(perf, meta):
    """Priority = how much we should work on this topic NOW.
    Higher when: low mastery, confident data, many topics depend on it, declining,
    or it is the unmastered prerequisite behind another weak topic (root cause)."""
    weak = {t for t, p in perf.items() if p["status"] == "weak"}
    dependents = defaultdict(int)
    for m in meta.values():
        for pre in m.get("prerequisites", []):
            dependents[pre] += 1
    blocks = defaultdict(list)
    for t in weak:
        for pre in meta.get(t, {}).get("prerequisites", []):
            if pre in weak:
                blocks[pre].append(t)

    for t, p in perf.items():
        if p["status"] not in ("weak", "developing"):
            continue
        score = (1 - p["mastery"]) * (0.5 + 0.5 * p["confidence"])
        score *= 1 + 0.10 * dependents.get(t, 0)
        score *= 1 + 0.25 * len(blocks.get(t, []))
        if p["trend"] == "declining":
            score *= 1.15
        elif p["trend"] == "improving":
            score *= 0.90
        if p["status"] == "developing":
            score *= 0.5
        p["priority"] = round(score, 3)
        p["root_cause_for"] = sorted(blocks.get(t, []))


# --------------------------------------------------------------- public API
def analyze_student(attempts, topics_meta=None, now=None, top_n=5) -> dict:
    """Full analysis for one student (this is what GET /students/{id}/analysis returns)."""
    meta = topics_meta or load_topics()
    perf, dropped, unknown = topic_performance(attempts, now, meta)
    _prioritise(perf, meta)

    topics = []
    for t, p in perf.items():
        m = meta.get(t, {})
        topics.append({**p, "name": m.get("name", t), "subject": m.get("subject", "Other")})
    topics.sort(key=lambda x: x["mastery"])

    scored = [x for x in topics if x["status"] in ("weak", "developing", "strong")]
    by_subject = defaultdict(list)
    for x in scored:
        by_subject[x["subject"]].append(x["mastery"])

    weak = sorted((x for x in topics if x["status"] == "weak"), key=lambda x: -x["priority"])
    developing = sorted((x for x in topics if x["status"] == "developing"), key=lambda x: -x["priority"])
    return {
        "overall_mastery": round(sum(x["mastery"] for x in scored) / len(scored), 3) if scored else None,
        "subject_mastery": {s: round(sum(v) / len(v), 3) for s, v in by_subject.items()},
        "topics": topics,
        "weak_topics": weak[:top_n],
        "developing_topics": developing[:top_n],
        "strong_topics": [x["topic_id"] for x in topics if x["status"] == "strong"],
        "retest_topics": [x["topic_id"] for x in topics if x["status"] == "stale"],
        "untested_topics": [t for t in meta if t not in perf],
        "data_quality": {
            "rows_used": sum(x["attempts"] for x in topics),
            "rows_dropped": dropped,
            "unknown_topics": unknown,      # show these to the uploader: usually typos
            "insufficient_data": [x["topic_id"] for x in topics if x["status"] == "insufficient_data"],
        },
    }


def class_overview(attempts_by_student: dict, topics_meta=None, now=None) -> dict:
    """Faculty view. attempts_by_student: {student_id: [attempt, ...]}"""
    meta = topics_meta or load_topics()
    per_topic = defaultdict(list)
    students, at_risk = [], []
    for sid, att in attempts_by_student.items():
        a = analyze_student(att, meta, now)
        students.append({"student_id": sid, "overall_mastery": a["overall_mastery"],
                         "weak_topics": [w["topic_id"] for w in a["weak_topics"]]})
        tested = [t for t in a["topics"] if t["status"] in ("weak", "developing", "strong")]
        for t in tested:
            per_topic[t["topic_id"]].append(t)
        if len(tested) >= AT_RISK_MIN_TOPICS and (
                a["overall_mastery"] < AT_RISK_MASTERY
                or sum(t["status"] == "weak" for t in tested) / len(tested) >= 0.4):
            at_risk.append(sid)
    topic_stats = [{"topic_id": t, "name": meta.get(t, {}).get("name", t),
                    "avg_mastery": round(sum(x["mastery"] for x in v) / len(v), 3),
                    "pct_weak": round(sum(x["status"] == "weak" for x in v) / len(v), 3),
                    "students": len(v)} for t, v in per_topic.items()]
    topic_stats.sort(key=lambda x: x["avg_mastery"])
    return {"topics": topic_stats, "at_risk_students": at_risk, "students": students}
