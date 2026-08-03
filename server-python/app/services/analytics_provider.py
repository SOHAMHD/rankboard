import threading

from ..config import GOOGLE_SERVICE_ACCOUNT_JSON
from .response_cache import cached

_METRICS = ["activeUsers", "newUsers", "userEngagementDuration", "sessions"]

_BREAKDOWNS = [
    ("byChannel", "sessionDefaultChannelGroup", None),
    ("byCountry", "country", 25),
    ("byCity", "city", 25),
    ("byLandingPage", "landingPagePlusQueryString", 25),
    ("byBrowser", "browser", 25),
    ("byDevice", "deviceCategory", None),
    ("byLanguage", "language", 25),
]

ALLOWED_DIMENSIONS = {
    "country", "region", "city", "continent", "language",
    "sessionDefaultChannelGroup", "sessionSource", "sessionMedium",
    "sessionSourceMedium", "sessionCampaignName",
    "firstUserDefaultChannelGroup", "firstUserSource", "firstUserMedium",
    "firstUserCampaignName",
    "deviceCategory", "operatingSystem", "operatingSystemWithVersion",
    "browser", "platform", "screenResolution", "mobileDeviceModel",
    "mobileDeviceBranding",
    "landingPagePlusQueryString", "pagePath", "pagePathPlusQueryString",
    "pageTitle", "fullPageUrl", "hostName",
    "eventName",
    "newVsReturning", "signedInWithUserId", "audienceName",
    "date", "dateHour", "hour", "dayOfWeekName", "week", "month", "year",
    "userAgeBracket", "userGender", "brandingInterest",
}

_BREAKDOWN_LIMIT = 25

ALLOWED_METRICS = {
    "activeUsers", "newUsers", "totalUsers", "sessions", "engagedSessions",
    "engagementRate", "averageSessionDuration", "userEngagementDuration",
    "screenPageViews", "eventCount", "bounceRate", "keyEvents", "totalRevenue",
}

DERIVED_METRICS = {
    "engagedSessionsPerUser": {
        "label": "Engaged Sessions / Active User",
        "helpers": ["engagedSessions", "activeUsers"],
    },
    "averageEngagementTime": {
        "label": "Avg Engagement Time",
        "helpers": ["userEngagementDuration", "activeUsers"],
    },
}

REPORT_METRICS = ALLOWED_METRICS | set(DERIVED_METRICS)

ALLOWED_MATCH_TYPES = {"EXACT", "CONTAINS", "BEGINS_WITH", "ENDS_WITH", "FULL_REGEXP"}


_local = threading.local()


def _analytics_client():
    """One GA4 client per thread, built once and reused.

    Previously a new client was constructed on every call: re-read the service
    account key from disk, re-parse the RSA private key, and — the expensive part
    — perform a fresh OAuth token exchange with Google. A single report makes
    twenty-odd GA4 calls, so that was twenty-odd needless token round trips.

    Cached in thread-local storage rather than a single shared instance, matching
    search_console_provider._build_service. The underlying transport wraps a
    requests.Session, which isn't guaranteed thread-safe, so each worker thread
    gets its own client instead of sharing one.
    """
    cached = getattr(_local, "ga_client", None)
    if cached is not None:
        return cached

    from google.analytics.data_v1beta import BetaAnalyticsDataClient

    raw = GOOGLE_SERVICE_ACCOUNT_JSON
    if raw.lstrip().startswith("{"):
        import json
        client = BetaAnalyticsDataClient.from_service_account_info(
            json.loads(raw), transport="rest"
        )
    else:
        client = BetaAnalyticsDataClient.from_service_account_json(raw, transport="rest")
    _local.ga_client = client
    return client


def build_dimension_filter(filters: list[dict] | None, match: str = "AND"):
    if not filters:
        return None
    from google.analytics.data_v1beta.types import (
        Filter,
        FilterExpression,
        FilterExpressionList,
    )
    expressions = []
    for f in filters:
        match_type = Filter.StringFilter.MatchType[f["operator"]]
        expr = FilterExpression(
            filter=Filter(
                field_name=f["dimension"],
                string_filter=Filter.StringFilter(
                    match_type=match_type,
                    value=f.get("value", ""),
                    case_sensitive=False,
                ),
            )
        )
        if f.get("exclude"):
            expr = FilterExpression(not_expression=expr)
        expressions.append(expr)
    group = FilterExpressionList(expressions=expressions)
    if str(match).upper() == "AND":
        return FilterExpression(and_group=group)
    return FilterExpression(or_group=group)


