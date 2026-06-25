"""REPORT GOOGLE FETCH — live GA4 + GSC fetch for report GENERATION.

The dashboard providers (analytics_provider / search_console_provider) deliberately
NEVER raise — they swallow every failure into {"error": ...} so a misconfigured
project degrades to a friendly message. That's wrong for report generation, where
a setup problem MUST stop the freeze with a SPECIFIC, diagnosable reason. So this
module REUSES their auth/client builders but runs report-shaped queries that
classify every outcome into exactly three cases:

  • SUCCESS (incl. a legitimate ZERO/empty result) → real data, returned to freeze
  • ACCESS/AUTH failure (403/401, bad property/site, missing creds) → GoogleAccessError
  • TRANSPORT failure (timeout, 5xx, 429, network)               → GoogleTransportError

The two error types let the operator tell "fix access" from "retry" apart. Sections
are declared ONCE here (GA4_SECTIONS) and iterated, so adding/removing a section is
a localized change. GA4 Data API per-request caps (≤9 dims, ≤10 metrics) are honored
by splitting a section's metrics into chunks and merging by dimension key.
"""
import calendar
from datetime import date, datetime, timedelta, timezone

from . import analytics_provider as ga          # reuse GA4 auth (_analytics_client)
from . import search_console_provider as scp    # reuse GSC auth (_build_service) + _metrics

# GA4 data matures ~48h; a report month is only eligible once it has fully ended
# AND this buffer has elapsed past the last day. 2 days ≈ 48h.
MATURATION_DAYS = 2

# GA4 Data API per-request limits.
GA4_MAX_METRICS = 10
GA4_MAX_DIMENSIONS = 9

# ── Declarative GA4 sections — the report's FIXED shape (not user-chosen) ──────
# Each: key, the GA4 dimensions + (valid) metric API names, an optional row cap,
# and `returning=True` to additionally derive returning-users via newVsReturning.
# Derived values (avg engagement time, engaged sessions / user) are computed
# generically from whichever component metrics a section requested — NOT sent to
# GA4 (those aren't real metric names).
GA4_SECTIONS = (
    {"key": "users_overview", "dimensions": [],
     "metrics": ["activeUsers", "newUsers", "totalUsers", "userEngagementDuration", "engagedSessions", "sessions"],
     "limit": None, "returning": True},
    {"key": "by_channel", "dimensions": ["sessionDefaultChannelGroup"],
     "metrics": ["totalUsers", "newUsers", "activeUsers", "engagedSessions", "userEngagementDuration"],
     "limit": None},
    {"key": "by_country_city", "dimensions": ["country", "city"],
     "metrics": ["activeUsers", "newUsers", "engagedSessions", "engagementRate", "userEngagementDuration"],
     "limit": 50},
    {"key": "by_landing_page", "dimensions": ["landingPagePlusQueryString"],
     "metrics": ["sessions", "activeUsers", "newUsers", "userEngagementDuration"],
     "limit": 25},
    {"key": "by_browser", "dimensions": ["browser"],
     "metrics": ["activeUsers", "newUsers", "sessions"], "limit": 25},
    {"key": "by_device", "dimensions": ["deviceCategory"],
     "metrics": ["activeUsers", "newUsers", "sessions"], "limit": None},
    {"key": "by_operating_system", "dimensions": ["operatingSystem"],
     "metrics": ["activeUsers", "newUsers", "sessions"], "limit": 25},
    {"key": "by_language", "dimensions": ["language"],
     "metrics": ["activeUsers", "newUsers", "sessions"], "limit": 25},
    {"key": "top_pages", "dimensions": ["pagePath"],
     "metrics": ["screenPageViews", "sessions", "activeUsers", "userEngagementDuration"],
     "limit": 25},
)

# Overview metrics carried into the previous-vs-current deltas the report shows.
_GA4_DELTA_KEYS = ("activeUsers", "newUsers", "totalUsers", "returningUsers", "avgEngagementSeconds")
_GSC_DELTA_KEYS = ("clicks", "impressions", "ctr", "position")


