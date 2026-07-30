"""IN-PROCESS TTL CACHE for slow third-party provider reads (GA4 / GSC / Moz).

WHY THIS EXISTS
    A GA4 dashboard load fans out to ~9 runReport calls; a Search Console query
    takes 10-20s (the provider's own comments say so). None of that was cached,
    so every tab switch, every back-and-forth, and every report regeneration paid
    the full latency AGAIN for data that changes at most once a day.

WHAT IT IS
    A dict guarded by a lock, keyed on the function name plus its arguments. Not
    Redis, not memcached — deliberately. The counters in throttle.py already
    establish this pattern for a single-worker uvicorn deployment, and a cache
    that resets on restart is exactly the right trade-off here: worst case a
    request is slow once more.

    Across multiple workers each holds its own copy. That's harmless (they just
    miss independently), but it does mean the effective hit rate falls as workers
    are added. A shared store is the upgrade if that ever matters.

FRESHNESS — the trade-off to understand
    Cached values can be up to TTL seconds stale. GA4 and Search Console data is
    itself hours-to-days behind real time (GSC's API even excludes the most
    recent incomplete days), so a 15-minute window adds nothing meaningful to a
    number that is already yesterday's. Tune with PROVIDER_CACHE_TTL, or set it
    to 0 to disable caching entirely without touching code.

ERRORS ARE CACHED TOO, BUT BRIEFLY
    A failing provider is usually failing for everyone — a bad property id, a
    revoked credential, a quota wall. Re-asking on every keystroke makes quota
    exhaustion worse, so failures are held for ERROR_TTL (short) rather than the
    full TTL. Long enough to stop a stampede, short enough that a fix shows up
    quickly.
"""
import functools
import json
import os
import threading
import time

# Successful responses live this long (seconds). 15 minutes by default.
TTL = int(os.environ.get("PROVIDER_CACHE_TTL", "900"))
# Failures are held much more briefly, so a fixed credential recovers fast.
ERROR_TTL = int(os.environ.get("PROVIDER_CACHE_ERROR_TTL", "30"))
# Hard ceiling on entries so a pathological number of distinct filter
# combinations can't grow this without bound. Oldest entries are evicted first.
MAX_ENTRIES = int(os.environ.get("PROVIDER_CACHE_MAX", "512"))

_lock = threading.Lock()
_store: dict[str, tuple[float, object]] = {}  # key -> (expires_at, value)


def _key(name: str, args: tuple, kwargs: dict) -> str:
    """A stable key from the call signature. json with sort_keys makes
    kwargs order irrelevant; default=str keeps it from blowing up on a value that
    isn't JSON-native (it only needs to be consistent, not reversible)."""
    try:
        blob = json.dumps([args, kwargs], sort_keys=True, default=str)
    except Exception:
        blob = repr((args, kwargs))
    return f"{name}|{blob}"


def _looks_like_error(value) -> bool:
    """The providers signal failure by RETURNING {"error": "..."} rather than
    raising, so a plain "did it raise?" check would treat those as successes and
    cache them for the full TTL."""
    return isinstance(value, dict) and value.get("error")


def _prune(now: float) -> None:
    """Drop expired entries; if still over the cap, evict nearest-to-expiry
    first. Called under _lock."""
    for k in [k for k, (exp, _) in _store.items() if exp <= now]:
        _store.pop(k, None)
    if len(_store) > MAX_ENTRIES:
        for k, _ in sorted(_store.items(), key=lambda kv: kv[1][0])[: len(_store) - MAX_ENTRIES]:
            _store.pop(k, None)


def cached(name: str):
    """Decorator: memoise a provider call for TTL seconds.

    Pass refresh=True at the call site to force a miss and refill the entry —
    that's how a "Refresh" button bypasses the cache without disabling it.
    """
    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, refresh: bool = False, **kwargs):
            if TTL <= 0:  # caching switched off via env — straight through
                return fn(*args, **kwargs)

            k = _key(name, args, kwargs)
            now = time.time()

            if not refresh:
                with _lock:
                    hit = _store.get(k)
                    if hit and hit[0] > now:
                        return hit[1]

            # Computed OUTSIDE the lock: these calls take seconds, and holding the
            # lock across them would serialise every unrelated request behind one
            # slow GA4 round trip. Two concurrent misses on the same key both do
            # the work; that's a deliberately accepted duplicate rather than the
            # much worse alternative of a global stall.
            value = fn(*args, **kwargs)

            with _lock:
                _prune(now)
                _store[k] = (now + (ERROR_TTL if _looks_like_error(value) else TTL), value)
            return value

        return wrapper
    return decorate


def clear() -> None:
    """Drop everything. For tests, and for an admin-triggered cache flush."""
    with _lock:
        _store.clear()


def stats() -> dict:
    """Cheap introspection — entry count and the configured windows."""
    with _lock:
        now = time.time()
        live = sum(1 for exp, _ in _store.values() if exp > now)
        return {"entries": len(_store), "live": live, "ttl": TTL, "errorTtl": ERROR_TTL}
