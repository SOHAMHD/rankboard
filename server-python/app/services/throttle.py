"""In-process brute-force protection for authentication (login + 2FA).

The counters live in memory (module-level dicts guarded by a lock). This covers
the common single-worker deployment (uvicorn / Passenger). Across multiple
workers or after a restart the counters reset — a DB-backed store (a
`login_attempts` table + a `users.lockout_until` column) is the robust upgrade
and is recommended once the DB layer is restored — but an in-memory guard
already converts "unlimited guessing" into "a few tries, then a cooldown",
which is what closes the brute-force window.

Public API:
    login_retry_after(key)      -> seconds locked out (0 = allowed)
    login_failed(key)           -> record a failed login
    login_ok(key)               -> clear on success
    twofa_retry_after(user_id)  -> seconds locked out (0 = allowed)
    twofa_failed(user_id)       -> record a failed 2FA attempt
    twofa_ok(user_id)           -> clear on success
    code_replayed(user_id, code)-> True if this exact code was just used
    mark_code_consumed(user_id, code)
"""
import threading
import time

# ── Tunables ────────────────────────────────────────────────────────────────
LOGIN_MAX = 5          # failed logins (per IP+email) before lockout
LOGIN_WINDOW = 900     # failures older than this (s) don't count toward the cap
LOGIN_LOCK = 900       # lockout duration (s) once the cap is hit
TWOFA_MAX = 5          # failed 2FA guesses (per user) before lockout
TWOFA_LOCK = 900       # 2FA lockout duration (s)
REPLAY_TTL = 120       # remember a consumed TOTP code this long (s) — blocks replay
RESET_MAX = 5          # email-code REQUESTS (per key) in the window before cooldown
RESET_WINDOW = 3600    # rolling window (s) for counting code requests
RESET_LOCK = 3600      # cooldown (s) once the request cap is hit

_lock = threading.Lock()
_login: dict[str, list] = {}   # key -> [count, first_ts, locked_until]
_twofa: dict[int, list] = {}   # user_id -> [count, first_ts, locked_until]
_reset: dict[str, list] = {}   # key -> [count, first_ts, locked_until]
_consumed: dict[int, dict] = {}  # user_id -> {code: consumed_ts}


def _retry_after(store, key):
    rec = store.get(key)
    if rec and rec[2] > time.time():
        return int(rec[2] - time.time()) + 1
    return 0


def _record_failure(store, key, cap, window, lock_secs):
    now = time.time()
    rec = store.get(key)
    if not rec or now - rec[1] > window:
        rec = [0, now, 0.0]   # reset the sliding window
    rec[0] += 1
    if rec[0] >= cap:
        rec[2] = now + lock_secs
    store[key] = rec


def login_retry_after(key: str) -> int:
    with _lock:
        return _retry_after(_login, key)


def login_failed(key: str) -> None:
    with _lock:
        _record_failure(_login, key, LOGIN_MAX, LOGIN_WINDOW, LOGIN_LOCK)


def login_ok(key: str) -> None:
    with _lock:
        _login.pop(key, None)


def twofa_retry_after(user_id: int) -> int:
    with _lock:
        return _retry_after(_twofa, user_id)


def twofa_failed(user_id: int) -> None:
    with _lock:
        _record_failure(_twofa, user_id, TWOFA_MAX, TWOFA_LOCK, TWOFA_LOCK)


def twofa_ok(user_id: int) -> None:
    with _lock:
        _twofa.pop(user_id, None)
        _consumed.pop(user_id, None)


def reset_retry_after(key: str) -> int:
    """Seconds until another password-reset / change-password code may be
    requested for this key (0 = allowed). Caps both email-bombing and the
    'guess 5 → re-request a fresh code → guess 5 more' unbounded-guessing loop."""
    with _lock:
        return _retry_after(_reset, key)


def reset_requested(key: str) -> None:
    with _lock:
        _record_failure(_reset, key, RESET_MAX, RESET_WINDOW, RESET_LOCK)


def code_replayed(user_id: int, code: str) -> bool:
    now = time.time()
    with _lock:
        seen = _consumed.get(user_id, {})
        # prune expired entries so the dict can't grow unbounded
        seen = {c: ts for c, ts in seen.items() if now - ts < REPLAY_TTL}
        _consumed[user_id] = seen
        return (code or "").strip() in seen


def mark_code_consumed(user_id: int, code: str) -> None:
    with _lock:
        _consumed.setdefault(user_id, {})[(code or "").strip()] = time.time()
