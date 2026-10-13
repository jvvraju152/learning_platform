"""quiz_engine.py - adaptive practice questions, explanations and grading.

Flow:  mastery -> difficulty mix -> pick unseen questions from the curated bank
       -> (optional) top up with LLM-generated questions -> validate -> verify -> cache.
The curated bank always works offline, so the demo never depends on an API.

LLM top-up is OFF unless ANTHROPIC_API_KEY is set (model: QUIZ_LLM_MODEL, default
claude-sonnet-5-5). Generated questions must pass (1) structural validation,
(2) duplicate check, and (3) an independent second-pass: the model answers each question
WITHOUT seeing the key, and the question is kept only if it agrees. If the verification
call fails, the questions are discarded (correctness over quantity).
"""
from __future__ import annotations

import json
import os
import random
import re
import tempfile
import urllib.request
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DIFFS = ("easy", "medium", "hard")
MAX_N = 20


# ------------------------------------------------------------ difficulty logic
def difficulty_mix(mastery: float, n: int) -> dict:
    """How many easy/medium/hard questions for a student at this mastery."""
    if mastery < 0.35:
        frac = (0.6, 0.4, 0.0)
    elif mastery < 0.60:
        frac = (0.3, 0.5, 0.2)
    else:
        frac = (0.1, 0.4, 0.5)
    counts = [int(n * f) for f in frac]
    counts[1] += n - sum(counts)  # remainder goes to medium
    return dict(zip(DIFFS, counts))


def _norm(text: str) -> str:
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def validate_question(q: dict) -> bool:
    """Reject malformed LLM output (wrong option count, bad key, empty explanation...)."""
    try:
        opts = q["options"]
        return (isinstance(q["question"], str) and len(q["question"].strip()) > 10
                and isinstance(opts, list) and len(opts) == 4
                and all(isinstance(o, str) and o.strip() for o in opts)
                and len({_norm(o) for o in opts}) == 4
                and isinstance(q["answer_index"], int) and not isinstance(q["answer_index"], bool)
                and 0 <= q["answer_index"] < 4
                and isinstance(q["explanation"], str) and len(q["explanation"].strip()) > 10)
    except (KeyError, TypeError):
        return False


# ------------------------------------------------------------------ the bank
class QuestionBank:
    def __init__(self, bank_path=None, generated_path=None):
        self.bank_path = Path(bank_path or DATA_DIR / "question_bank.json")
        self.gen_path = Path(generated_path or DATA_DIR / "generated_questions.json")
        self.questions = {}
        for p in (self.bank_path, self.gen_path):
            if p.exists():
                for q in json.loads(p.read_text(encoding="utf-8")):
                    self.questions[q["id"]] = q

    def for_topic(self, topic_id):
        return [q for q in self.questions.values() if q["topic_id"] == topic_id]

    def is_duplicate(self, q):
        key = _norm(q["question"])
        return any(_norm(x["question"]) == key for x in self.for_topic(q["topic_id"]))

    def add_generated(self, new_questions):
        gen = [q for q in self.questions.values() if q.get("source") == "llm"] + list(new_questions)
        fd, tmp = tempfile.mkstemp(dir=self.gen_path.parent, suffix=".tmp")   # atomic write
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(gen, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.gen_path)
        for q in new_questions:
            self.questions[q["id"]] = q


@lru_cache(maxsize=1)
def get_bank() -> QuestionBank:
    """Shared default bank: loaded once, not re-read from disk on every request."""
    return QuestionBank()


def _public(q: dict) -> dict:
    """What the client sees: never include the answer or explanation."""
    return {"id": q["id"], "topic_id": q["topic_id"], "difficulty": q["difficulty"],
            "question": q["question"], "options": q["options"], "source": q.get("source", "curated")}


# --------------------------------------------------------------- LLM top-up
def _call_llm(prompt, max_tokens=1500, timeout=25):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": os.environ.get("QUIZ_LLM_MODEL", "claude-sonnet-5-5"),
                       "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        text = "".join(b.get("text", "") for b in data["content"])
        return re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    except Exception:  # network, auth, bad payload -> caller falls back to the bank
        return None