@cached("get_analytics")
def get_analytics(
    property_id: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> dict:
    start_date = start_date or "28daysAgo"
    end_date = end_date or "today"

    if not property_id or not str(property_id).strip():
        return {
            "configured": False,
            "message": "Add this project's GA4 property ID to see traffic.",
        }

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            MetricAggregation,
            OrderBy,
            RunReportRequest,
        )
    except ImportError:
        return {"error": "The google-analytics-data package is not installed on the server."}

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return {
            "configured": False,
            "message": "GA4 is not configured on the server (no service-account key set).",
        }

    try:
        client = _analytics_client()
    except Exception as exc:
        print("GA4 service-account key load failed:", exc)
        return {"error": "Google Analytics isn't configured correctly on the server."}

    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"
    date_ranges = [DateRange(start_date=start_date, end_date=end_date)]
    metrics = [Metric(name=m) for m in _METRICS]
    dimension_filter = build_dimension_filter(filters, match)

    import concurrent.futures

    summary_req = RunReportRequest(
        property=resource, metrics=metrics, date_ranges=date_ranges,
        dimension_filter=dimension_filter,
    )
    bydate_req = RunReportRequest(
        property=resource, dimensions=[Dimension(name="date")],
        metrics=[Metric(name="activeUsers"), Metric(name="newUsers")],
        date_ranges=date_ranges,
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
        dimension_filter=dimension_filter,
    )

    def _breakdown_req(dimension, limit):
        kwargs = dict(
            property=resource, dimensions=[Dimension(name=dimension)], metrics=metrics,
            date_ranges=date_ranges, metric_aggregations=[MetricAggregation.TOTAL],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
            dimension_filter=dimension_filter,
        )
        if limit is not None:
            kwargs["limit"] = limit
        return RunReportRequest(**kwargs)

    jobs = [
        ("summary", summary_req, lambda r: _summary(r)),
        ("byDate", bydate_req, lambda r: {"rows": _date_rows(r)}),
    ]
    for bucket, dimension, limit in _BREAKDOWNS:
        jobs.append(
            (bucket, _breakdown_req(dimension, limit),
             lambda r: {"rows": _rows(r), "totals": _totals(r)})
        )

    def _run(job):
        key, req, parse = job
        return key, parse(client.run_report(req))

    out: dict = {"configured": True}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(jobs))) as pool:
            for key, value in pool.map(_run, jobs):
                out[key] = value
    except Exception as exc:
        return {"error": f"Google Analytics request failed: {exc}"}
    return out


@cached("get_dimension_breakdown")
def get_dimension_breakdown(
    property_id: str | None,
    dimension: str,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> dict:
    start_date = start_date or "28daysAgo"
    end_date = end_date or "today"

    if not property_id or not str(property_id).strip():
        return {"error": "This project has no GA4 property ID set.", "dimension": dimension}

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            MetricAggregation,
            OrderBy,
            RunReportRequest,
        )
    except ImportError:
        return {"error": "The google-analytics-data package is not installed on the server.", "dimension": dimension}

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return {"error": "GA4 is not configured on the server (no service-account key set).", "dimension": dimension}

    try:
        client = _analytics_client()
    except Exception as exc:
        return {"error": f"Could not load the Google service-account key: {exc}", "dimension": dimension}

    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"

    try:
        request = RunReportRequest(
            property=resource,
            dimensions=[Dimension(name=dimension)],
            metrics=[Metric(name=m) for m in _METRICS],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metric_aggregations=[MetricAggregation.TOTAL],
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
            limit=_BREAKDOWN_LIMIT,
            dimension_filter=build_dimension_filter(filters, match),
        )
        response = client.run_report(request)
    except Exception as exc:
        return {"error": f"Google Analytics request failed: {exc}", "dimension": dimension}

    return {
        "dimension": dimension,
        "rows": _breakdown_rows(response),
        "totals": _breakdown_totals(response),
    }


