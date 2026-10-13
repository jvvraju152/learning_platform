"""Accounts and sessions: PBKDF2 password hashing, random session tokens in an HttpOnly cookie.
Only a SHA-256 of the token is stored, so a copy of the database cannot be used to log in."""
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from .config import MIN_PASSWORD, PBKDF2_ITERATIONS, SESSION_DAYS
from .db import now_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str, iterations: int = PBKDF2_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(check.hex(), digest)
    except (ValueError, TypeError):
        return False


def clean_name(value) -> str:
    return " ".join(str(value or "").split())


def clean_email(value) -> str:
    return str(value or "").strip().lower()


def validate_registration(name, email, password):
    """Returns an error message, or None when fine."""
    if not (1 <= len(clean_name(name)) <= 60):
        return "Please enter your name (up to 60 characters)."
    if not EMAIL_RE.match(clean_email(email)) or len(clean_email(email)) > 255:
        return "Please enter a valid email address."
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password) > 200:
        return "Password is too long."
    return None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db, student_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat()
    db.execute("INSERT INTO sessions(token_hash, student_id, created_at, expires_at) VALUES (?,?,?,?)",
               (_hash_token(token), student_id, now_iso(), expires))
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (now_iso(),))   # housekeeping
    return token


def student_for_token(db, token):
    if not token:
        return None
    return db.execute(
        "SELECT s.id, s.name, s.email FROM sessions x JOIN students s ON s.id = x.student_id "
        "WHERE x.token_hash = ? AND x.expires_at > ?", (_hash_token(token), now_iso())).fetchone()


def delete_session(db, token) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


# --- brute-force guard: 5 failed logins per (client, email) per 10 minutes (in memory, per process)
_FAILS: dict = {}
_WINDOW, _MAX_FAILS = 600, 5


def login_blocked(key) -> bool:
    now = time.time()
    recent = [t for t in _FAILS.get(key, []) if now - t < _WINDOW]
    _FAILS[key] = recent
    return len(recent) >= _MAX_FAILS


def note_failed_login(key) -> None:
    _FAILS.setdefault(key, []).append(time.time())


def clear_failed_logins(key) -> None:
    _FAILS.pop(key, None)