def _llm_generate(topic_name, subject, difficulty, count):
    if count <= 0:
        return []
    text = _call_llm(
        f"Write {count} multiple-choice questions for an engineering student on '{topic_name}' "
        f"({subject}), difficulty: {difficulty}. Each must have exactly 4 distinct options and "
        "exactly ONE correct answer. Respond with ONLY a JSON array, no markdown, items shaped like "
        '{"question": str, "options": [4 strings], "answer_index": 0-3, "explanation": str '
        "(2 sentences, why the answer is right)}.")
    try:
        items = json.loads(text) if text else []
        return items if isinstance(items, list) else []
    except json.JSONDecodeError:
        return []


def _llm_verify(questions):
    """Independent solve: the model sees the question and options but NOT the key.
    Returns a list of chosen indices (None where unsure); all None if the call fails."""
    listing = "\n\n".join(f"Q{i + 1}. {q['question']}\n" + "\n".join(f"  {j}: {o}" for j, o in enumerate(q["options"]))
                          for i, q in enumerate(questions))
    text = _call_llm("Solve each multiple-choice question. Reply with ONLY a JSON array of integers, one per "
                     "question, giving the index (0-3) of the single correct option, or -1 if no option or "
                     "more than one option is correct.\n\n" + listing, max_tokens=300)
    try:
        ans = json.loads(text) if text else None
        if isinstance(ans, list) and len(ans) == len(questions):
            return [a if isinstance(a, int) and 0 <= a <= 3 else None for a in ans]
    except json.JSONDecodeError:
        pass
    return [None] * len(questions)


def _llm_topup(topic_id, meta, difficulty, count, bank, rng, require_verification=True):
    cands = []
    for item in _llm_generate(meta["name"], meta["subject"], difficulty, count):
        q = {"topic_id": topic_id, "difficulty": difficulty, "source": "llm",
             "question": item.get("question", "") if isinstance(item, dict) else "",
             "options": item.get("options") if isinstance(item, dict) else None,
             "answer_index": item.get("answer_index") if isinstance(item, dict) else None,
             "explanation": item.get("explanation", "") if isinstance(item, dict) else ""}
        if validate_question(q) and not bank.is_duplicate(q) and not any(_norm(q["question"]) == _norm(c["question"]) for c in cands):
            cands.append(q)
    if not cands:
        return []
    if require_verification:
        solved = _llm_verify(cands)
        cands = [q for q, s in zip(cands, solved) if s == q["answer_index"]]
    out = []
    for q in cands:
        order = list(range(4))                       # shuffle: LLMs favour certain answer slots
        rng.shuffle(order)
        q["options"] = [q["options"][i] for i in order]
        q["answer_index"] = order.index(q["answer_index"])
        q["id"] = f"{topic_id}-llm-{uuid.uuid4().hex[:8]}"
        q["verified"] = bool(require_verification)
        out.append(q)
    return out


# --------------------------------------------------------------- public API
def generate_practice(topic_id, mastery, n=5, seen_ids=(), bank=None, topics_meta=None,
                      use_llm=True, seed=None, require_verification=True) -> dict:
    """Build a practice set adapted to the student's mastery on this topic."""
    try:
        from .analyzer import load_topics
    except ImportError:  # run as a plain script from inside ai_engine/
        from analyzer import load_topics
    bank = bank or get_bank()
    n = max(1, min(int(n), MAX_N))
    mastery = min(max(float(mastery), 0.0), 1.0)
    meta = (topics_meta or load_topics()).get(topic_id, {"name": topic_id, "subject": ""})
    rng = random.Random(seed)
    seen, chosen, note = set(seen_ids), [], None

    pool = {d: [q for q in bank.for_topic(topic_id) if q["difficulty"] == d and q["id"] not in seen]
            for d in DIFFS}
    for d in pool:
        rng.shuffle(pool[d])

    # 1) fill the target mix from unseen questions
    for diff, count in difficulty_mix(mastery, n).items():
        chosen += [pool[diff].pop() for _ in range(min(count, len(pool[diff])))]

    # 2) shortage -> try the LLM (validated + independently verified) for the missing amount
    if len(chosen) < n and use_llm and meta["name"] != topic_id:
        target = "easy" if mastery < 0.35 else "medium" if mastery < 0.6 else "hard"
        fresh = _llm_topup(topic_id, meta, target, n - len(chosen), bank, rng, require_verification)
        if fresh:
            bank.add_generated(fresh)
            chosen += fresh[: n - len(chosen)]

    # 3) still short -> any other unseen question, nearest difficulty first
    if len(chosen) < n:
        rest = [q for d in DIFFS for q in pool[d] if q not in chosen]
        chosen += rest[: n - len(chosen)]

    # 4) still short -> re-serve questions the student already saw
    if len(chosen) < n:
        repeats = [q for q in bank.for_topic(topic_id) if q not in chosen]
        rng.shuffle(repeats)
        chosen += repeats[: n - len(chosen)]
        if repeats:
            note = "Not enough new questions for this topic; some are repeats."
    if not chosen:
        note = "No questions available for this topic yet."
    elif len(chosen) < n:
        note = f"Only {len(chosen)} questions available for this topic (add more or enable LLM top-up)."

    order = {d: i for i, d in enumerate(DIFFS)}
    chosen.sort(key=lambda q: order[q["difficulty"]])  # warm-up first
    return {"topic_id": topic_id, "topic_name": meta["name"], "mastery_used": mastery,
            "questions": [_public(q) for q in chosen], "note": note}