@cached("run_custom_report")
def run_custom_report(
    property_id: str | None,
    start: str | None,
    end: str | None,
    dimensions: list[str],
    metrics: list[str],
    filters: list[dict] | None = None,
    match: str = "AND",
    limit: int = 250,
) -> dict:
    start = start or "28daysAgo"
    end = end or "today"
    filters = filters or []

    if not property_id or not str(property_id).strip():
        return {"error": "This project has no GA4 property ID set."}

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            MetricAggregation,
            OrderBy,
            RunReportRequest,
        )
    except ImportError:
        return {"error": "The google-analytics-data package is not installed on the server."}

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        return {"error": "GA4 is not configured on the server (no service-account key set)."}

    try:
        client = _analytics_client()
    except Exception as exc:
        print("GA4 service-account key load failed:", exc)
        return {"error": "Google Analytics isn't configured correctly on the server."}

    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"

    selected = list(metrics)
    derived_selected = [m for m in selected if m in DERIVED_METRICS]
    ga_metrics = [m for m in selected if m not in DERIVED_METRICS]
    for d in derived_selected:
        for h in DERIVED_METRICS[d]["helpers"]:
            if h not in ga_metrics:
                ga_metrics.append(h)

    try:
        kwargs = dict(
            property=resource,
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in ga_metrics],
            date_ranges=[DateRange(start_date=start, end_date=end)],
            metric_aggregations=[MetricAggregation.TOTAL],
            limit=limit or 250,
        )
        if selected:
            first = selected[0]
            if first in DERIVED_METRICS:
                helpers = DERIVED_METRICS[first]["helpers"]
                order_metric = helpers[0] if helpers else "activeUsers"
            else:
                order_metric = first
            kwargs["order_bys"] = [
                OrderBy(metric=OrderBy.MetricOrderBy(metric_name=order_metric), desc=True)
            ]

        dimension_filter = build_dimension_filter(filters, match)
        if dimension_filter is not None:
            kwargs["dimension_filter"] = dimension_filter

        response = client.run_report(RunReportRequest(**kwargs))
    except Exception as exc:
        return {"error": f"Google Analytics request failed: {exc}"}

    report = _custom_report(response, dimensions, ga_metrics)
    return _apply_derived(report, selected, derived_selected)


def _apply_derived(report: dict, selected: list[str], derived_selected: list[str]) -> dict:
    def compute(values: dict) -> dict:
        for d in derived_selected:
            num_name, denom_name = DERIVED_METRICS[d]["helpers"]
            num = values.get(num_name, 0)
            denom = values.get(denom_name, 0)
            try:
                values[d] = round(num / denom, 4) if denom else 0
            except (TypeError, ZeroDivisionError):
                values[d] = 0
        return values

    def trim(values: dict) -> dict:
        return {name: values.get(name, 0) for name in selected}

    rows = [{"dims": r["dims"], "metrics": trim(compute(r["metrics"]))} for r in report["rows"]]
    totals = trim(compute(report["totals"]))
    return {
        "dimensions": report["dimensions"],
        "metrics": list(selected),
        "rows": rows,
        "totals": totals,
    }


@cached("get_returning_users")
def get_returning_users(
    property_id: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> int:
    start_date = start_date or "28daysAgo"
    end_date = end_date or "today"
    if not property_id or not str(property_id).strip():
        return 0

    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )

        if not GOOGLE_SERVICE_ACCOUNT_JSON:
            return 0
        client = _analytics_client()
        prop = str(property_id).strip()
        resource = prop if prop.startswith("properties/") else f"properties/{prop}"
        request = RunReportRequest(
            property=resource,
            dimensions=[Dimension(name="newVsReturning")],
            metrics=[Metric(name="activeUsers")],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            dimension_filter=build_dimension_filter(filters, match),
        )
        response = client.run_report(request)
        for row in response.rows:
            label = row.dimension_values[0].value if row.dimension_values else ""
            if str(label).strip().lower() == "returning":
                return _as_int(row.metric_values[0].value if row.metric_values else "0")
    except Exception:
        return 0
    return 0


