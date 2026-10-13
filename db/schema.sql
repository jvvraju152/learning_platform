-- SQLite schema for the learning platform. app/db.py runs this file on startup
-- (every statement is CREATE ... IF NOT EXISTS, so it is safe to run repeatedly).
-- Questions, topics and resources are NOT stored here: they live in app/ai_engine/data/*.json
-- (that is where the AI engine reads them). The database holds the people and what they did.

CREATE TABLE IF NOT EXISTS students (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,          -- stored lower-case
    password_hash TEXT NOT NULL,                 -- pbkdf2_sha256$iterations$salt$hash
    created_at    TEXT NOT NULL                  -- ISO-8601 UTC
);

-- Login sessions. Only a SHA-256 of the cookie token is stored.
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sessions_student ON sessions(student_id);

-- The subjects (Data Structures, DBMS, ...) a student chose to study.
CREATE TABLE IF NOT EXISTS student_subjects (
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    subject    TEXT NOT NULL,
    added_at   TEXT NOT NULL,
    PRIMARY KEY (student_id, subject)
);

-- One row per finished quiz. difficulty is easy | medium | hard (a level quiz) or practice (adaptive).
CREATE TABLE IF NOT EXISTS quiz_results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    topic_id   TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard','practice')),
    score      INTEGER NOT NULL CHECK (score >= 0),
    total      INTEGER NOT NULL CHECK (total > 0),
    passed     INTEGER NOT NULL DEFAULT 0 CHECK (passed IN (0,1)),
    taken_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_results_student_topic ON quiz_results(student_id, topic_id, difficulty);

-- One row per answered question. These rows are exactly what ai_engine.analyze_student() consumes.
CREATE TABLE IF NOT EXISTS attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    quiz_result_id INTEGER NOT NULL REFERENCES quiz_results(id) ON DELETE CASCADE,
    question_id    TEXT NOT NULL,
    topic_id       TEXT NOT NULL,
    difficulty     TEXT NOT NULL CHECK (difficulty IN ('easy','medium','hard')),
    chosen_index   INTEGER NOT NULL CHECK (chosen_index BETWEEN 0 AND 3),
    correct        INTEGER NOT NULL CHECK (correct IN (0,1)),
    timestamp      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts_student ON attempts(student_id, topic_id);
