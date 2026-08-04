import calendar
import concurrent.futures
from datetime import date, datetime, timedelta, timezone

from . import analytics_provider as ga
from . import search_console_provider as scp

MATURATION_DAYS = 2

#: Concurrency for the per-section GA4 fan-out. Kept modest so a report can't
#: exhaust Google's per-property quota in one burst.
_GA4_FANOUT = 6

#: A long-lived pool, deliberately NOT created per call. Both Google clients are
#: cached in thread-local storage (analytics_provider._analytics_client,
#: search_console_provider._build_service), so reusing the same worker threads
#: means each one builds its client — and does its OAuth token exchange — once
#: for the life of the process. A fresh pool per call would pay that every time.
_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=_GA4_FANOUT, thread_name_prefix="google-fanout"
)

GA4_MAX_METRICS = 10
GA4_MAX_DIMENSIONS = 9

GA4_SECTIONS = (
    {"key": "users_overview", "dimensions": [],
     "metrics": ["activeUsers", "newUsers", "totalUsers", "userEngagementDuration", "engagedSessions", "sessions"],
     "limit": None, "returning": True},
    {"key": "users_trend", "dimensions": ["date"],
     "metrics": ["activeUsers", "newUsers"],
     "limit": None, "order_by_dim": True},
    # firstUserPrimaryChannelGroup — deliberately first-user scope, matching the
    # GA4 User acquisition report the team reconciles reports against. Note this
    # answers "where were these users originally acquired", not "where did this
    # month's visits come from"; session scope is the other option if that
    # changes. "Primary" (not "Default") is GA4's current grouping model.
    {"key": "by_channel", "dimensions": ["firstUserPrimaryChannelGroup"],
     "metrics": ["totalUsers", "newUsers", "activeUsers", "engagedSessions", "userEngagementDuration"],
     "limit": None},
    {"key": "by_country_city", "dimensions": ["country", "region", "city"],
     "metrics": ["activeUsers", "newUsers", "engagedSessions", "engagementRate", "userEngagementDuration"],
     "limit": 50},
    {"key": "by_landing_page", "dimensions": ["landingPagePlusQueryString"],
     "metrics": ["sessions", "activeUsers", "newUsers", "userEngagementDuration"],
     "limit": 25},
    {"key": "by_browser", "dimensions": ["browser"],
     "metrics": ["activeUsers", "newUsers"], "limit": 25},
    {"key": "by_device", "dimensions": ["deviceCategory"],
     "metrics": ["activeUsers", "newUsers"], "limit": None},
    {"key": "by_operating_system", "dimensions": ["operatingSystem"],
     "metrics": ["activeUsers", "newUsers"], "limit": 25},
    {"key": "by_language", "dimensions": ["language"],
     "metrics": ["activeUsers", "newUsers"], "limit": 25},
    {"key": "top_pages", "dimensions": ["pagePath"],
     "metrics": ["screenPageViews", "sessions", "activeUsers", "userEngagementDuration"],
     "limit": 25},
)

_GA4_DELTA_KEYS = ("activeUsers", "newUsers", "totalUsers", "returningUsers", "avgEngagementSeconds")
_GSC_DELTA_KEYS = ("clicks", "impressions", "ctr", "position")


class GoogleFetchError(Exception):
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def reason_text(self) -> str:
        return self.message


class GoogleAccessError(GoogleFetchError):
    retryable = False


class GoogleTransportError(GoogleFetchError):
    retryable = True


def _parse_period(period_key: str) -> tuple[int, int]:
    y_str, m_str = str(period_key).split("-")
    y, m = int(y_str), int(m_str)
    if not (1 <= m <= 12):
        raise ValueError(f"bad month in period_key {period_key!r}")
    return y, m


def month_bounds(period_key: str) -> tuple[str, str]:
    y, m = _parse_period(period_key)
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


