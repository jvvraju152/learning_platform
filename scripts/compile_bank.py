# scripts/compile_bank.py
import json
import random
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.ai_engine.quiz_engine import validate_question
from scripts.data_ds import get_ds_questions
from scripts.data_ds_linked_lists import get_linked_lists_questions
from scripts.data_ds_stacks_queues import get_stacks_queues_questions
from scripts.data_ds_recursion import get_recursion_questions
from scripts.data_ds_trees import get_trees_questions
from scripts.data_ds_sorting import get_sorting_questions
from scripts.data_dbms_sql import get_sql_questions
from scripts.data_dbms_norm import get_norm_questions
from scripts.data_dbms_trans import get_trans_questions
from scripts.data_dbms_index import get_index_questions
from scripts.data_os_proc import get_proc_questions
from scripts.data_os_sched import get_sched_questions
from scripts.data_os_dead import get_dead_questions
from scripts.data_os_mem import get_mem_questions

def compile_bank():
    all_questions = []
    all_questions.extend(get_ds_questions())
    all_questions.extend(get_linked_lists_questions())
    all_questions.extend(get_stacks_queues_questions())
    all_questions.extend(get_recursion_questions())
    all_questions.extend(get_trees_questions())
    all_questions.extend(get_sorting_questions())
    all_questions.extend(get_sql_questions())
    all_questions.extend(get_norm_questions())
    all_questions.extend(get_trans_questions())
    all_questions.extend(get_index_questions())
    all_questions.extend(get_proc_questions())
    all_questions.extend(get_sched_questions())
    all_questions.extend(get_dead_questions())
    all_questions.extend(get_mem_questions())

    print(f"Total compiled questions: {len(all_questions)}")
    assert len(all_questions) == 630, f"Expected 630 questions, got {len(all_questions)}"

    # Distribute the correct answer position across options A, B, C, D (0, 1, 2, 3)
    # rather than having all correct answers remain at index 0 (Option A).
    # Group questions by (topic_id, difficulty) to ensure each quiz level has an even distribution.
    groups = {}
    for q in all_questions:
        key = (q["topic_id"], q["difficulty"])
        groups.setdefault(key, []).append(q)

    slot_pattern = [1, 2, 0, 3, 2, 1, 3, 0, 1, 3, 0, 2, 3, 0, 1]

    for g_idx, (key, q_list) in enumerate(sorted(groups.items())):
        for q_idx, q in enumerate(q_list):
            target_slot = (slot_pattern[q_idx % len(slot_pattern)] + g_idx) % 4
            correct_idx = q["answer_index"]
            correct_text = q["options"][correct_idx]
            distractors = [opt for i, opt in enumerate(q["options"]) if i != correct_idx]
            rng = random.Random(f"{q['id']}_distractors")
            rng.shuffle(distractors)

            new_options = [None] * 4
            new_options[target_slot] = correct_text
            d_i = 0
            for s in range(4):
                if s != target_slot:
                    new_options[s] = distractors[d_i]
                    d_i += 1

            q["options"] = new_options
            q["answer_index"] = target_slot

    # Validate each question
    seen_ids = set()
    topic_counts = {}
    answer_dist = {0: 0, 1: 0, 2: 0, 3: 0}

    for i, q in enumerate(all_questions):
        qid = q["id"]
        assert qid not in seen_ids, f"Duplicate ID found: {qid}"
        seen_ids.add(qid)

        valid = validate_question(q)
        if not valid:
            print(f"Validation FAILED for question {i}: {q}")
            assert False, f"Question validation failed for ID: {qid}"

        key = (q["topic_id"], q["difficulty"])
        topic_counts[key] = topic_counts.get(key, 0) + 1
        answer_dist[q["answer_index"]] += 1

    letters = {0: "A", 1: "B", 2: "C", 3: "D"}
    print(f"Answer key distribution across all questions: { {letters[k]: v for k, v in answer_dist.items()} }")

    for (t, d), count in sorted(topic_counts.items()):
        print(f"Topic '{t}' [{d}]: {count} questions")
        assert count == 15, f"Expected 15 questions for {t} [{d}], got {count}"

    output_path = ROOT_DIR / "app" / "ai_engine" / "data" / "question_bank.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_questions, f, indent=1, ensure_ascii=False)

    print(f"Successfully compiled and wrote 630 verified questions to {output_path}")

if __name__ == "__main__":
    compile_bank()
