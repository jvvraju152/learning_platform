# ai_engine (Member 2: AI and Personalization)

Pure Python, standard library only. Run `python demo.py` to see everything work and
run the edge-case checks.

## Integration contract (share this with Members 1 and 3)

| Function | Called by endpoint | Input | Output |
|---|---|---|---|
| `analyze_student(attempts)` | `GET /students/{id}/analysis` | list of attempt rows | mastery per topic, `weak_topics`, `subject_mastery`, `data_quality` |
| `recommend_for_student(analysis)` | `GET /students/{id}/recommendations` | the analysis dict | resources per weak topic |
| `build_study_plan(analysis, days, minutes_per_day)` | `GET /students/{id}/plan` | the analysis dict | day-by-day plan |
| `generate_practice(topic_id, mastery, n, seen_ids)` | `POST /students/{id}/practice` | topic + mastery | questions (answers hidden) |
| `grade_session(answers)` | `POST /attempts` | `[{question_id, chosen_index}]` | score, explanations, `attempts` rows to store |
| `class_overview({sid: attempts})` | `GET /class/overview` | all students' attempts | topic stats, at-risk students |

**Attempt row (what Member 1's DB query must produce):**
`{"topic_id": "trees", "correct": 1, "difficulty": "hard", "timestamp": "2026-10-01T10:30:00"}`
`difficulty` and `timestamp` are optional. `topic_id` may be an id or a topic name. `correct` must be 0/1 or
true/false; blank/NaN/other values are DROPPED (never counted as wrong) and reported in `data_quality`.
Topic ids live in `data/topics.json`.

## Methods
- **Mastery:** recency-weighted, difficulty-weighted accuracy with Bayesian shrinkage toward 0.5.
- **Status:** `insufficient_data` (<3 attempts), `stale` (no attempt in 90 days: re-test, don't label),
  `weak` (<0.50), `developing` (<0.75), `strong`.
- **Priority:** low mastery x confidence x number of dependent topics, boosted for prerequisites
  that are blocking other weak topics (root cause) and for declining trends.
- **Questions:** difficulty mix adapts to mastery; curated bank first (112 questions, correct answers
  balanced across A-D). Optional LLM top-up (set `ANTHROPIC_API_KEY`): validated, de-duplicated, then
  independently re-solved by the model without seeing the key; kept only if it agrees. If the check fails,
  the questions are discarded.
- **Known limits:** MCQ guessing is not modelled; difficulty labels are author-assigned (calibrate from
  real attempt data later); LLM path was tested with mocks, not a live API call.

## To do before the demo
1. **Spot-check the links** in `data/resource_bank.json` (Wikipedia, VisuAlgo, OSTEP, PostgreSQL docs,
   LeetCode, HackerRank, SQLBolt, Microsoft Learn). They are well-known stable pages but were not opened
   from the build environment. The per-topic "YouTube (search)" entries are search links
   (`link_type: "search"`); replace them with a specific NPTEL/YouTube lecture your team likes.
2. Add more questions if you want longer sessions (8 per topic now; `generate_practice` tells you when short).
3. Add your own subjects: extend `topics.json` (with prerequisites) plus the two banks.
4. Run `python demo.py` after any change; it must end with "All checks passed."
