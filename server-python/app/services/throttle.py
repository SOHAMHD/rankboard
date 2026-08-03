import threading
import time

LOGIN_MAX = 5
LOGIN_WINDOW = 900
LOGIN_LOCK = 900
TWOFA_MAX = 5
TWOFA_LOCK = 900
REPLAY_TTL = 120
RESET_MAX = 5
RESET_WINDOW = 3600
RESET_LOCK = 3600

_lock = threading.Lock()
_login: dict[str, list] = {}
_twofa: dict[int, list] = {}
_reset: dict[str, list] = {}
_consumed: dict[int, dict] = {}


def _retry_after(store, key):
    rec = store.get(key)
    if rec and rec[2] > time.time():
        return int(rec[2] - time.time()) + 1
    return 0


def _record_failure(store, key, cap, window, lock_secs):
    now = time.time()
    rec = store.get(key)
    if not rec or now - rec[1] > window:
        rec = [0, now, 0.0]
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
    with _lock:
        return _retry_after(_reset, key)


def reset_requested(key: str) -> None:
    with _lock:
        _record_failure(_reset, key, RESET_MAX, RESET_WINDOW, RESET_LOCK)


def code_replayed(user_id: int, code: str) -> bool:
    now = time.time()
    with _lock:
        seen = _consumed.get(user_id, {})
        seen = {c: ts for c, ts in seen.items() if now - ts < REPLAY_TTL}
        _consumed[user_id] = seen
        return (code or "").strip() in seen


def mark_code_consumed(user_id: int, code: str) -> None:
    with _lock:
        _consumed.setdefault(user_id, {})[(code or "").strip()] = time.time()