# ── Outcome classification ────────────────────────────────────────────────────
class GoogleFetchError(Exception):
    """Base for a section fetch that must STOP generation. `retryable`
    distinguishes a transport blip from a setup/access problem."""
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def reason_text(self) -> str:
        return self.message


class GoogleAccessError(GoogleFetchError):
    """403/401, wrong property/site, or missing credentials — FIX access, not retry."""
    retryable = False


class GoogleTransportError(GoogleFetchError):
    """Timeout / 5xx / 429 / network — RETRY; access is fine."""
    retryable = True


# ── Period / date helpers ─────────────────────────────────────────────────────
def _parse_period(period_key: str) -> tuple[int, int]:
    y_str, m_str = str(period_key).split("-")
    y, m = int(y_str), int(m_str)
    if not (1 <= m <= 12):
        raise ValueError(f"bad month in period_key {period_key!r}")
    return y, m


def month_bounds(period_key: str) -> tuple[str, str]:
    """ "2026-05" → ("2026-05-01", "2026-05-31") (inclusive YYYY-MM-DD dates the
    GA4 + GSC APIs both accept)."""
    y, m = _parse_period(period_key)
    last = calendar.monthrange(y, m)[1]
    return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"


def previous_period(period_key: str) -> str:
    """ "2026-01" → "2025-12". The prior month the report compares against."""
    y, m = _parse_period(period_key)
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def period_is_complete(period_key: str, now: datetime | None = None) -> bool:
    """True only for a COMPLETE PAST month whose data has had MATURATION_DAYS to
    settle. The current (incomplete) month and any future month return False, so
    generation never freezes unsettled GA4 data."""
    now = now or datetime.now(timezone.utc)
    try:
        y, m = _parse_period(period_key)
    except (ValueError, AttributeError):
        return False
    last = calendar.monthrange(y, m)[1]
    month_end = date(y, m, last)
    return now.date() >= month_end + timedelta(days=MATURATION_DAYS)


# ── number parsing / derivations ──────────────────────────────────────────────
def _num(raw):
    """GA4/GSC return metric values as strings; convert to int when whole, else a
    rounded float. Unparseable → 0."""
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return 0
    return int(f) if f.is_integer() else round(f, 4)


def _derive(metrics: dict) -> dict:
    """Add the derived metrics the report uses, computed from component metrics
    that are present (avg engagement time per active user; engaged sessions per
    active user). A zero denominator yields 0, never an error."""
    out = dict(metrics)
    active = metrics.get("activeUsers")
    dur = metrics.get("userEngagementDuration")
    if dur is not None and "activeUsers" in metrics:
        out["avgEngagementSeconds"] = round(dur / active, 1) if active else 0
    es = metrics.get("engagedSessions")
    if es is not None and "activeUsers" in metrics:
        out["engagedSessionsPerUser"] = round(es / active, 4) if active else 0
    return out


# ── GA4 ───────────────────────────────────────────────────────────────────────
def _ga4_types():
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest,
    )
    return DateRange, Dimension, Metric, MetricAggregation, OrderBy, RunReportRequest


def _ga4_call(client, request, property_id: str):
    """Run one GA4 runReport, classifying failure. PermissionDenied / Unauthenticated
    are reliable ACCESS signals regardless of transport; every other API error
    (5xx, 429, unavailable, deadline) and any non-API exception is TRANSPORT."""
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
    """Run ONE declarative section as a runReport (splitting into ≤10-metric
    chunks merged by dimension key to honor the GA4 limit). Returns
    {dimensions, rows:[{dims, metrics}], totals} with derived metrics applied."""
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
        # Order/limit only make sense WITH a dimension; the dimensionless overview
        # is a single aggregate row.
        if dims and chunk:
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
    """Returning users via the newVsReturning dimension (GA4 does NOT expose a
    `returningUsers` metric, and new+returning don't sum to total). 0 when absent."""
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


