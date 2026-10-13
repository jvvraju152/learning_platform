# Personalized Learning Platform

One app: the AI engine (mastery, weak topics, adaptive practice, study plans) + the backend
(accounts, database) + a plain HTML frontend.

## Run it

```
python -m venv .venv
.venv\Scripts\activate            (Windows)      source .venv/bin/activate   (macOS/Linux)
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000 . The same server serves the pages and the API.

Want something to look at straight away? `python scripts/build_sqlite.py --demo --force` adds
`demo@example.com` / `demo1234` with a few weeks of quiz history (weak in Trees and Recursion).
Without `--demo` the database starts empty (that is how it ships).

## New frontend (React + shadcn/ui)

The modern UI lives in `web/` (Vite, React, TypeScript, Tailwind, shadcn/ui components in `web/src/components/ui`).
Build it once and the Python server serves it automatically (it falls back to the old plain `frontend/` if not built):

```
cd web
npm install
npm run build          # writes ../frontend_dist
cd ..
uvicorn app.main:app --reload
```

For live editing run `uvicorn app.main:app --reload` in one terminal and `npm run dev` in `web/` in another
(Vite proxies `/api` to port 8000; open http://localhost:5173). Add more shadcn components with `npx shadcn@latest add <name>`.

## What the student sees

1. **index.html** - "Please enter your name".
2. **signup.html** - create the account (email + password). **login.html** for returning students.
3. **subjects.html** - choose what to learn: Data Structures, DBMS, Operating Systems.
4. **modules.html** - the subject's modules, each with Easy / Medium / Hard quizzes.
   Passing a level (60% or more) unlocks the next one. Click a module for **module.html**: study
   resources matched to the student's level, the three quizzes, and an adaptive practice set.
5. **quiz.html** - answer, submit, see the score, the right answers and explanations.
6. **dashboard.html** (My Progress) - mastery per subject and topic, weak topics, what to study
   (resources), and a day-by-day study plan. Every answered question feeds this.

## How the pieces fit

| Part | Where | Notes |
|---|---|---|
| AI engine | `app/ai_engine/` | Your original code, plus one added function, `level_quiz()`, for the fixed Easy/Medium/Hard quizzes. Content lives in `app/ai_engine/data/*.json`. |
| API | `app/main.py` | JSON under `/api/...`; everything except register/login needs the login cookie. |
| Database | `learning.db`, schema in `db/schema.sql` | students, sessions, student_subjects, quiz_results (one per quiz), attempts (one per answered question, in exactly the shape `analyze_student()` expects). |
| Glue | `app/services/progress.py` | Level locking, module view, attempts -> engine. |
| Frontend | `frontend/` | Plain HTML + one CSS + one small JS file. No build step, no framework. |

Endpoints: `POST /api/register|login|logout`, `GET /api/me`, `GET /api/subjects`, `POST /api/me/subjects`,
`GET /api/modules?subject=`, `GET /api/modules/{topic}`, `POST /api/quiz/start`, `POST /api/quiz/submit`,
`GET /api/me/analysis|recommendations|plan`, `GET /api/class/overview` (needs `ADMIN_KEY`).

## Changes from the two original zips

- **Stack:** the original backend used FastAPI + SQLAlchemy. This version uses Starlette (which FastAPI
  is built on) + the standard library's `sqlite3`: two dependencies, and it could be run and tested end
  to end where it was built.
- **Database:** rebuilt. The old `scores` table (hand-entered percentages, sample students with
  Trees/Graphs/Subnetting) and `resources` table (example.com placeholders) are gone. Results now come
  from answered questions, and resources come from the engine's `resource_bank.json` (real links).
  The old template-based question generator and score-based analytics are replaced by the engine's.
- **Accounts:** new. Passwords are PBKDF2-hashed, sessions are random tokens in an HttpOnly cookie, and
  login attempts are throttled (5 failures per 10 minutes).

## Adding content (Java, DAA, ...)

Add topics to `app/ai_engine/data/topics.json` (with `subject` and `prerequisites`), questions to
`question_bank.json` (4 options, `answer_index`, `explanation`, difficulty easy/medium/hard) and links to
`resource_bank.json`. A new subject appears on the Subjects page automatically. Restart the server.

## Known limits

- **Quizzes are short**: each module has 2 easy, 3 medium and 3 hard questions, so a level is 2-3
  questions (easy needs 2 of 2 to pass) and a retake repeats the same questions. More questions per
  topic is the biggest improvement to make.
- 14 of the 71 resource links are YouTube *search* links (shown as "search results"). No link was opened
  from the build environment, so spot-check them.
- Mastery is rule-based and explainable, not a trained model.
- No password reset or email verification. No teacher login: `/api/class/overview` is only a key-protected endpoint.
- Modules show their prerequisites but are not locked by them (only levels inside a module are locked).

## Tests

`python tests/test_api.py` runs the whole flow on a throwaway database (older Starlette needs `httpx` installed).
