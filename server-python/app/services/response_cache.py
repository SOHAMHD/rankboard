import copy
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


#: Keys currently being computed, so concurrent callers can wait instead of
#: duplicating the work. Each value is an Event the leader sets on completion.
_inflight: dict[str, threading.Event] = {}

#: How long a follower waits for the leader before giving up and calling `fn`
#: itself. A ceiling rather than a policy: without it a leader that hangs would
#: block every follower indefinitely.
FOLLOWER_TIMEOUT = 60


def cached(name: str):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, refresh: bool = False, **kwargs):
            if TTL <= 0:
                return fn(*args, **kwargs)

            k = _key(name, args, kwargs)

            while True:
                now = time.time()

                if not refresh:
                    with _lock:
                        hit = _store.get(k)
                        if hit and hit[0] > now:
                            # A copy, not the stored object. Providers return
                            # nested dicts and callers edit them in place — the
                            # analytics summary picks up returningUsers after the
                            # fact, for one — so handing out the cached value by
                            # reference let one request's edits show up in every
                            # later cache hit for the same key.
                            return copy.deepcopy(hit[1])

                        # Somebody else is already computing this key. Wait for
                        # them rather than issuing the same GA4/GSC report run —
                        # opening one project screen fires ~6 endpoints, so a cold
                        # cache used to send several identical requests against the
                        # same quota at once, and it was worst exactly when the TTL
                        # expired.
                        waiting = _inflight.get(k)
                        if waiting is not None:
                            leader = None
                        else:
                            leader = _inflight[k] = threading.Event()

                    if leader is None:
                        if waiting.wait(timeout=FOLLOWER_TIMEOUT):
                            # Leader finished — loop round and read the cache. If
                            # it failed and stored nothing, we become the leader.
                            continue
                        # Leader is taking too long; fall through and do it
                        # ourselves rather than block forever.
                        return fn(*args, **kwargs)
                else:
                    with _lock:
                        leader = _inflight.get(k) or threading.Event()
                        _inflight[k] = leader

                try:
                    value = fn(*args, **kwargs)
                    with _lock:
                        _prune(now)
                        _store[k] = (
                            now + (ERROR_TTL if _looks_like_error(value) else TTL),
                            value,
                        )
                    return value
                finally:
                    # Always release the followers, success or not — a leader that
                    # raised must not leave them waiting out the full timeout.
                    with _lock:
                        _inflight.pop(k, None)
                    leader.set()

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
