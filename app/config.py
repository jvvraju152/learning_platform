import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "learning.db"))
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
# Prefer the built shadcn/React app (web/ -> npm run build -> frontend_dist/); fall back to the plain HTML pages.
_BUILT = BASE_DIR / "frontend_dist"
FRONTEND_DIR = _BUILT if (_BUILT / "index.html").exists() else BASE_DIR / "frontend"

SESSION_DAYS = 30
COOKIE_NAME = "session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "").lower() in {"1", "true", "yes"}   # set when served over HTTPS

PASS_RATIO = 0.6            # a level is passed with at least 60% correct
MIN_PASSWORD = 6
PBKDF2_ITERATIONS = 200_000
LEVELS = ("easy", "medium", "hard")   # a level unlocks when the one before it is passed

# Minimum 10 and maximum 15 questions per topic and level
QUIZ_MIN = 10
QUIZ_MAX = 15
TIME_PER_QUESTION = 120   # 2 minutes (120 seconds) per question

# Base question count by difficulty level, before topic complexity scaling
LEVEL_BASE = {
    "easy": 10,
    "medium": 12,
    "hard": 14,
}

# Relative topic complexity weight: scales question counts between 10 and 15 per topic/module
TOPIC_COMPLEXITY = {
    # Data Structures
    "arrays": 1.0,           # easy: 10, med: 12, hard: 14
    "linked_lists": 1.05,    # easy: 10, med: 13, hard: 15
    "stacks_queues": 1.0,    # easy: 10, med: 12, hard: 14
    "recursion": 1.08,       # easy: 11, med: 13, hard: 15
    "trees": 1.10,           # easy: 11, med: 13, hard: 15
    "sorting": 1.05,         # easy: 10, med: 13, hard: 15
    # DBMS
    "sql": 1.0,              # easy: 10, med: 12, hard: 14
    "normalization": 1.08,   # easy: 11, med: 13, hard: 15
    "transactions": 1.10,    # easy: 11, med: 13, hard: 15
    "indexing": 1.05,        # easy: 10, med: 13, hard: 15
    # Operating Systems
    "processes": 1.0,        # easy: 10, med: 12, hard: 14
    "scheduling": 1.05,      # easy: 10, med: 13, hard: 15
    "deadlocks": 1.08,       # easy: 11, med: 13, hard: 15
    "memory": 1.10,          # easy: 11, med: 13, hard: 15
}

# Faculty endpoint /api/class/overview is disabled unless ADMIN_KEY is set (sent as X-Admin-Key).
ADMIN_KEY = os.getenv("ADMIN_KEY", "")