def _custom_report(response, dimensions: list[str], metrics: list[str]) -> dict:
    rows = []
    for row in response.rows:
        dims = [dv.value for dv in row.dimension_values]
        mvals = {
            name: _as_num(row.metric_values[i].value if i < len(row.metric_values) else "0")
            for i, name in enumerate(metrics)
        }
        rows.append({"dims": dims, "metrics": mvals})

    if getattr(response, "totals", None):
        values = response.totals[0].metric_values
        totals = {
            name: _as_num(values[i].value if i < len(values) else "0")
            for i, name in enumerate(metrics)
        }
    else:
        totals = {name: 0 for name in metrics}

    return {
        "dimensions": list(dimensions),
        "metrics": list(metrics),
        "rows": rows,
        "totals": totals,
    }


def _as_num(raw):
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return raw
    return int(f) if f.is_integer() else round(f, 4)


def _breakdown_rows(response) -> list[dict]:
    rows = []
    for row in response.rows:
        label = row.dimension_values[0].value if row.dimension_values else ""
        active = _as_int(_metric(row, 0))
        new = _as_int(_metric(row, 1))
        duration = _as_float(_metric(row, 2))
        rows.append({
            "label": label,
            "activeUsers": active,
            "newUsers": new,
            "avgEngagement": _avg_engagement(duration, active),
        })
    return rows


def _breakdown_totals(response) -> dict:
    if not getattr(response, "totals", None):
        return {"activeUsers": 0, "newUsers": 0, "avgEngagement": 0}
    values = response.totals[0].metric_values
    active = _as_int(values[0].value if len(values) > 0 else "0")
    new = _as_int(values[1].value if len(values) > 1 else "0")
    duration = _as_float(values[2].value if len(values) > 2 else "0")
    return {
        "activeUsers": active,
        "newUsers": new,
        "avgEngagement": _avg_engagement(duration, active),
    }


def _rows(response) -> list[dict]:
    rows = []
    for row in response.rows:
        value = row.dimension_values[0].value if row.dimension_values else ""
        active = _as_int(_metric(row, 0))
        new = _as_int(_metric(row, 1))
        duration = _as_float(_metric(row, 2))
        sessions = _as_int(_metric(row, 3))
        rows.append({
            "value": value,
            "activeUsers": active,
            "newUsers": new,
            "sessions": sessions,
            "avgEngagementSeconds": _avg_engagement(duration, active),
        })
    return rows


def _date_rows(response) -> list[dict]:
    rows = []
    for row in response.rows:
        date = row.dimension_values[0].value if row.dimension_values else ""
        rows.append({
            "date": date,
            "activeUsers": _as_int(_metric(row, 0)),
            "newUsers": _as_int(_metric(row, 1)),
        })
    return rows


def _summary(response) -> dict:
    if not response.rows:
        return {"activeUsers": 0, "newUsers": 0, "avgEngagementSeconds": 0}
    row = response.rows[0]
    active = _as_int(_metric(row, 0))
    new = _as_int(_metric(row, 1))
    duration = _as_float(_metric(row, 2))
    return {
        "activeUsers": active,
        "newUsers": new,
        "avgEngagementSeconds": _avg_engagement(duration, active),
    }


def _totals(response) -> dict:
    if not getattr(response, "totals", None):
        return {"activeUsers": 0, "newUsers": 0, "sessions": 0, "avgEngagementSeconds": 0}
    values = response.totals[0].metric_values
    active = _as_int(values[0].value if len(values) > 0 else "0")
    new = _as_int(values[1].value if len(values) > 1 else "0")
    duration = _as_float(values[2].value if len(values) > 2 else "0")
    sessions = _as_int(values[3].value if len(values) > 3 else "0")
    return {
        "activeUsers": active,
        "newUsers": new,
        "sessions": sessions,
        "avgEngagementSeconds": _avg_engagement(duration, active),
    }


def _metric(row, i: int) -> str:
    return row.metric_values[i].value if i < len(row.metric_values) else "0"


def _avg_engagement(duration: float, active: int) -> float:
    if not active:
        return 0
    return round(duration / active, 1)


def _as_int(raw: str) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def _as_float(raw: str) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
