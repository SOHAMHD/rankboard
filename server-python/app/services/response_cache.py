import functools
import json
import os
import threading
import time

TTL = int(os.environ.get("PROVIDER_CACHE_TTL", "900"))
ERROR_TTL = int(os.environ.get("PROVIDER_CACHE_ERROR_TTL", "30"))
MAX_ENTRIES = int(os.environ.get("PROVIDER_CACHE_MAX", "512"))

_lock = threading.Lock()
_store: dict[str, tuple[float, object]] = {}


def _key(name: str, args: tuple, kwargs: dict) -> str:
    try:
        blob = json.dumps([args, kwargs], sort_keys=True, default=str)
    except Exception:
        blob = repr((args, kwargs))
    return f"{name}|{blob}"


def _looks_like_error(value) -> bool:
    return isinstance(value, dict) and value.get("error")


#: How often the expiry sweep may run, in seconds. _prune used to walk the whole
#: store — and sort it — on every single cache write.
_PRUNE_INTERVAL = 60
_last_prune = 0.0


def _prune(now: float, force: bool = False) -> None:
    global _last_prune
    over_capacity = len(_store) > MAX_ENTRIES
    if not force and not over_capacity and now - _last_prune < _PRUNE_INTERVAL:
        return
    _last_prune = now
    for k in [k for k, (exp, _) in _store.items() if exp <= now]:
        _store.pop(k, None)
    if len(_store) > MAX_ENTRIES:
        for k, _ in sorted(_store.items(), key=lambda kv: kv[1][0])[: len(_store) - MAX_ENTRIES]:
            _store.pop(k, None)


def cached(name: str):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, refresh: bool = False, **kwargs):
            if TTL <= 0:
                return fn(*args, **kwargs)

            k = _key(name, args, kwargs)
            now = time.time()

            if not refresh:
                with _lock:
                    hit = _store.get(k)
                    if hit and hit[0] > now:
                        return hit[1]

            value = fn(*args, **kwargs)

            with _lock:
                _prune(now)
                _store[k] = (now + (ERROR_TTL if _looks_like_error(value) else TTL), value)
            return value

        return wrapper
    return decorate


def clear() -> None:
    with _lock:
        _store.clear()


def stats() -> dict:
    with _lock:
        now = time.time()
        live = sum(1 for exp, _ in _store.values() if exp > now)
        return {"entries": len(_store), "live": live, "ttl": TTL, "errorTtl": ERROR_TTL}
