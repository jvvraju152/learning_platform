"""Create (or rebuild) learning.db.

  python scripts/build_sqlite.py --force          # empty database with the schema (what ships)
  python scripts/build_sqlite.py --demo --force   # also adds demo@example.com / demo1234 with quiz history
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import auth                      # noqa: E402
from app.ai_engine.quiz_engine import get_bank   # noqa: E402
from app.config import DB_PATH            # noqa: E402
from app.db import connect, init_db       # noqa: E402

# (topic, level, ratio_correct) per day offset: a student strong in arrays, weak in trees and recursion.
DEMO = [(20, "arrays", "easy", 1.0), (19, "arrays", "medium", 0.9), (18, "arrays", "hard", 0.85),
        (14, "linked_lists", "easy", 0.8), (13, "linked_lists", "medium", 0.7),
        (9, "recursion", "easy", 0.4), (8, "recursion", "easy", 0.3), (5, "trees", "easy", 0.1), (2, "trees", "easy", 0.2),
        (1, "sql", "easy", 0.9), (1, "sql", "medium", 0.8)]


def add_demo():
    conn = connect()
    cur = conn.execute("INSERT INTO students(name, email, password_hash, created_at) VALUES (?,?,?,?)",
                       ("Demo Student", "demo@example.com", auth.hash_password("demo1234"),
                        datetime.now(timezone.utc).replace(microsecond=0).isoformat()))
    sid, bank = cur.lastrowid, get_bank()
    conn.execute("INSERT INTO student_subjects VALUES (?,?,?)", (sid, "Data Structures", "2026-01-01T00:00:00+00:00"))
    for days_ago, topic, level, ratio in DEMO:
        ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(microsecond=0).isoformat()
        qs = [q for q in bank.for_topic(topic) if q["difficulty"] == level]
        total = len(qs)
        right = round(total * ratio)
        need = -(-total * 6 // 10)
        r = conn.execute("INSERT INTO quiz_results(student_id, topic_id, difficulty, score, total, passed, taken_at) "
                         "VALUES (?,?,?,?,?,?,?)", (sid, topic, level, right, total, int(right >= need), ts))
        for i, q in enumerate(qs):
            ok = i < right
            chosen = q["answer_index"] if ok else (q["answer_index"] + 1) % 4
            conn.execute("INSERT INTO attempts(student_id, quiz_result_id, question_id, topic_id, difficulty, "
                         "chosen_index, correct, timestamp) VALUES (?,?,?,?,?,?,?,?)",
                         (sid, r.lastrowid, q["id"], topic, level, chosen, int(ok), ts))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="delete an existing database first")
    ap.add_argument("--demo", action="store_true", help="add a demo account with quiz history")
    args = ap.parse_args()
    if DB_PATH.exists():
        if not args.force:
            sys.exit(f"{DB_PATH} exists. Use --force to rebuild it.")
        for suffix in ("", "-wal", "-shm"):
            Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
    init_db()
    if args.demo:
        add_demo()
    print(f"Created {DB_PATH}" + (" with demo account demo@example.com / demo1234" if args.demo else " (empty)"))
