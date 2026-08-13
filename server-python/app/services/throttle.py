"""Login, 2FA and reset rate limiting, held in Postgres.

This was a set of module-level dicts, which made every limit per-process:

* Two uvicorn workers turned "5 login attempts per 15 minutes" into 10, and the
  2FA lockout into 10 tries — the limit silently scaled with worker count.
* A restart cleared every counter, including an active brute-force lockout. The
  one moment you least want the limiter reset is the moment someone is hammering
  it and you restart to see what's going on.
* Nothing was shared, so a lockout applied on one worker was invisible to the
  next request if it landed on another.

The counters now live in `throttle_counters`, so the limits are the limits.

The public API is unchanged on purpose — callers in routers/auth.py pass no
connection, so each function takes a short-lived one itself. That is a round trip
per login attempt, which is the correct price for a limit that actually holds; a
successful login already does more work than this.
"""

import time

from ..db import db_session

LOGIN_MAX = 5
LOGIN_WINDOW = 900
LOGIN_LOCK = 900
TWOFA_MAX = 5
TWOFA_LOCK = 900
REPLAY_TTL = 120
RESET_MAX = 5
RESET_WINDOW = 3600
RESET_LOCK = 3600

#: Rows older than this are pruned opportunistically. Long enough to cover the
#: widest window and lock above, with room to spare.
_KEEP_SECONDS = max(LOGIN_WINDOW + LOGIN_LOCK, RESET_WINDOW + RESET_LOCK) + 3600

_SCOPE_LOGIN = "login"
_SCOPE_TWOFA = "twofa"
_SCOPE_RESET = "reset"
_SCOPE_REPLAY = "replay"


def _retry_after(scope: str, key: str) -> int:
    now = time.time()
    with db_session() as db:
        row = db.execute(
            "SELECT locked_until FROM throttle_counters WHERE scope = ? AND key = ?",
            (scope, str(key)),
        ).fetchone()
    if row is None or not row["locked_until"]:
        return 0
    remaining = float(row["locked_until"]) - now
    return int(remaining) + 1 if remaining > 0 else 0


def _record_failure(scope: str, key: str, cap: int, window: int, lock_secs: int) -> None:
    """Count one failure, and start a lockout once the cap is reached.

    Written as a single upsert so two simultaneous failures can't each read the
    same count and write it back — with in-memory dicts that race was harmless,
    but the whole point of moving here is that concurrent workers share state.
    """
    now = time.time()
    with db_session() as db:
        db.execute(
            """INSERT INTO throttle_counters (scope, key, attempts, window_start, locked_until)
               VALUES (?, ?, 1, ?, NULL)
               ON CONFLICT (scope, key) DO UPDATE SET
                 -- A failure outside the window starts a fresh count rather than
                 -- accumulating forever.
                 attempts = CASE
                     WHEN ? - throttle_counters.window_start > ? THEN 1
                     ELSE throttle_counters.attempts + 1 END,
                 window_start = CASE
                     WHEN ? - throttle_counters.window_start > ? THEN ?
                     ELSE throttle_counters.window_start END,
                 locked_until = CASE
                     WHEN (CASE
                             WHEN ? - throttle_counters.window_start > ? THEN 1
                             ELSE throttle_counters.attempts + 1 END) >= ?
                     THEN ? + ?
                     ELSE throttle_counters.locked_until END""",
            (scope, str(key), now,
             now, window,
             now, window, now,
             now, window, cap,
             now, lock_secs),
        )
        _prune(db, now)


def _clear(scope: str, key: str) -> None:
    with db_session() as db:
        db.execute(
            "DELETE FROM throttle_counters WHERE scope = ? AND key = ?", (scope, str(key))
        )


def _prune(db, now: float) -> None:
    """Drop rows nothing can consult any more.

    Opportunistic rather than scheduled: this table only grows on failed attempts,
    so tying the cleanup to a failure keeps it proportional and needs no cron.
    """
    db.execute(
        "DELETE FROM throttle_counters WHERE window_start < ?"
        "  AND (locked_until IS NULL OR locked_until < ?)",
        (now - _KEEP_SECONDS, now),
    )


# ── login ─────────────────────────────────────────────────────────────

def login_retry_after(key: str) -> int:
    return _retry_after(_SCOPE_LOGIN, key)


def login_failed(key: str) -> None:
    _record_failure(_SCOPE_LOGIN, key, LOGIN_MAX, LOGIN_WINDOW, LOGIN_LOCK)


def login_ok(key: str) -> None:
    _clear(_SCOPE_LOGIN, key)


# ── TOTP / backup codes ───────────────────────────────────────────────

def twofa_retry_after(user_id: int) -> int:
    return _retry_after(_SCOPE_TWOFA, user_id)


def twofa_failed(user_id: int) -> None:
    _record_failure(_SCOPE_TWOFA, user_id, TWOFA_MAX, TWOFA_LOCK, TWOFA_LOCK)


def twofa_ok(user_id: int) -> None:
    _clear(_SCOPE_TWOFA, user_id)
    with db_session() as db:
        db.execute(
            "DELETE FROM throttle_counters WHERE scope = ? AND key LIKE ?",
            (_SCOPE_REPLAY, f"{int(user_id)}:%"),
        )


# ── password reset requests ───────────────────────────────────────────

def reset_retry_after(key: str) -> int:
    return _retry_after(_SCOPE_RESET, key)


def reset_requested(key: str) -> None:
    _record_failure(_SCOPE_RESET, key, RESET_MAX, RESET_WINDOW, RESET_LOCK)


# ── one-time-code replay protection ───────────────────────────────────

def code_replayed(user_id: int, code: str) -> bool:
    """Has this exact code already been accepted for this user recently?

    A TOTP code stays valid for its whole time step, so without this a code
    observed once could be replayed within the same window.
    """
    now = time.time()
    key = f"{int(user_id)}:{(code or '').strip()}"
    with db_session() as db:
        row = db.execute(
            "SELECT locked_until FROM throttle_counters WHERE scope = ? AND key = ?",
            (_SCOPE_REPLAY, key),
        ).fetchone()
    return bool(row and row["locked_until"] and float(row["locked_until"]) > now)


def mark_code_consumed(user_id: int, code: str) -> None:
    now = time.time()
    key = f"{int(user_id)}:{(code or '').strip()}"
    with db_session() as db:
        db.execute(
            """INSERT INTO throttle_counters (scope, key, attempts, window_start, locked_until)
               VALUES (?, ?, 1, ?, ?)
               ON CONFLICT (scope, key) DO UPDATE
                 SET window_start = ?, locked_until = ?""",
            (_SCOPE_REPLAY, key, now, now + REPLAY_TTL, now, now + REPLAY_TTL),
        )
