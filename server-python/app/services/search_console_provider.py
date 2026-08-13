from datetime import date, datetime, timedelta, timezone

from ..config import GOOGLE_SERVICE_ACCOUNT_JSON
from .response_cache import cached

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

#: Rows fetched per dimension for the summary panels. Was 25, which silently
#: truncated the queries and pages lists well below what the GSC UI shows.
_ROW_LIMIT = 1000

#: Hard cap the Search Analytics API allows in one request.
_API_MAX_ROWS = 25000

#: Search Console reports in Pacific time regardless of the property or the
#: viewer, and its data lags. Using the server's or the browser's "today" as the
#: end date asks for days that do not exist yet, so those days come back empty
#: and every total reads low.
_GSC_TZ_OFFSET_HOURS = -8  # America/Los_Angeles, without a tzdata dependency
_GSC_LAG_DAYS = 3

#: "all" includes the most recent, still-incomplete days — which is what the GSC
#: UI's Performance report shows. The API default is "final", so omitting this
#: silently dropped the last two to three days from every figure.
_DATA_STATE = "all"

import threading

_local = threading.local()


def gsc_today() -> date:
    """Today in Search Console's reporting timezone (Pacific)."""
    return (datetime.now(timezone.utc) + timedelta(hours=_GSC_TZ_OFFSET_HOURS)).date()


def gsc_last_available_date() -> date:
    """The most recent date GSC is likely to have data for."""
    return gsc_today() - timedelta(days=_GSC_LAG_DAYS)


def default_range(days: int = 28) -> tuple[str, str]:
    """A `days`-long window ending at the last date GSC should have data for.

    Mirrors how the GSC UI builds "Last 28 days" — it ends at the newest date
    with data, not at today.
    """
    end = gsc_last_available_date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def _build_service():
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
    try:
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
        try:
            service = build("webmasters", "v3", credentials=credentials)
        except Exception as exc:
            return None, f"Could not build the Search Console service: {exc}"

    return service, None


def _query(service, site_url: str, body: dict) -> list[dict]:
    """Run one Search Analytics query, following startRow pagination.

    Every body gets dataState so the freshest days are included. Without
    pagination a request stopped at rowLimit and the table could never show as
    much as the GSC UI's export.
    """
    body = {"dataState": _DATA_STATE, **body}
    wanted = int(body.get("rowLimit") or _ROW_LIMIT)
    # Always request full pages, regardless of how many rows the caller wants.
    # This was min(wanted, _API_MAX_ROWS), which meant a caller asking for 1000
    # got page_size == 1000, the first response filled it exactly, and the
    # short-page break below fired every time — so the loop could never reach a
    # second page and results were silently capped at `wanted` while the code
    # read as though pagination worked. `rows[:wanted]` at the end still honours
    # the caller's limit.
    page_size = _API_MAX_ROWS

    rows: list[dict] = []
    start_row = 0
    while True:
        page_body = {**body, "rowLimit": page_size, "startRow": start_row}
        response = service.searchanalytics().query(siteUrl=site_url, body=page_body).execute()
        page = response.get("rows", []) or []
        rows.extend(page)
        # A short page means there is nothing more to fetch.
        if len(page) < page_size or len(rows) >= wanted:
            break
        start_row += len(page)
    return rows[:wanted]


def _metrics(row: dict) -> dict:
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
    if not site_url or not str(site_url).strip():
        return {"error": "No Search Console property configured for this project"}

    site_url = str(site_url).strip()

    if not start_date or not end_date:
        # Was date.today() in the SERVER's timezone, with end = today — a date
        # Search Console never has data for.
        default_start, default_end = default_range(28)
        end_date = end_date or default_end
        start_date = start_date or default_start

    service, err = _build_service()
    if err:
        return {"error": err}

    try:
        date_body = {"startDate": start_date, "endDate": end_date}

        totals_rows = _query(service, site_url, {**date_body})
        totals = _metrics(totals_rows[0]) if totals_rows else {
            "clicks": 0, "impressions": 0, "ctr": 0, "position": 0,
        }

        query_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["query"], "rowLimit": _ROW_LIMIT},
        )
        queries = [
            {"query": (r.get("keys") or [""])[0], **_metrics(r)} for r in query_rows
        ]

        page_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["page"], "rowLimit": _ROW_LIMIT},
        )
        pages = [
            {"page": (r.get("keys") or [""])[0], **_metrics(r)} for r in page_rows
        ]

        trend_rows = _query(
            service, site_url,
            {**date_body, "dimensions": ["date"]},
        )
        trend = sorted(
            ({"date": (r.get("keys") or [""])[0], **_metrics(r)} for r in trend_rows),
            key=lambda d: d["date"],
        )
    except Exception as exc:
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
        return {"error": f"Search Console request failed: {exc}"}

    return [{"keys": r.get("keys") or [], **_metrics(r)} for r in raw_rows]
