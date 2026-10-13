"""Personalized Learning Platform: one app serving the JSON API (/api/...) and the plain HTML frontend.

Run:  uvicorn app.main:app --reload      then open http://127.0.0.1:8000
"""
import json
import random
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import auth
from .ai_engine import (build_study_plan, class_overview, generate_practice, grade_session,
                        recommend_for_student)
from .ai_engine.quiz_engine import get_bank
from .ai_engine.recommendations import recommend_resources
from .config import (ADMIN_KEY, COOKIE_NAME, COOKIE_SECURE, FRONTEND_DIR, LEVELS, QUIZ_MAX, SESSION_DAYS,
                     TIME_PER_QUESTION)
from .db import init_db, now_iso, session
from .services import progress

# A submission may arrive slightly after the deadline (network + client clock drift). Anything later than
# deadline + GRACE is rejected; anything inside the grace window is graded and flagged as timed out.
GRACE_SECONDS = 15
QUIZ_SESSION_KEEP_DAYS = 2

QUIZ_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS quiz_sessions (
    id           TEXT PRIMARY KEY,
    student_id   INTEGER NOT NULL,
    topic_id     TEXT NOT NULL,
    difficulty   TEXT NOT NULL,
    question_ids TEXT NOT NULL,      -- JSON list of the question ids served, in the order served
    started_at   TEXT NOT NULL,
    deadline_at  TEXT,               -- NULL for practice (untimed)
    submitted_at TEXT,
    result_id    INTEGER,
    paused_at    TEXT
)"""


# ------------------------------------------------------------------ plumbing
class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status, self.detail = status, detail


class Ctx:
    """What a handler gets: an open DB connection, the logged-in student, the JSON body, the query."""

    def __init__(self, request, db, user, data):
        self.request, self.db, self.user, self.data = request, db, user, data
        self.query = request.query_params
        self.new_token = None       # set by login/register
        self.clear_cookie = False   # set by logout

    def field(self, name, default=None):
        return (self.data or {}).get(name, default)


def endpoint(auth_required=True, body=False, status=200):
    """Wrap a plain function(ctx) -> dict into a Starlette handler (JSON in, JSON out)."""
    def deco(fn):
        async def handler(request):
            data = None
            if body:
                try:
                    data = await request.json()
                except Exception:
                    return JSONResponse({"detail": "Request body must be valid JSON."}, status_code=400)
                if not isinstance(data, dict):
                    return JSONResponse({"detail": "Request body must be a JSON object."}, status_code=400)

            def work():
                with session() as db:
                    user = auth.student_for_token(db, request.cookies.get(COOKIE_NAME))
                    if auth_required and user is None:
                        raise ApiError(401, "Please log in.")
                    ctx = Ctx(request, db, user, data)
                    return fn(ctx), ctx

            try:
                result, ctx = await run_in_threadpool(work)
            except ApiError as e:
                return JSONResponse({"detail": e.detail}, status_code=e.status)
            resp = JSONResponse(result, status_code=status)
            if ctx.new_token:
                resp.set_cookie(COOKIE_NAME, ctx.new_token, max_age=SESSION_DAYS * 86400, httponly=True,
                                samesite="lax", secure=COOKIE_SECURE, path="/")
            if ctx.clear_cookie:
                resp.delete_cookie(COOKIE_NAME, path="/")
            resp.headers["Cache-Control"] = "no-store"
            return resp
        return handler
    return deco


def user_json(c: Ctx) -> dict:
    subs = [r["subject"] for r in c.db.execute(
        "SELECT subject FROM student_subjects WHERE student_id=? ORDER BY added_at, subject", (c.user["id"],))]
    return {"id": c.user["id"], "name": c.user["name"], "email": c.user["email"], "subjects": subs}


# ------------------------------------------------------------------ accounts
@endpoint(auth_required=False, body=True, status=201)
def register(c: Ctx):
    name, email, pw = c.field("name"), c.field("email"), c.field("password")
    problem = auth.validate_registration(name, email, pw)
    if problem:
        raise ApiError(422, problem)
    try:
        cur = c.db.execute("INSERT INTO students(name, email, password_hash, created_at) VALUES (?,?,?,?)",
                           (auth.clean_name(name), auth.clean_email(email), auth.hash_password(pw), now_iso()))
    except sqlite3.IntegrityError:
        raise ApiError(409, "An account with this email already exists. Try logging in.")
    c.new_token = auth.create_session(c.db, cur.lastrowid)
    c.user = {"id": cur.lastrowid, "name": auth.clean_name(name), "email": auth.clean_email(email)}
    return user_json(c)


@endpoint(auth_required=False, body=True)
def login(c: Ctx):
    email, pw = auth.clean_email(c.field("email")), c.field("password")
    key = (c.request.client.host if c.request.client else "?", email)
    if auth.login_blocked(key):
        raise ApiError(429, "Too many failed attempts. Please wait a few minutes and try again.")
    row = c.db.execute("SELECT * FROM students WHERE email=?", (email,)).fetchone()
    if not row or not isinstance(pw, str) or not auth.verify_password(pw, row["password_hash"]):
        auth.note_failed_login(key)
        raise ApiError(401, "Wrong email or password.")
    auth.clear_failed_logins(key)
    c.new_token = auth.create_session(c.db, row["id"])
    c.user = {"id": row["id"], "name": row["name"], "email": row["email"]}
    return user_json(c)


@endpoint(auth_required=False)
def logout(c: Ctx):
    auth.delete_session(c.db, c.request.cookies.get(COOKIE_NAME))
    c.clear_cookie = True
    return {"ok": True}


@endpoint(auth_required=False)
def me(c: Ctx):
    """Used by every page to find out whether someone is logged in (200 with null when not)."""
    return {"user": user_json(c) if c.user else None}


# ------------------------------------------------------------------ subjects & modules
@endpoint()
def subjects(c: Ctx):
    summary = progress.results_summary(c.db, c.user["id"])
    chosen = set(user_json(c)["subjects"])
    out = []
    for s in progress.subject_names():
        mods = [progress.levels_for(t, summary) for t in progress.module_ids(s)]
        out.append({"subject": s, "modules": len(mods), "selected": s in chosen,
                    "levels_total": sum(len(m) for m in mods),
                    "levels_passed": sum(l["passed"] for m in mods for l in m)})
    return {"subjects": out}


@endpoint(body=True)
def choose_subject(c: Ctx):
    subject = c.field("subject")
    if subject not in progress.subject_names():
        raise ApiError(404, "Unknown subject.")
    c.db.execute("INSERT OR IGNORE INTO student_subjects(student_id, subject, added_at) VALUES (?,?,?)",
                 (c.user["id"], subject, now_iso()))
    return user_json(c)


@endpoint()
def modules(c: Ctx):
    subject = c.query.get("subject", "")
    if subject not in progress.subject_names():
        raise ApiError(404, "Unknown subject.")
    summary = progress.results_summary(c.db, c.user["id"])
    a = {t["topic_id"]: t for t in progress.analysis_for(c.db, c.user["id"])["topics"]}
    return {"subject": subject, "modules": [progress.module_view(t, summary, a) for t in progress.module_ids(subject)]}


@endpoint()
def module_detail(c: Ctx):
    topic_id = c.request.path_params["topic_id"]
    if topic_id not in progress.topics():
        raise ApiError(404, "Unknown module.")
    summary = progress.results_summary(c.db, c.user["id"])
    analysis = progress.analysis_for(c.db, c.user["id"])
    view = progress.module_view(topic_id, summary, {t["topic_id"]: t for t in analysis["topics"]})
    mastery = view["mastery"] if view["mastery"] is not None else 0.5   # no data yet: middle level
    view["resources"] = recommend_resources(topic_id, mastery, progress.resources(), k=4)
    return view


# ------------------------------------------------------------------ quizzes
# Every quiz a student takes is a *session*: the server picks the questions, stores their ids, and later
# grades the submission against exactly that stored set. The client never decides what the quiz contains.
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _require_unlocked(c: Ctx, topic_id, difficulty):
    summary = progress.results_summary(c.db, c.user["id"])
    for lv in progress.levels_for(topic_id, summary):
        if lv["difficulty"] == difficulty:
            if not lv["unlocked"]:
                raise ApiError(403, "This level is locked. Pass the previous level first.")
            return
    raise ApiError(404, "This module has no questions at that level yet.")


def _pick_level_questions(c: Ctx, topic_id: str, difficulty: str) -> list:
    """Choose this attempt's questions: quiz_size() of them, preferring ones the student has seen least,
    then preserve pedagogical progression (rank order 1..15) so questions start from core foundations
    and progressively advance deeper into complex challenges."""
    pool = [q for q in get_bank().for_topic(topic_id) if q["difficulty"] == difficulty]
    seen = {r["question_id"]: r["n"] for r in c.db.execute(
        "SELECT question_id, COUNT(*) AS n FROM attempts WHERE student_id=? AND topic_id=? AND difficulty=? "
        "GROUP BY question_id", (c.user["id"], topic_id, difficulty))}
    # Sort primarily by least seen, then by curated difficulty index
    def _rank(q):
        # Extract question number e.g. 'arrays_e1' -> 1
        num_match = re.search(r"\d+", q["id"])
        return int(num_match.group()) if num_match else 0
    pool.sort(key=lambda q: (seen.get(q["id"], 0), _rank(q)))
    chosen = pool[:progress.quiz_size(topic_id, difficulty)]
    # Order the served attempt in smooth ascending pedagogical depth
    chosen.sort(key=_rank)
    return [q["id"] for q in chosen]


def _served_ids(payload: dict, topic_id: str) -> list:
    """Question ids inside a payload built by the engine (used for adaptive practice)."""
    bank, ids = get_bank(), []
    for q in payload.get("questions", []):
        qid = (q.get("id") or q.get("question_id")) if isinstance(q, dict) else None
        if qid in bank.questions and bank.questions[qid]["topic_id"] == topic_id and qid not in ids:
            ids.append(qid)
    if not ids:
        raise ApiError(500, "Could not build this quiz. Please try again.")
    return ids


def _public_questions(ids: list) -> list:
    """What the student may see: the question and its options, never anything that reveals the answer."""
    bank = get_bank()
    out = []
    for qid in ids:
        q = bank.questions[qid]
        out.append({
            "id": qid,
            "topic_id": q["topic_id"],
            "difficulty": q["difficulty"],
            "question": q["question"],
            "options": q["options"],
            "source": q.get("source", "curated"),
        })
    return out


def _open_session(c: Ctx, topic_id: str, difficulty: str, ids: list, now: datetime, deadline) -> str:
    sid = secrets.token_urlsafe(16)
    c.db.execute("INSERT INTO quiz_sessions(id, student_id, topic_id, difficulty, question_ids, started_at, deadline_at) "
                 "VALUES (?,?,?,?,?,?,?)",
                 (sid, c.user["id"], topic_id, difficulty, json.dumps(ids), now.isoformat(),
                  deadline.isoformat() if deadline else None))
    return sid


@endpoint(body=True)
def quiz_start(c: Ctx):
    topic_id, difficulty = c.field("topic_id"), c.field("difficulty")
    if topic_id not in progress.topics():
        raise ApiError(404, "Unknown module.")
    now = _now()
    c.db.execute("DELETE FROM quiz_sessions WHERE started_at < ?",
                 ((now - timedelta(days=QUIZ_SESSION_KEEP_DAYS)).isoformat(),))

    if difficulty == "practice":
        a = {t["topic_id"]: t for t in progress.analysis_for(c.db, c.user["id"])["topics"]}
        n = c.field("n", 5)
        n = n if isinstance(n, int) and not isinstance(n, bool) else 5
        n = max(1, min(n, QUIZ_MAX))
        payload = generate_practice(topic_id, a[topic_id]["mastery"] if topic_id in a else 0.5, n=n)
        ids = _served_ids(payload, topic_id)
        sid = _open_session(c, topic_id, "practice", ids, now, None)
        return payload | {"difficulty": "practice", "session_id": sid, "total": len(ids)}

    if difficulty not in LEVELS:
        raise ApiError(422, "difficulty must be easy, medium, hard or practice.")
    _require_unlocked(c, topic_id, difficulty)

    # Resume an unfinished attempt instead of re-rolling: a refresh must not reshuffle the questions or reset the clock.
    row = c.db.execute("SELECT * FROM quiz_sessions WHERE student_id=? AND topic_id=? AND difficulty=? "
                       "AND submitted_at IS NULL ORDER BY started_at DESC LIMIT 1",
                       (c.user["id"], topic_id, difficulty)).fetchone()
    paused_seconds_left = None
    is_paused = False
    if row:
        row_deadline = datetime.fromisoformat(row["deadline_at"]) if row["deadline_at"] else None
        if row["paused_at"]:
            paused_at = datetime.fromisoformat(row["paused_at"])
            remaining = max(0, int((row_deadline - paused_at).total_seconds())) if row_deadline else None
            sid, ids, deadline, resumed = row["id"], json.loads(row["question_ids"]), row_deadline, True
            paused_seconds_left = remaining
            is_paused = True
        elif row_deadline and row_deadline > now:
            sid, ids, deadline, resumed = row["id"], json.loads(row["question_ids"]), row_deadline, True
        else:
            ids = _pick_level_questions(c, topic_id, difficulty)
            deadline = now + timedelta(seconds=TIME_PER_QUESTION * len(ids))
            sid, resumed = _open_session(c, topic_id, difficulty, ids, now, deadline), False
    else:
        ids = _pick_level_questions(c, topic_id, difficulty)
        deadline = now + timedelta(seconds=TIME_PER_QUESTION * len(ids))
        sid, resumed = _open_session(c, topic_id, difficulty, ids, now, deadline), False

    n = len(ids)
    sec_left = paused_seconds_left if is_paused else (max(0, int((deadline - now).total_seconds())) if deadline else None)
    return {"session_id": sid, "topic_id": topic_id, "difficulty": difficulty, "resumed": resumed,
            "total": n, "pass_mark": progress.pass_mark(n),
            "time_limit_seconds": TIME_PER_QUESTION * n,
            "seconds_left": sec_left,
            "is_paused": is_paused,
            "expires_at": deadline.isoformat() if deadline else None,
            "questions": _public_questions(ids)}


@endpoint(body=True)
def quiz_pause(c: Ctx):
    sid = c.field("session_id")
    if not sid:
        raise ApiError(422, "session_id is required.")
    sess = c.db.execute("SELECT * FROM quiz_sessions WHERE id=? AND student_id=?", (sid, c.user["id"])).fetchone()
    if sess is None:
        raise ApiError(404, "Quiz session not found.")
    if sess["submitted_at"] is not None:
        raise ApiError(409, "Quiz has already been submitted.")
    if sess["deadline_at"] is None:
        return {"status": "paused", "session_id": sid, "seconds_left": None}
    
    now = _now()
    if sess["paused_at"]:
        # Already paused
        p_at = datetime.fromisoformat(sess["paused_at"])
        d_at = datetime.fromisoformat(sess["deadline_at"])
        rem = max(0, int((d_at - p_at).total_seconds()))
        return {"status": "paused", "session_id": sid, "seconds_left": rem}

    deadline = datetime.fromisoformat(sess["deadline_at"])
    if now > deadline + timedelta(seconds=GRACE_SECONDS):
        raise ApiError(410, "Time ran out before pausing.")

    remaining = max(0, int((deadline - now).total_seconds()))
    c.db.execute("UPDATE quiz_sessions SET paused_at=? WHERE id=?", (now.isoformat(), sid))
    return {"status": "paused", "session_id": sid, "seconds_left": remaining}


@endpoint(body=True)
def quiz_resume(c: Ctx):
    sid = c.field("session_id")
    if not sid:
        raise ApiError(422, "session_id is required.")
    sess = c.db.execute("SELECT * FROM quiz_sessions WHERE id=? AND student_id=?", (sid, c.user["id"])).fetchone()
    if sess is None:
        raise ApiError(404, "Quiz session not found.")
    if sess["submitted_at"] is not None:
        raise ApiError(409, "Quiz has already been submitted.")
    if sess["deadline_at"] is None:
        return {"status": "resumed", "session_id": sid, "seconds_left": None}

    now = _now()
    if not sess["paused_at"]:
        # Not paused, calculate current seconds left
        deadline = datetime.fromisoformat(sess["deadline_at"])
        remaining = max(0, int((deadline - now).total_seconds()))
        return {"status": "resumed", "session_id": sid, "seconds_left": remaining, "deadline_at": deadline.isoformat()}

    paused_at = datetime.fromisoformat(sess["paused_at"])
    old_deadline = datetime.fromisoformat(sess["deadline_at"])
    remaining_secs = max(0, int((old_deadline - paused_at).total_seconds()))
    new_deadline = now + timedelta(seconds=remaining_secs)

    c.db.execute("UPDATE quiz_sessions SET paused_at=NULL, deadline_at=? WHERE id=?",
                 (new_deadline.isoformat(), sid))
    return {"status": "resumed", "session_id": sid, "seconds_left": remaining_secs, "deadline_at": new_deadline.isoformat()}


@endpoint(body=True)
def quiz_submit(c: Ctx):
    """Grade a submission against the question set that was served to this attempt.

    Rules (the same for every level quiz and for practice):
      * the session must exist, belong to this student and not be submitted already;
      * every answered question id must be in the served set, at most once, with a valid option index;
      * the served set is the denominator: total = questions served, skipped questions count as wrong;
      * pass mark and `passed` come from that total (progress.grade_attempt), never from the whole bank;
      * answers (and only answers) become `attempts` rows, so skipped or timed-out questions do not drag mastery down;
      * a timed quiz may be submitted until deadline + GRACE_SECONDS; later submissions are rejected and not recorded;
        a submission after the deadline but inside the grace window is graded normally and flagged timed_out.
    """
    sid, answers = c.field("session_id"), c.field("answers")
    req_topic, req_diff = c.field("topic_id"), c.field("difficulty")

    if req_topic and req_diff and req_diff in LEVELS:
        _require_unlocked(c, req_topic, req_diff)

    if not isinstance(sid, str) or not sid:
        if req_topic and req_diff:
            row = c.db.execute("SELECT * FROM quiz_sessions WHERE student_id=? AND topic_id=? AND difficulty=? "
                               "AND submitted_at IS NULL ORDER BY started_at DESC LIMIT 1",
                               (c.user["id"], req_topic, req_diff)).fetchone()
            if row:
                sid = row["id"]
        if not sid:
            raise ApiError(422, "session_id is required. Start the quiz again.")
    if not isinstance(answers, list):
        raise ApiError(422, "Send a list of answers (it may be empty if you ran out of time).")

    sess = c.db.execute("SELECT * FROM quiz_sessions WHERE id=? AND student_id=?", (sid, c.user["id"])).fetchone()
    if sess is None:
        raise ApiError(404, "Quiz not found. Start the quiz again.")
    if sess["submitted_at"] is not None:
        raise ApiError(409, "This quiz was already submitted.")

    topic_id, difficulty = sess["topic_id"], sess["difficulty"]
    if difficulty in LEVELS:
        _require_unlocked(c, topic_id, difficulty)
    for field, actual in (("topic_id", topic_id), ("difficulty", difficulty)):
        if c.field(field) not in (None, actual):
            raise ApiError(422, f"{field} does not match this quiz.")

    now = _now()
    timed_out = bool(c.field("timed_out")) is True
    if sess["deadline_at"] is not None:
        deadline = datetime.fromisoformat(sess["deadline_at"])
        if sess["paused_at"]:
            # If paused at submit time, calculate effective deadline
            paused_at = datetime.fromisoformat(sess["paused_at"])
            remaining = max(0, int((deadline - paused_at).total_seconds()))
            deadline = now + timedelta(seconds=remaining)
        if now > deadline + timedelta(seconds=GRACE_SECONDS):
            raise ApiError(410, "Time ran out before this quiz was submitted. Start a new attempt.")
        timed_out = timed_out or now > deadline

    bank = get_bank()
    asked = json.loads(sess["question_ids"])            # exactly what was served, in the order served
    if len(answers) > len(asked):
        raise ApiError(422, "More answers than questions in this quiz.")
    served = set(asked)
    given = {}                                          # question_id -> chosen_index (None = skipped)
    for a in answers:
        qid = a.get("question_id") if isinstance(a, dict) else None
        if not isinstance(qid, (str, int)) or isinstance(qid, bool) or qid not in served:
            raise ApiError(422, "Answers contain a question that was not part of this quiz.")
        if qid in given:
            raise ApiError(422, "Each question can only be answered once.")
        idx = a.get("chosen_index")
        if idx is not None and (isinstance(idx, bool) or not isinstance(idx, int)
                                or not 0 <= idx < len(bank.questions[qid]["options"])):
            raise ApiError(422, "chosen_index is not a valid option for that question.")
        given[qid] = idx

    # Claim the session first (atomic) so a double submit or a retry cannot be graded twice.
    claimed = c.db.execute("UPDATE quiz_sessions SET submitted_at=?, paused_at=NULL WHERE id=? AND student_id=? AND submitted_at IS NULL",
                           (now.isoformat(), sid, c.user["id"]))
    if claimed.rowcount != 1:
        raise ApiError(409, "This quiz was already submitted.")

    total = len(asked)
    graded = grade_session([{"question_id": qid, "chosen_index": given.get(qid)} for qid in asked])
    grade = progress.grade_attempt(graded["score"], total)
    score = grade["score"]
    is_level = difficulty != "practice"
    passed = is_level and grade["passed"]
    ts = now_iso()
    qmap = {r["question_id"]: r for r in graded["results"]}

    cur = c.db.execute("INSERT INTO quiz_results(student_id, topic_id, difficulty, score, total, passed, taken_at) "
                       "VALUES (?,?,?,?,?,?,?)", (c.user["id"], topic_id, difficulty, score, total, int(passed), ts))
    c.db.execute("UPDATE quiz_sessions SET result_id=? WHERE id=?", (cur.lastrowid, sid))
    answered = [qid for qid in asked if given.get(qid) is not None and "correct" in qmap.get(qid, {})]
    c.db.executemany(
        "INSERT INTO attempts(student_id, quiz_result_id, question_id, topic_id, difficulty, chosen_index, correct, timestamp) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(c.user["id"], cur.lastrowid, qid, topic_id, bank.questions[qid]["difficulty"], given[qid],
          int(qmap[qid]["correct"]), ts) for qid in answered])

    summary = progress.results_summary(c.db, c.user["id"])
    levels = progress.levels_for(topic_id, summary)
    next_level = None
    if passed:
        idx = [l["difficulty"] for l in levels].index(difficulty)
        if idx + 1 < len(levels):
            next_level = levels[idx + 1]["difficulty"]
    return {"topic_id": topic_id, "difficulty": difficulty, "score": score, "total": total,
            "pass_mark": grade["pass_mark"] if is_level else None,
            "passed": passed, "next_level": next_level, "levels": levels,
            "answered": len(answered), "unanswered": total - len(answered), "timed_out": timed_out,
            "results": [{"question_id": qid, "question": bank.questions[qid]["question"],
                         "options": bank.questions[qid]["options"], "chosen_index": given.get(qid), **qmap[qid]}
                        for qid in asked if qid in qmap]}


# ------------------------------------------------------------------ progress, recommendations, plan
@endpoint()
def my_analysis(c: Ctx):
    return progress.analysis_for(c.db, c.user["id"]) | {
        "topic_names": {t: m["name"] for t, m in progress.topics().items()}}


@endpoint()
def my_recommendations(c: Ctx):
    return {"recommendations": recommend_for_student(progress.analysis_for(c.db, c.user["id"]), progress.resources())}


@endpoint()
def my_plan(c: Ctx):
    def num(name, default, lo, hi):
        try:
            return min(max(int(c.query.get(name, default)), lo), hi)
        except ValueError:
            return default
    return build_study_plan(progress.analysis_for(c.db, c.user["id"]), days=num("days", 7, 2, 30),
                            minutes_per_day=num("minutes", 60, 20, 480), resources=progress.resources())


@endpoint(auth_required=False)
def class_view(c: Ctx):
    key = c.request.headers.get("x-admin-key", "")
    if not ADMIN_KEY or key != ADMIN_KEY:
        raise ApiError(404, "Not found.")
    by = {}
    for r in c.db.execute("SELECT student_id, topic_id, correct, difficulty, timestamp FROM attempts ORDER BY id"):
        by.setdefault(r["student_id"], []).append(dict(r))
    return class_overview(by)


# ------------------------------------------------------------------ app
async def not_found(request):
    return JSONResponse({"detail": "Not found."}, status_code=404)


@asynccontextmanager
async def lifespan(app):
    init_db()
    with session() as db:                 # move into db.init_db() if you prefer all DDL in one place
        db.execute(QUIZ_SESSIONS_DDL)
        # Ensure paused_at column exists if table was previously created without it
        try:
            db.execute("ALTER TABLE quiz_sessions ADD COLUMN paused_at TEXT")
        except sqlite3.OperationalError:
            pass
    yield


routes = [
    Route("/api/register", register, methods=["POST"]),
    Route("/api/login", login, methods=["POST"]),
    Route("/api/logout", logout, methods=["POST"]),
    Route("/api/me", me, methods=["GET"]),
    Route("/api/subjects", subjects, methods=["GET"]),
    Route("/api/me/subjects", choose_subject, methods=["POST"]),
    Route("/api/modules", modules, methods=["GET"]),
    Route("/api/modules/{topic_id}", module_detail, methods=["GET"]),
    Route("/api/quiz/start", quiz_start, methods=["POST"]),
    Route("/api/quiz/pause", quiz_pause, methods=["POST"]),
    Route("/api/quiz/resume", quiz_resume, methods=["POST"]),
    Route("/api/quiz/submit", quiz_submit, methods=["POST"]),
    Route("/api/me/analysis", my_analysis, methods=["GET"]),
    Route("/api/me/recommendations", my_recommendations, methods=["GET"]),
    Route("/api/me/plan", my_plan, methods=["GET"]),
    Route("/api/class/overview", class_view, methods=["GET"]),
    Route("/api/{rest:path}", not_found),
    Mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend"),
]
app = Starlette(routes=routes, lifespan=lifespan)