def previous_period(period_key: str) -> str:
    y, m = _parse_period(period_key)
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def period_is_complete(period_key: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    try:
        y, m = _parse_period(period_key)
    except (ValueError, AttributeError):
        return False
    last = calendar.monthrange(y, m)[1]
    month_end = date(y, m, last)
    return now.date() >= month_end + timedelta(days=MATURATION_DAYS)


def period_has_started(period_key: str, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    try:
        y, m = _parse_period(period_key)
    except (ValueError, AttributeError):
        return False
    return now.date() >= date(y, m, 1)


def report_window(period_key: str, now: datetime | None = None) -> tuple[str, str]:
    now = now or datetime.now(timezone.utc)
    start, end = month_bounds(period_key)
    today = now.date().isoformat()
    if today < end:
        end = today
    return start, end


def _num(raw):
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else round(f, 4)


def _derive(metrics: dict) -> dict:
    out = dict(metrics)
    active = metrics.get("activeUsers")
    dur = metrics.get("userEngagementDuration")
    if dur is not None and "activeUsers" in metrics:
        out["avgEngagementSeconds"] = round(dur / active, 1) if active else 0
    es = metrics.get("engagedSessions")
    if es is not None and "activeUsers" in metrics:
        out["engagedSessionsPerUser"] = round(es / active, 4) if active else 0
    return out


def _ga4_types():
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest,
    )
    return DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest


def _ga4_call(client, request, property_id: str):
    try:
        from google.api_core import exceptions as gax
    except ImportError:
        gax = None
    try:
        return client.run_report(request)
    except Exception as exc:  # noqa: BLE001 — classified and re-raised below
        if gax is not None and isinstance(exc, (gax.PermissionDenied, gax.Unauthenticated)):
            raise GoogleAccessError(
                f"GA4 403 for property {property_id}: service account lacks access ({exc})"
            )
        raise GoogleTransportError(
            f"GA4 transport error for property {property_id} (retryable): {exc}"
        )


def _ga4_run_section(client, resource, section, date_range, property_id) -> dict:
    DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest = _ga4_types()
    dims = section["dimensions"]
    metrics = section["metrics"]
    if len(dims) > GA4_MAX_DIMENSIONS:
        raise GoogleAccessError(
            f"GA4 section {section['key']} declares {len(dims)} dimensions (>{GA4_MAX_DIMENSIONS} cap)"
        )
    chunks = [metrics[i:i + GA4_MAX_METRICS] for i in range(0, len(metrics), GA4_MAX_METRICS)] or [[]]

    merged_rows: dict = {}
    merged_totals: dict = {}
    for chunk in chunks:
        kwargs = dict(
            property=resource,
            dimensions=[Dimension(name=d) for d in dims],
            metrics=[Metric(name=m) for m in chunk],
            date_ranges=[DateRange(start_date=date_range[0], end_date=date_range[1])],
            metric_aggregations=[MetricAggregation.TOTAL],
        )
        if dims and section.get("order_by_dim"):
            kwargs["order_bys"] = [OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name=dims[0]), desc=False)]
        elif dims and chunk:
            kwargs["order_bys"] = [OrderBy(metric=OrderBy.MetricOrderBy(metric_name=chunk[0]), desc=True)]
        if dims and section["limit"]:
            kwargs["limit"] = section["limit"]
        response = _ga4_call(client, RunReportRequest(**kwargs), property_id)

        for row in response.rows:
            key = tuple(dv.value for dv in row.dimension_values)
            entry = merged_rows.setdefault(key, {"dims": list(key), "metrics": {}})
            for i, name in enumerate(chunk):
                entry["metrics"][name] = _num(row.metric_values[i].value if i < len(row.metric_values) else "0")
        if getattr(response, "totals", None):
            tv = response.totals[0].metric_values
            for i, name in enumerate(chunk):
                merged_totals[name] = _num(tv[i].value if i < len(tv) else "0")
        else:
            for name in chunk:
                merged_totals.setdefault(name, 0)

    rows = [{"dims": e["dims"], "metrics": _derive(e["metrics"])} for e in merged_rows.values()]
    return {"dimensions": list(dims), "rows": rows, "totals": _derive(merged_totals)}


def _ga4_returning(client, resource, date_range, property_id) -> int:
    DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest = _ga4_types()
    request = RunReportRequest(
        property=resource,
        dimensions=[Dimension(name="newVsReturning")],
        metrics=[Metric(name="activeUsers")],
        date_ranges=[DateRange(start_date=date_range[0], end_date=date_range[1])],
    )
    response = _ga4_call(client, request, property_id)
    for row in response.rows:
        label = row.dimension_values[0].value if row.dimension_values else ""
        if str(label).strip().lower() == "returning":
            return _num(row.metric_values[0].value if row.metric_values else "0")
    return 0


def _ga4_section_task(resource, sec, date_range, property_id):
    """Runs on a worker thread; grabs that thread's own GA4 client."""
    return _ga4_run_section(ga._analytics_client(), resource, sec, date_range, property_id)


def _ga4_returning_task(resource, date_range, property_id):
    return _ga4_returning(ga._analytics_client(), resource, date_range, property_id)


def _ga4_collect(resource, date_range, property_id) -> dict:
    """Fetch every GA4 section for one date range, concurrently.

    The sections are independent queries against the same property, and each is a
    blocking HTTPS round trip of a few hundred milliseconds. Running them one
    after another meant a report waited on eleven serialised requests per date
    range — and fetch_ga4 covers two ranges, so twenty-two. Fanning them out
    reduces that to roughly the cost of the slowest single call.
    """
    sections: dict = {}
    future_to_key = {
        _pool.submit(_ga4_section_task, resource, sec, date_range, property_id): sec["key"]
        for sec in GA4_SECTIONS
    }
    needs_returning = [sec for sec in GA4_SECTIONS if sec.get("returning")]
    returning_future = (
        _pool.submit(_ga4_returning_task, resource, date_range, property_id)
        if needs_returning
        else None
    )

    # .result() re-raises worker exceptions here, so failures propagate exactly
    # as they did when this ran sequentially.
    for future, key in future_to_key.items():
        sections[key] = future.result()

    if returning_future is not None:
        returning = returning_future.result()
        for sec in needs_returning:
            sections[sec["key"]]["totals"]["returningUsers"] = returning

    ordered = {sec["key"]: sections[sec["key"]] for sec in GA4_SECTIONS}
    return {"range": list(date_range), "sections": ordered}