def _valid_choice(c) -> bool:
    return isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 3


def grade_answer(question_id, chosen_index, bank=None) -> dict:
    """Grade one answer and return the explanation."""
    bank = bank or get_bank()
    q = bank.questions.get(question_id)
    if q is None:
        return {"error": f"unknown question id: {question_id}"}
    if not _valid_choice(chosen_index):
        return {"error": "chosen_index must be an integer from 0 to 3"}
    ok = chosen_index == q["answer_index"]
    return {"question_id": question_id, "correct": ok,
            "correct_index": q["answer_index"], "correct_answer": q["options"][q["answer_index"]],
            "explanation": q["explanation"]}


def grade_session(answers, bank=None, timestamp=None) -> dict:
    """answers: [{"question_id": ..., "chosen_index": int | None}, ...]
    Returns per-question feedback, the score, and `attempts` rows in the exact format
    analyzer.py expects, so the backend can store them and mastery updates automatically.
    Each question counts once (duplicates ignored); skipped or invalid answers are not
    counted as wrong."""
    bank = bank or get_bank()
    ts = (timestamp or datetime.now(timezone.utc)).isoformat()
    results, attempts, seen, unknown = [], [], set(), []
    for a in answers or []:
        if not isinstance(a, dict):
            continue
        qid = a.get("question_id")
        q = bank.questions.get(qid)
        if q is None:
            unknown.append(qid)
            continue
        if qid in seen:
            continue
        seen.add(qid)
        chosen = a.get("chosen_index")
        if not _valid_choice(chosen):  # None (skipped) or malformed: feedback only
            results.append({"question_id": qid, "skipped": True, "explanation": q["explanation"],
                            "correct_answer": q["options"][q["answer_index"]]})
            continue
        r = grade_answer(qid, chosen, bank)
        results.append(r)
        attempts.append({"topic_id": q["topic_id"], "correct": int(r["correct"]),
                         "difficulty": q["difficulty"], "timestamp": ts})
    return {"score": sum(1 for x in results if x.get("correct")), "answered": len(attempts),
            "total": len(results), "results": results, "attempts": attempts, "unknown_ids": unknown}


def level_quiz(topic_id, difficulty, bank=None, topics_meta=None, seed=None) -> dict:
    """The fixed quiz for one module level: every curated question of that difficulty for the
    topic, in random order. (generate_practice is the *adaptive* mix; this is the level quiz
    used by the module -> easy / medium / hard flow.) Answers are never included."""
    try:
        from .analyzer import load_topics
    except ImportError:
        from analyzer import load_topics
    if difficulty not in DIFFS:
        raise ValueError(f"difficulty must be one of {DIFFS}")
    bank = bank or get_bank()
    meta = (topics_meta or load_topics()).get(topic_id, {"name": topic_id, "subject": ""})
    qs = [q for q in bank.for_topic(topic_id) if q["difficulty"] == difficulty]
    random.Random(seed).shuffle(qs)
    return {"topic_id": topic_id, "topic_name": meta["name"], "difficulty": difficulty,
            "questions": [_public(q) for q in qs],
            "note": None if qs else "No questions available for this level yet."}
