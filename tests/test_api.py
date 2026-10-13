"""End-to-end API tests on a throwaway database.  Run:  python tests/test_api.py   (pytest also works)"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")
os.environ["ADMIN_KEY"] = "secret-admin"

from starlette.testclient import TestClient  # noqa: E402

from app.ai_engine.quiz_engine import get_bank  # noqa: E402
from app.main import app  # noqa: E402
from app.services import progress  # noqa: E402


def answer_key(topic, level):
    return {q["id"]: q["answer_index"] for q in get_bank().for_topic(topic) if q["difficulty"] == level}


def take(client, topic, level, correct=True):
    qz = client.post("/api/quiz/start", json={"topic_id": topic, "difficulty": level})
    assert qz.status_code == 200, qz.text
    key = answer_key(topic, level)
    ans = [{"question_id": q["id"], "chosen_index": key[q["id"]] if correct else (key[q["id"]] + 1) % 4}
           for q in qz.json()["questions"]]
    return qz.json(), client.post("/api/quiz/submit", json={"topic_id": topic, "difficulty": level, "answers": ans})


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/api/me").json() == {"user": None}
        assert c.get("/api/subjects").status_code == 401          # must log in
        assert c.get("/").status_code == 200                       # frontend served

        # --- account
        bad = c.post("/api/register", json={"name": "Asha", "email": "nope", "password": "abcdef"})
        assert bad.status_code == 422
        assert c.post("/api/register", json={"name": "Asha", "email": "asha@x.com", "password": "123"}).status_code == 422
        r = c.post("/api/register", json={"name": "  Asha   K ", "email": "Asha@X.com", "password": "secret1"})
        assert r.status_code == 201 and r.json()["name"] == "Asha K"
        assert "HttpOnly" in r.headers["set-cookie"]
        assert c.post("/api/register", json={"name": "B", "email": "asha@x.com", "password": "secret1"}).status_code == 409
        assert c.get("/api/me").json()["user"]["email"] == "asha@x.com"

        # --- subjects and modules
        subs = c.get("/api/subjects").json()["subjects"]
        assert [s["subject"] for s in subs] == ["Data Structures", "DBMS", "Operating Systems"]
        assert c.post("/api/me/subjects", json={"subject": "Nonsense"}).status_code == 404
        assert c.post("/api/me/subjects", json={"subject": "Data Structures"}).json()["subjects"] == ["Data Structures"]
        mods = c.get("/api/modules", params={"subject": "Data Structures"}).json()["modules"]
        assert len(mods) == 6 and mods[0]["topic_id"] == "arrays"
        lv = {l["difficulty"]: l for l in mods[0]["levels"]}
        assert lv["easy"]["unlocked"] and not lv["medium"]["unlocked"] and not lv["hard"]["unlocked"]
        assert lv["easy"]["pass_mark"] == progress.pass_mark(lv["easy"]["questions"]) and lv["medium"]["pass_mark"] == progress.pass_mark(lv["medium"]["questions"])

        # --- locked levels cannot be started or submitted
        assert c.post("/api/quiz/start", json={"topic_id": "arrays", "difficulty": "medium"}).status_code == 403
        assert c.post("/api/quiz/submit", json={"topic_id": "arrays", "difficulty": "medium", "answers": [
            {"question_id": next(iter(answer_key("arrays", "medium"))), "chosen_index": 0}]}).status_code == 403

        # --- the quiz never leaks answers
        quiz, res = take(c, "arrays", "easy", correct=False)
        assert all(set(q) == {"id", "topic_id", "difficulty", "question", "options", "source"} for q in quiz["questions"])
        res = res.json()
        assert res["score"] == 0 and not res["passed"] and res["next_level"] is None
        assert c.post("/api/quiz/start", json={"topic_id": "arrays", "difficulty": "medium"}).status_code == 403  # still locked

        # --- pass easy -> medium unlocks -> pass medium -> hard unlocks
        _, res = take(c, "arrays", "easy")
        res = res.json()
        assert res["passed"] and res["score"] == res["total"] and res["next_level"] == "medium"
        _, res = take(c, "arrays", "medium")
        assert res.json()["passed"] and res.json()["next_level"] == "hard"
        _, res = take(c, "arrays", "hard")
        assert res.json()["passed"] and res.json()["next_level"] is None
        mod = c.get("/api/modules/arrays").json()
        assert mod["completed"] and mod["levels_passed"] == 3 and len(mod["resources"]) > 0

        # --- cheating guards: questions from another topic / level are rejected
        other = next(iter(answer_key("trees", "easy")))
        bad = c.post("/api/quiz/submit", json={"topic_id": "arrays", "difficulty": "easy",
                                               "answers": [{"question_id": other, "chosen_index": 0}]})
        assert bad.status_code == 422

        # --- a weak topic shows up in analysis, recommendations and the plan
        for _ in range(2):
            take(c, "linked_lists", "easy", correct=False)
        a = c.get("/api/me/analysis").json()
        topics = {t["topic_id"]: t for t in a["topics"]}
        assert topics["linked_lists"]["status"] == "weak" and topics["arrays"]["status"] in ("developing", "strong")
        assert a["topic_names"]["linked_lists"] == "Linked Lists" and "trees" in a["untested_topics"]
        rec = c.get("/api/me/recommendations").json()["recommendations"]
        assert rec and rec[0]["topic_id"] == "linked_lists" and rec[0]["resources"]
        plan = c.get("/api/me/plan", params={"days": 5, "minutes": 45}).json()
        assert plan["days"] and plan["days"][-1]["topic_name"] == "Checkpoint"

        # --- adaptive practice: stored as attempts, but does not touch level progress
        before = {l["difficulty"]: l["tries"] for l in c.get("/api/modules/trees").json()["levels"]}
        pq = c.post("/api/quiz/start", json={"topic_id": "trees", "difficulty": "practice", "n": 4}).json()
        assert len(pq["questions"]) == 4
        pr = c.post("/api/quiz/submit", json={"topic_id": "trees", "difficulty": "practice", "answers": [
            {"question_id": q["id"], "chosen_index": 0} for q in pq["questions"]]}).json()
        assert pr["total"] == 4 and pr["pass_mark"] is None and not pr["passed"]
        assert {l["difficulty"]: l["tries"] for l in c.get("/api/modules/trees").json()["levels"]} == before

        # --- pause and resume session test
        p_sess = c.post("/api/quiz/start", json={"topic_id": "normalization", "difficulty": "easy"}).json()
        sid = p_sess["session_id"]
        p_res = c.post("/api/quiz/pause", json={"session_id": sid}).json()
        assert p_res["status"] == "paused" and p_res["seconds_left"] is not None
        # Check re-fetch quiz_start sees is_paused
        p_check = c.post("/api/quiz/start", json={"topic_id": "normalization", "difficulty": "easy"}).json()
        assert p_check["is_paused"] is True
        r_res = c.post("/api/quiz/resume", json={"session_id": sid}).json()
        assert r_res["status"] == "resumed" and r_res["seconds_left"] is not None

        # --- unanswered questions count as wrong for the level score but are not stored as attempts
        qz = c.post("/api/quiz/start", json={"topic_id": "sql", "difficulty": "easy"}).json()
        key = answer_key("sql", "easy")
        first = qz["questions"][0]["id"]
        r = c.post("/api/quiz/submit", json={"topic_id": "sql", "difficulty": "easy",
                                             "answers": [{"question_id": first, "chosen_index": key[first]}]}).json()
        assert r["score"] == 1 and r["total"] == len(qz["questions"]) and not r["passed"]
        assert any(x.get("skipped") for x in r["results"])
        n = c.get("/api/me/analysis").json()["data_quality"]["rows_used"]
        assert n > 0

        # --- faculty endpoint needs the admin key
        assert c.get("/api/class/overview").status_code == 404
        assert "topics" in c.get("/api/class/overview", headers={"x-admin-key": "secret-admin"}).json()

        # --- logout, then log back in
        c.post("/api/logout", json={})
        assert c.get("/api/me").json() == {"user": None}
        assert c.post("/api/login", json={"email": "asha@x.com", "password": "wrong"}).status_code == 401
        assert c.post("/api/login", json={"email": "ASHA@x.com", "password": "secret1"}).status_code == 200
        assert c.get("/api/modules/arrays").json()["completed"]          # progress persisted


def test_progress_is_per_student_and_login_is_throttled():
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/register", json={"name": "A", "email": "a@x.com", "password": "secret1"})
        b.post("/api/register", json={"name": "B", "email": "b@x.com", "password": "secret1"})
        take(a, "recursion", "easy")
        assert any(l["tries"] for l in a.get("/api/modules/recursion").json()["levels"])
        assert not any(l["tries"] for l in b.get("/api/modules/recursion").json()["levels"])
        codes = [b.post("/api/login", json={"email": "b@x.com", "password": "bad"}).status_code for _ in range(7)]
        assert codes[:5] == [401] * 5 and codes[5:] == [429, 429]


def test_bad_input():
    with TestClient(app) as c:
        assert c.post("/api/login", content="not json", headers={"content-type": "application/json"}).status_code == 400
        assert c.post("/api/login", json=[1]).status_code == 400
        assert c.get("/api/nothing").status_code == 404


if __name__ == "__main__":      # works with or without pytest
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok  ", name)
    print("All tests passed.")
