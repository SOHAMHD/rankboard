from ..config import GOOGLE_SERVICE_ACCOUNT_JSON
from .response_cache import cached

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

_ROW_LIMIT = 25

import threading

_local = threading.local()


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
    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return response.get("rows", []) or []


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
        from datetime import date, timedelta

        today = date.today()
        end_date = end_date or today.isoformat()
        start_date = start_date or (today - timedelta(days=27)).isoformat()

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