def fetch_ga4(property_id, cur_range: tuple[str, str], prev_range: tuple[str, str]) -> dict:
    # Deliberately NOT @cached. report_service._fetch_section mutates the returned
    # dict (`section["source"] = ...`), and response_cache hands out the stored
    # object by reference — so caching here writes callers' mutations back into
    # the cache. The per-section fan-out below is where the real win is anyway.
    if not property_id or not str(property_id).strip():
        raise GoogleAccessError("GA4 not configured: this project has no GA4 property id set")
    pid = str(property_id).strip()
    resource = pid if pid.startswith("properties/") else f"properties/{pid}"

    try:
        # Validate credentials up front so a bad key still produces the same
        # GoogleAccessError it always did, rather than surfacing from a worker.
        ga._analytics_client()
    except Exception as exc:
        raise GoogleAccessError(f"GA4 credentials could not be loaded for property {pid}: {exc}")

    report = _ga4_collect(resource, cur_range, pid)
    prior = _ga4_collect(resource, prev_range, pid)

    cur_tot = report["sections"]["users_overview"]["totals"]
    prev_tot = prior["sections"]["users_overview"]["totals"]
    deltas = {k: _delta(cur_tot.get(k), prev_tot.get(k)) for k in _GA4_DELTA_KEYS}

    return {
        "property_id": pid,
        "report_month": report,
        "prior_month": prior,
        "deltas": deltas,
    }


def _gsc_query(service, site_url: str, body: dict) -> list[dict]:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = None
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
        return response.get("rows", []) or []
    except Exception as exc:  # noqa: BLE001 — classified and re-raised below
        status = None
        if HttpError is not None and isinstance(exc, HttpError):
            status = getattr(getattr(exc, "resp", None), "status", None)
            try:
                status = int(status)
            except (TypeError, ValueError):
                status = None
        if status in (401, 403):
            raise GoogleAccessError(
                f"GSC {status} for {site_url}: service account lacks access ({exc})"
            )
        if status == 400:
            raise GoogleAccessError(
                f"GSC 400 for {site_url}: request rejected — check the exact gsc_site_url ({exc})"
            )
        raise GoogleTransportError(
            f"GSC transport error for {site_url} (retryable): {exc}"
        )


def _gsc_collect(service, site_url: str, date_range: tuple[str, str]) -> dict:
    # dataState "all" includes the freshest, still-incomplete days, matching what
    # the GSC UI shows. The API default is "final", which silently omitted the
    # last two to three days and made every report figure read low.
    body = {
        "startDate": date_range[0],
        "endDate": date_range[1],
        "dataState": "all",
        "type": "web",
    }

    # Left sequential on purpose: `service` is a googleapiclient resource, which
    # is not thread-safe (hence the threading.local cache in _build_service), so
    # it must not be shared across workers. GSC is only four calls per report
    # against GA4's twenty-two, so there is little to win here anyway.
    totals_rows = _gsc_query(service, site_url, dict(body))
    totals = scp._metrics(totals_rows[0]) if totals_rows else {
        "clicks": 0, "impressions": 0, "ctr": 0, "position": 0,
    }
    trend_rows = _gsc_query(
        service, site_url, {**body, "dimensions": ["date"], "rowLimit": 1000}
    )
    trend = sorted(
        ({"date": (r.get("keys") or [""])[0], **scp._metrics(r)} for r in trend_rows),
        key=lambda d: d["date"],
    )
    return {"range": list(date_range), "totals": totals, "trend": trend}


def fetch_gsc(site_url, cur_range: tuple[str, str], prev_range: tuple[str, str]) -> dict:
    # Not cached, for the same aliasing reason as fetch_ga4 above.
    if not site_url or not str(site_url).strip():
        raise GoogleAccessError("GSC not configured: this project has no gsc_site_url set")
    url = str(site_url).strip()

    service, err = scp._build_service()
    if err:
        raise GoogleAccessError(f"GSC could not be initialised for {url}: {err}")

    report = _gsc_collect(service, url, cur_range)
    prior = _gsc_collect(service, url, prev_range)
    deltas = {k: _delta(report["totals"].get(k), prior["totals"].get(k)) for k in _GSC_DELTA_KEYS}

    return {
        "site_url": url,
        "report_month": report,
        "prior_month": prior,
        "deltas": deltas,
    }


def _delta(current, previous):
    if current is None or previous is None:
        return None
    value = current - previous
    return round(value, 4) if isinstance(value, float) else value
