"""Script to generate a comprehensive, highly rigorous, and advanced question bank
for all 14 topics across Data Structures, DBMS, and Operating Systems.
Contains 15 Easy, 15 Medium, and 15 Hard questions per topic = 45 questions * 14 topics = 630 questions.
All questions adhere to validate_question() rules and feature deep explanations.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "ai_engine" / "data"

def norm(text: str) -> str:
    return re.sub(r"\W+", " ", str(text).lower()).strip()

def validate_q(q: dict) -> bool:
    try:
        opts = q["options"]
        valid = (isinstance(q["question"], str) and len(q["question"].strip()) > 10
                 and isinstance(opts, list) and len(opts) == 4
                 and all(isinstance(o, str) and o.strip() for o in opts)
                 and len({norm(o) for o in opts}) == 4
                 and isinstance(q["answer_index"], int) and not isinstance(q["answer_index"], bool)
                 and 0 <= q["answer_index"] < 4
                 and isinstance(q["explanation"], str) and len(q["explanation"].strip()) > 10)
        return valid
    except (KeyError, TypeError):
        return False
