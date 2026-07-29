"""RANK PROVIDER — the swappable-transport pattern, third appearance.

check_ranks() answers one question per keyword: "what position does
this project's domain hold on Google right now?" — via one of two
transports:

  DATAFORSEO_LOGIN/PASSWORD set  -> real lookups via DataForSEO's
                                    SERP API (Live mode: one POST,
                                    results in seconds)
  not set                        -> simulated random walk around the
                                    current rank, clearly labeled, so
                                    the feature is demoable for free

Callers (and the UI) only know "a lookup happened and here are the
numbers + the source". Swapping providers later (SerpApi, Search
Console) touches only this file.
"""
import base64
import concurrent.futures
import json
import logging
import random
import sys
import urllib.request

from ..config import (
    DATAFORSEO_BASE,
    DATAFORSEO_LOGIN,
    DATAFORSEO_PASSWORD,
    RANK_CHECK_DEPTH,
    RANK_LANGUAGE,
    RANK_LOCATION_CODE,
)

# ── Observability ────────────────────────────────────────────────────
# uvicorn does NOT configure the root logger, so INFO from a custom logger
# is invisible by default. Give this module its own stdout handler (Render
# captures stdout) so the rank-check trace below always shows up.
log = logging.getLogger("rankboard.rank_provider")
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def check_ranks(domain: str | None, keywords: list[dict], location_code: int | None = None) -> tuple[dict, str]:
    """keywords: [{"term": str, "currentRank": int|None}, ...]
    location_code: the project's DataForSEO country code, or None to fall
    back to the global RANK_LOCATION_CODE default.
    Returns ({term: rank | None}, source). None = not found in the
    checked depth."""
    if DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD:
        code = location_code if location_code is not None else RANK_LOCATION_CODE
        log.info(
            "check-ranks source=dataforseo keywords=%d domain=%r location_code=%s base=%s",
            len(keywords), domain, code, DATAFORSEO_BASE,
        )
        return _dataforseo(domain, [k["term"] for k in keywords], code), "dataforseo"
    log.info("check-ranks source=simulated keywords=%d domain=%r", len(keywords), domain)
    return _simulated(keywords), "simulated"


def _simulated(keywords: list[dict]) -> dict:
    out = {}
    for k in keywords:
        cur = k.get("currentRank")
        base = cur if isinstance(cur, int) else random.randint(8, 45)
        out[k["term"]] = max(1, min(100, base + random.randint(-4, 3)))
    return out


def _domain_matches(item_domain: str | None, target: str) -> bool:
    d = (item_domain or "").lower()
    return d == target or d == f"www.{target}" or d.endswith("." + target)


def _dataforseo(domain: str, terms: list[str], location_code: int) -> dict:
    """DataForSEO's LIVE endpoint accepts only ONE task per request
    (batching returns 40000 "You can set only one task at a time"), so we
    send one POST per keyword. Those calls are independent, so we run them
    CONCURRENTLY — otherwise a 30-keyword project would take minutes.
    Each task asks Google for the top RANK_CHECK_DEPTH organic results for
    that keyword in the given country (location_code) / configured language."""
    auth = base64.b64encode(f"{DATAFORSEO_LOGIN}:{DATAFORSEO_PASSWORD}".encode()).decode()

    def _lookup(term: str):
        task = {
            "keyword": term,
            "location_code": location_code,
            "language_code": RANK_LANGUAGE,
            "device": "desktop",
            "depth": RANK_CHECK_DEPTH,
        }
        url = f"{DATAFORSEO_BASE}/v3/serp/google/organic/live/advanced"
        req = urllib.request.Request(
            url,
            data=json.dumps([task]).encode(),
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as res:
            http_status = res.status
            payload = json.loads(res.read())
        # Full endpoint + top-level response health. cost/tasks_error reveal
        # billing and auth/balance problems even when HTTP is 200.
        log.info(
            "rank-check term=%r POST %s (base=%s) http=%s cost=%s tasks_error=%s status_code=%s",
            term, url, DATAFORSEO_BASE, http_status,
            payload.get("cost"), payload.get("tasks_error"), payload.get("status_code"),
        )
        tasks = payload.get("tasks") or []
        if not tasks or tasks[0].get("status_code") != 20000:
            log.info(
                "rank-check term=%r task failed task_status_code=%s task_status_message=%s -> not found",
                term,
                tasks[0].get("status_code") if tasks else None,
                tasks[0].get("status_message") if tasks else None,
            )
            return None  # task failed; treat as "not found"
        # Collect every returned item once so we can both log the SERP and then
        # scan it. Order is preserved, so first-match behavior is unchanged.
        items = [item for result in (tasks[0].get("result") or []) for item in (result.get("items") or [])]
        organic_domains = [it.get("domain") for it in items if it.get("type") == "organic"]
        # _domain_matches normalizes only the SERP side (accepts www.<target>
        # and *.<target>); it does NOT strip scheme/www/path from `domain` (the
        # project string). So `target_domain` below is exactly what's compared.
        log.info(
            "rank-check term=%r items=%d organic=%d first_domains=%s target_domain=%r "
            "(matching: lowercases SERP domain, accepts www.<target> and *.<target>; "
            "does NOT strip scheme/www/path from target)",
            term, len(items), len(organic_domains), organic_domains[:10], domain,
        )
        for item in items:
            # rank_group = position among ORGANIC results only;
            # rank_absolute would also count ads/SERP features.
            if item.get("type") == "organic" and _domain_matches(item.get("domain"), domain):
                return item.get("rank_group")
        return None

    out: dict = {t: None for t in terms}
    if not terms:
        return out

    errors: list[Exception] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(terms))) as pool:
        future_to_term = {pool.submit(_lookup, t): t for t in terms}
        for future in concurrent.futures.as_completed(future_to_term):
            term = future_to_term[future]
            try:
                out[term] = future.result()
            except Exception as exc:  # network/HTTP failure for this one keyword
                errors.append(exc)

    # If EVERY request failed (bad auth, no balance, outage), surface it as
    # an error instead of silently reporting "all not found".
    if errors and len(errors) == len(terms):
        raise errors[0]
    return out