def _ga4_collect(client, resource, date_range, property_id) -> dict:
    """Run every GA4 section for one date range → {range, sections}."""
    sections = {}
    for sec in GA4_SECTIONS:
        result = _ga4_run_section(client, resource, sec, date_range, property_id)
        if sec.get("returning"):
            result["totals"]["returningUsers"] = _ga4_returning(client, resource, date_range, property_id)
        sections[sec["key"]] = result
    return {"range": list(date_range), "sections": sections}


def fetch_ga4(property_id, cur_range: tuple[str, str], prev_range: tuple[str, str]) -> dict:
    """Fetch the report month AND prior month from GA4, returning the frozen-ready
    structure (incl. previous-vs-current overview deltas). Raises GoogleAccessError /
    GoogleTransportError on any failure — never a silent {"error": ...}."""
    if not property_id or not str(property_id).strip():
        raise GoogleAccessError("GA4 not configured: this project has no GA4 property id set")
    pid = str(property_id).strip()
    resource = pid if pid.startswith("properties/") else f"properties/{pid}"

    try:
        client = ga._analytics_client()  # reuse the dashboard's service-account auth
    except Exception as exc:  # bad/missing key content → a setup problem, name it
        raise GoogleAccessError(f"GA4 credentials could not be loaded for property {pid}: {exc}")

    report = _ga4_collect(client, resource, cur_range, pid)
    prior = _ga4_collect(client, resource, prev_range, pid)

    cur_tot = report["sections"]["users_overview"]["totals"]
    prev_tot = prior["sections"]["users_overview"]["totals"]
    deltas = {k: _delta(cur_tot.get(k), prev_tot.get(k)) for k in _GA4_DELTA_KEYS}

    return {
        "property_id": pid,
        "report_month": report,
        "prior_month": prior,
        "deltas": deltas,
    }


# ── GSC ───────────────────────────────────────────────────────────────────────
def _gsc_query(service, site_url: str, body: dict) -> list[dict]:
    """Run one searchanalytics().query(), classifying failure by HTTP status:
    401/403/400 → ACCESS (fix the grant or the gsc_site_url); 5xx/429/network →
    TRANSPORT (retry). Returns raw rows (possibly [] — a legitimate empty result)."""
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
    """Totals (clicks/impressions/CTR/avg position) + the daily trend series for
    one month → {range, totals, trend}."""
    body = {"startDate": date_range[0], "endDate": date_range[1]}

    totals_rows = _gsc_query(service, site_url, dict(body))
    totals = scp._metrics(totals_rows[0]) if totals_rows else {
        "clicks": 0, "impressions": 0, "ctr": 0, "position": 0,
    }
    trend_rows = _gsc_query(service, site_url, {**body, "dimensions": ["date"], "rowLimit": 1000})
    trend = sorted(
        ({"date": (r.get("keys") or [""])[0], **scp._metrics(r)} for r in trend_rows),
        key=lambda d: d["date"],
    )
    return {"range": list(date_range), "totals": totals, "trend": trend}


def fetch_gsc(site_url, cur_range: tuple[str, str], prev_range: tuple[str, str]) -> dict:
    """Fetch the report month AND prior month from GSC (totals + daily trend),
    returning the frozen-ready structure with previous-vs-current totals deltas.
    Raises GoogleAccessError / GoogleTransportError on any failure."""
    if not site_url or not str(site_url).strip():
        raise GoogleAccessError("GSC not configured: this project has no gsc_site_url set")
    url = str(site_url).strip()

    service, err = scp._build_service()  # reuse the dashboard's service-account auth
    if err:
        # Missing key / build failure — a setup problem, not retryable.
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


# ── shared ────────────────────────────────────────────────────────────────────
def _delta(current, previous):
    """current - previous, or None when either is missing. (For GSC `position`
    a NEGATIVE delta is an IMPROVEMENT, same rank convention as ranks/Moz.)"""
    if current is None or previous is None:
        return None
    value = current - previous
    return round(value, 4) if isinstance(value, float) else value
