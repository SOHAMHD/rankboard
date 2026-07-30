"""SEARCH CONSOLE PROVIDER — per-project Google Search Console (GSC) data.

Same swappable-transport idea as analytics_provider, but for search
performance rather than GA4 traffic. The SAME Google *service account*
that powers GA4 (its JSON key path comes from
config.GOOGLE_SERVICE_ACCOUNT_JSON) authenticates every call — Search
Console just needs the Search Console API enabled and the service
account granted access to the property. Each project supplies its own
GSC *site URL* (a URL-prefix property like "https://www.example.com/"
or a domain property like "sc-domain:example.com").

get_search_console() runs the Search Analytics API's query once for the
headline totals, once per dimension breakdown (query, page) and once for
a by-date trend, all over the same date range. Every report measures the
same four things — clicks, impressions, CTR, position — so the whole
panel speaks one vocabulary. It never raises: a missing site URL, a
missing/invalid key file, the API not being enabled, or any API error
all come back as {"error": "..."} so a misconfigured project degrades to
a friendly message instead of a 500.
"""
from ..config import GOOGLE_SERVICE_ACCOUNT_JSON
from .response_cache import cached

# Read-only scope — we only ever query, never write. The SAME service-account
# JSON GA4 uses works here once the Search Console API is enabled and the
# account has been added to the property in Search Console.
_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

# Row cap for the query / page breakdowns — keep the busiest ~25 rows.
_ROW_LIMIT = 25

# ── Service cache (per worker thread) ───────────────────────────────────────
# Building the Search Console service is expensive: it loads the credentials,
# fetches/parses the API discovery document, and the first real call performs
# an OAuth token exchange. The old code did all of this on EVERY provider call,
# and the Performance report makes THREE calls per request — so a single page
# load paid that cost three times over (a big chunk of the ~20s slowness).
#
# We cache the built service per THREAD (not a single global) because the
# service's underlying httplib2 transport is not safe to share across threads
# running requests concurrently. FastAPI dispatches these sync endpoints on a
# bounded worker-thread pool, so each thread builds the service once and reuses
# it on every later call — the three queries in one request always run on the
# same thread, sequentially, so they safely share that thread's service.
import threading

_local = threading.local()   # holds `service` per worker thread once built


def _build_service():
    """Return a per-thread cached, authenticated Search Console service, or
    (None, error).

    Built once per worker thread and reused (see the cache note above).
    Imported lazily so the rest of the app (and `python -m py_compile`)
    doesn't hard-depend on google-api-python-client being installed. Tries the
    modern "searchconsole" v1 discovery doc first and falls back to the legacy
    "webmasters" v3 if that name/version doesn't resolve against the installed
    client — both expose searchanalytics().query()."""
    # Fast path: this thread already built one — reuse it.
    cached = getattr(_local, "service", None)
    if cached is not None:
        return cached, None

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return None, "Search Console is not configured on the server (no service-account key set)."

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, "The google-api-python-client package is not installed on the server."

    service, err = _construct_service(Credentials, build)
    if err:
        return None, err
    _local.service = service
    return service, None


def _construct_service(Credentials, build):
    """Load credentials and build the service (no caching). Returns
    (service, None) or (None, error_message)."""
    try:
        # GOOGLE_SERVICE_ACCOUNT_JSON may hold the full JSON key CONTENT (an env
        # var on hosts like Render, where there's no key file on disk) or a PATH
        # to a key file (the local-dev default). JSON content is detected by its
        # leading "{"; anything else is treated as a file path so dev is unchanged.
        raw = GOOGLE_SERVICE_ACCOUNT_JSON
        if raw.lstrip().startswith("{"):
            import json
            credentials = Credentials.from_service_account_info(
                json.loads(raw), scopes=_SCOPES
            )
        else:
            credentials = Credentials.from_service_account_file(
                raw, scopes=_SCOPES
            )
    except Exception as exc:
        return None, f"Could not load the Google service-account key: {exc}"

    try:
        service = build("searchconsole", "v1", credentials=credentials)
    except Exception:
        # Older client libraries only know the legacy "webmasters" v3 name;
        # it exposes the same searchanalytics().query() surface.
        try:
            service = build("webmasters", "v3", credentials=credentials)
        except Exception as exc:
            return None, f"Could not build the Search Console service: {exc}"

    return service, None


def _query(service, site_url: str, body: dict) -> list[dict]:
    """Run one searchanalytics().query() and return its raw rows (may be []).

    Raises on failure — callers wrap this so any error becomes {"error": ...}."""
    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return response.get("rows", []) or []


def _metrics(row: dict) -> dict:
    """The four standard metrics off one Search Analytics row → numbers.
    CTR is a fraction (0–1); position is 1-based. Missing values read as 0."""
    return {
        "clicks": int(row.get("clicks", 0) or 0),
        "impressions": int(row.get("impressions", 0) or 0),
        "ctr": float(row.get("ctr", 0) or 0),
        "position": round(float(row.get("position", 0) or 0), 1),
    }


@cached("get_search_console")
def get_search_console(
    site_url: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Return Search Console performance for one site over a date range:

        {
          "totals":  {clicks, impressions, ctr, position},
          "queries": [{query, clicks, impressions, ctr, position}, ...],
          "pages":   [{page,  clicks, impressions, ctr, position}, ...],
          "trend":   [{date,  clicks, impressions, ctr, position}, ...],  # by date asc
        }

    `site_url` is the GSC property identifier — a URL-prefix property like
    "https://www.example.com/" or a domain property like "sc-domain:example.com".
    start_date / end_date are YYYY-MM-DD; they default to the last 28 days
    (matching the GA4 panel) when not supplied.

    Never raises. On an unset site URL, missing credentials, the Search
    Console API not being enabled, no access to the property, or any API
    error it returns {"error": "<message>"} so the caller can show a friendly
    message instead of a stack trace."""
    if not site_url or not str(site_url).strip():
        return {"error": "No Search Console property configured for this project"}

    site_url = str(site_url).strip()

    # Default to the last 28 days only when a bound isn't supplied. Search
    # Console wants concrete YYYY-MM-DD dates (no "28daysAgo" expressions), so
    # compute them here.
    if not start_date or not end_date:
        from datetime import date, timedelta

        today = date.today()
        end_date = end_date or today.isoformat()
        start_date = start_date or (today - timedelta(days=27)).isoformat()

    service, err = _build_service()
    if err:
        return {"error": err}

    try:
        date_body = {"startDate": start_date, "endDate": end_date}

        # ── Headline totals: no dimensions → a single summary row ──
        totals_rows = _query(service, site_url, {**date_body})
        totals = _metrics(totals_rows[0]) if totals_rows else {
            "clicks": 0, "impressions": 0, "ctr": 0, "position": 0,
        }

        # ── By query (top 25) ──
        query_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["query"], "rowLimit": _ROW_LIMIT},
        )
        queries = [
            {"query": (r.get("keys") or [""])[0], **_metrics(r)} for r in query_rows
        ]

        # ── By page (top 25) ──
        page_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["page"], "rowLimit": _ROW_LIMIT},
        )
        pages = [
            {"page": (r.get("keys") or [""])[0], **_metrics(r)} for r in page_rows
        ]

        # ── Trend by date, ascending ──
        trend_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["date"]},
        )
        trend = sorted(
            ({"date": (r.get("keys") or [""])[0], **_metrics(r)} for r in trend_rows),
            key=lambda d: d["date"],
        )
    except Exception as exc:
        # No access, API not enabled, bad site URL, quota, etc.
        return {"error": f"Search Console request failed: {exc}"}

    return {"totals": totals, "queries": queries, "pages": pages, "trend": trend}


@cached("query_performance")
def query_performance(
    site_url: str | None,
    start: str,
    end: str,
    search_type: str = "web",
    dimensions: list[str] | None = None,
    filters: list[dict] | None = None,
    row_limit: int = 1000,
) -> list[dict] | dict:
    """Run ONE Search Analytics query and return its rows — the building
    block behind the Performance report (the router calls this three times:
    once with no dimensions for the headline totals, once by ["date"] for the
    trend, once by the active table dimension for the rows).

    Builds the searchanalytics.query body the way Google's REST API documents
    it (lowercase enum values — the same form the rest of this module already
    sends, e.g. dimensions=["query"]):

        {
          "startDate": start, "endDate": end,
          "type": search_type,              # web|image|video|news|discover|googleNews
          "dimensions": dimensions,         # omitted when empty (the totals call)
          "rowLimit": row_limit,
          "dimensionFilterGroups": [        # only when `filters` is non-empty
            {"groupType": "and", "filters": [
              {"dimension": .., "operator": .., "expression": ..}, ...
            ]}
          ],
        }

    `type` is the current field name (the legacy alias `searchType` still
    exists in the discovery doc but `type` is canonical). Returns a list of
    rows, each {"keys": [<dimension values>], clicks, impressions, ctr,
    position}; `keys` is [] for the dimensionless totals call. Never raises:
    an unset site URL, missing credentials, the API not being enabled, no
    access, or any API error all come back as {"error": "<message>"} so the
    caller (and ultimately the client) shows a friendly message, never a 500."""
    if not site_url or not str(site_url).strip():
        return {"error": "No Search Console property configured for this project"}

    service, err = _build_service()
    if err:
        return {"error": err}

    dimensions = dimensions or []
    filters = filters or []

    body: dict = {
        "startDate": start,
        "endDate": end,
        "type": search_type,
        "rowLimit": row_limit,
    }
    if dimensions:
        body["dimensions"] = dimensions
    if filters:
        body["dimensionFilterGroups"] = [
            {
                "groupType": "and",
                "filters": [
                    {
                        "dimension": f["dimension"],
                        "operator": f["operator"],
                        "expression": f.get("expression", ""),
                    }
                    for f in filters
                ],
            }
        ]

    try:
        raw_rows = _query(service, str(site_url).strip(), body)
    except Exception as exc:
        # No access, API not enabled, bad site URL / filter, quota, etc.
        return {"error": f"Search Console request failed: {exc}"}

    return [{"keys": r.get("keys") or [], **_metrics(r)} for r in raw_rows]
