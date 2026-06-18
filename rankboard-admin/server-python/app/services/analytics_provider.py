"""ANALYTICS PROVIDER — per-project Google Analytics 4 (GA4) traffic.

Same swappable-transport idea as rank_provider, but for traffic rather
than rankings. One Google *service account* (a JSON key whose path
comes from config.GOOGLE_SERVICE_ACCOUNT_JSON) authenticates every
call; each project supplies its own GA4 *property ID*.

get_analytics() runs the GA4 Data API's runReport once for a headline
summary, once for a daily time-series, and once per dimension breakdown
(channel, country, city, landing page, browser, device, language). Every
report measures the same three things — active users, new users, and
average engagement time per active user — so the whole panel speaks one
vocabulary. It never raises: a missing property ID, a missing/invalid
key file, or an API error all come back as a plain dict the router can
hand straight to the client — so a misconfigured project degrades to a
friendly message instead of a 500.
"""
from ..config import GOOGLE_SERVICE_ACCOUNT_JSON

# The GA4 metrics every report requests, in this order. Average engagement
# time is NOT a raw metric — it's derived as userEngagementDuration /
# activeUsers (GA4's "avg engagement time per active user"), so we fetch the
# duration and divide. Sessions is appended LAST (index 3) so the breakdown
# tables can show a permanent Sessions column; the headline summary ignores it.
_METRICS = ["activeUsers", "newUsers", "userEngagementDuration", "sessions"]

# Dimension breakdowns, each one runReport call: (bucket, GA4 dimension,
# row cap). `bucket` is the camelCase key the client reads back. Tables
# are ordered by activeUsers descending; capped ones keep the busiest 25.
# Channel and device are naturally small, so they stay uncapped.
_BREAKDOWNS = [
    ("byChannel", "sessionDefaultChannelGroup", None),
    ("byCountry", "country", 25),
    ("byCity", "city", 25),
    ("byLandingPage", "landingPagePlusQueryString", 25),
    ("byBrowser", "browser", 25),
    ("byDevice", "deviceCategory", None),
    ("byLanguage", "language", 25),
]

# Allowlist for the dynamic dimension picker (get_dimension_breakdown): the
# SAME set of GA4 API names the frontend's DIMENSION_GROUPS map offers,
# grouped here by the same categories for easy diffing. The router validates
# ?dimension= against this set so we never hand GA4 an arbitrary string.
ALLOWED_DIMENSIONS = {
    # Geography
    "country", "region", "city", "continent", "language",
    # Traffic source (session)
    "sessionDefaultChannelGroup", "sessionSource", "sessionMedium",
    "sessionSourceMedium", "sessionCampaignName",
    # Traffic source (first user)
    "firstUserDefaultChannelGroup", "firstUserSource", "firstUserMedium",
    "firstUserCampaignName",
    # Platform / device
    "deviceCategory", "operatingSystem", "operatingSystemWithVersion",
    "browser", "platform", "screenResolution", "mobileDeviceModel",
    "mobileDeviceBranding",
    # Page / screen
    "landingPagePlusQueryString", "pagePath", "pagePathPlusQueryString",
    "pageTitle", "fullPageUrl", "hostName",
    # User
    "newVsReturning", "signedInWithUserId", "audienceName",
    # Time
    "date", "dateHour", "hour", "dayOfWeekName", "week", "month", "year",
    # Demographics (needs Google Signals)
    "userAgeBracket", "userGender", "brandingInterest",
}

# Row cap for a single-dimension breakdown — keep the busiest ~25 rows.
_BREAKDOWN_LIMIT = 25

# Allowlist for the custom report builder's metric picker — the SAME set of
# GA4 metric API names the frontend's METRICS map offers. The router validates
# every requested metric against this so we never hand GA4 an arbitrary string.
ALLOWED_METRICS = {
    "activeUsers", "newUsers", "totalUsers", "sessions", "engagedSessions",
    "engagementRate", "averageSessionDuration", "userEngagementDuration",
    "screenPageViews", "eventCount", "bounceRate", "keyEvents", "totalRevenue",
}

# Derived (computed) metrics — NOT real GA4 metric names; these are never sent
# to GA4. Each is computed after the report returns from its real "helper"
# metrics (which we auto-add to the request when needed). label is for parity
# with the frontend METRICS map; the report builder accepts these names too.
DERIVED_METRICS = {
    "engagedSessionsPerUser": {
        "label": "Engaged Sessions / Active User",
        "helpers": ["engagedSessions", "activeUsers"],  # numerator, denominator
    },
}

# What the report builder accepts when validating a selection: every real GA4
# metric plus the derived ones (which run_custom_report resolves specially).
REPORT_METRICS = ALLOWED_METRICS | set(DERIVED_METRICS)

# Allowlist for filter operators — GA4 StringFilter match-type names, mirroring
# the frontend's operator dropdown. The router validates every filter.operator
# against this; build_dimension_filter maps the name onto Filter.StringFilter.MatchType.
ALLOWED_MATCH_TYPES = {"EXACT", "CONTAINS", "BEGINS_WITH", "ENDS_WITH", "FULL_REGEXP"}


def build_dimension_filter(filters: list[dict] | None, match: str = "AND"):
    """Build a GA4 dimension FilterExpression from a list of
    {dimension, operator, value, exclude} conditions, or return None when
    there are no conditions.

    Each condition becomes a case-insensitive StringFilter on its dimension;
    `operator` is a GA4 match-type name (EXACT, CONTAINS, BEGINS_WITH,
    ENDS_WITH, FULL_REGEXP) and `exclude` wraps that one condition in a NOT.
    All conditions are collected into a FilterExpressionList placed in
    and_group when `match`=="AND" else or_group.

    Shared by every GA4 query (the headline summary, the trend, each fixed
    breakdown, the dynamic breakdown, and the Explore report) so one filter
    set applies across the whole Traffic section, GA4-style.

    Imports the GA4 filter types lazily — same as the report functions — so
    the module stays importable without google-analytics-data installed."""
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
        # An excluded condition is the same filter wrapped in NOT.
        if f.get("exclude"):
            expr = FilterExpression(not_expression=expr)
        expressions.append(expr)
    group = FilterExpressionList(expressions=expressions)
    if str(match).upper() == "AND":
        return FilterExpression(and_group=group)
    return FilterExpression(or_group=group)


def get_analytics(
    property_id: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> dict:
    """Return GA4 traffic for one property:

        {
          "summary":      {activeUsers, newUsers, avgEngagementSeconds},
          "byDate":       {"rows": [{date, activeUsers, newUsers}, ...]},
          "byChannel":    {"rows": [...], "totals": {...}},
          "byCountry":    {"rows": [...], "totals": {...}},
          "byCity":       {"rows": [...], "totals": {...}},
          "byLandingPage":{"rows": [...], "totals": {...}},
          "byBrowser":    {"rows": [...], "totals": {...}},
          "byDevice":     {"rows": [...], "totals": {...}},
          "byLanguage":   {"rows": [...], "totals": {...}},
        }

    Each breakdown "rows" item is
        {"value": "<dimension>", "activeUsers": .., "newUsers": .., "avgEngagementSeconds": ..}
    and each "totals" is {"activeUsers": .., "newUsers": .., "avgEngagementSeconds": ..}
    for the whole period — which can exceed the sum of the visible rows
    when the table is capped, exactly as GA reports it.

    start_date / end_date may be exact dates ("2026-05-01") or any GA4
    date expression; they default to the last 28 days when not provided.

    `filters` / `match` are an optional shared dimension filter (see
    build_dimension_filter) applied to EVERY report this runs — the headline
    summary, the trend time-series, and each breakdown — so the whole panel
    reflects the same conditions, GA4-style. Omit them for unfiltered traffic.

    Never raises. On an unset property ID or any credential/API failure
    it returns {"configured": False, ...} / {"error": "..."} so callers
    can show a message instead of a stack trace.
    """
    # Default to the last 28 days only when a bound isn't supplied.
    start_date = start_date or "28daysAgo"
    end_date = end_date or "today"

    if not property_id or not str(property_id).strip():
        return {
            "configured": False,
            "message": "Add this project's GA4 property ID to see traffic.",
        }

    # Imported lazily so the rest of the app (and `python -m py_compile`)
    # doesn't hard-depend on google-analytics-data being installed.
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
        client = BetaAnalyticsDataClient.from_service_account_json(GOOGLE_SERVICE_ACCOUNT_JSON)
    except Exception as exc:
        return {"error": f"Could not load the Google service-account key: {exc}"}

    # GA4 wants the property as "properties/<id>"; accept either form.
    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"
    date_ranges = [DateRange(start_date=start_date, end_date=end_date)]
    metrics = [Metric(name=m) for m in _METRICS]
    # The shared dimension filter (None when no conditions) — applied to every
    # request below so the cards, trend and breakdowns all reflect it.
    dimension_filter = build_dimension_filter(filters, match)

    out: dict = {"configured": True}

    # ── Headline summary: the three metrics, no dimension ──
    try:
        request = RunReportRequest(
            property=resource,
            metrics=metrics,
            date_ranges=date_ranges,
            dimension_filter=dimension_filter,
        )
        response = client.run_report(request)
    except Exception as exc:
        return {"error": f"Google Analytics request failed: {exc}"}
    out["summary"] = _summary(response)

    # ── Time-series for the trend chart: by date, ascending ──
    try:
        request = RunReportRequest(
            property=resource,
            dimensions=[Dimension(name="date")],
            metrics=[Metric(name="activeUsers"), Metric(name="newUsers")],
            date_ranges=date_ranges,
            order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
            dimension_filter=dimension_filter,
        )
        response = client.run_report(request)
    except Exception as exc:
        return {"error": f"Google Analytics request failed: {exc}"}
    out["byDate"] = {"rows": _date_rows(response)}

    # ── Dimension breakdowns ──
    for bucket, dimension, limit in _BREAKDOWNS:
        try:
            kwargs = dict(
                property=resource,
                dimensions=[Dimension(name=dimension)],
                metrics=metrics,
                date_ranges=date_ranges,
                metric_aggregations=[MetricAggregation.TOTAL],
                # Order by active users descending so the cap keeps the busiest rows.
                order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
                dimension_filter=dimension_filter,
            )
            if limit is not None:
                kwargs["limit"] = limit
            request = RunReportRequest(**kwargs)
            response = client.run_report(request)
        except Exception as exc:
            return {"error": f"Google Analytics request failed: {exc}"}
        out[bucket] = {
            "rows": _rows(response),
            "totals": _totals(response),
        }
    return out


def get_dimension_breakdown(
    property_id: str | None,
    dimension: str,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> dict:
    """Run ONE GA4 runReport for a single requested `dimension` plus the
    three standard metrics, ordered by activeUsers descending, capped at
    ~25 rows, with metric_aggregations=[TOTAL] for true period totals.

    Returns
        {
          "dimension": "<GA4 name>",
          "rows":   [{label, activeUsers, newUsers, avgEngagement}, ...],
          "totals": {activeUsers, newUsers, avgEngagement},
        }

    where avgEngagement is userEngagementDuration / activeUsers (0 when
    there are no active users), matching the other breakdowns.

    start_date / end_date use the same handling as get_analytics (default
    to the last 28 days; accept any GA4 date expression). `filters` / `match`
    are the optional shared dimension filter (see build_dimension_filter).

    Never raises. GA4 rejects some dimension+metric combinations
    (incompatible scopes) and unknown dimensions; on ANY failure — or an
    unset property / missing credentials — it returns
    {"error": "<message>", "dimension": dimension} so the caller can show a
    friendly message instead of a 500."""
    # Default to the last 28 days only when a bound isn't supplied.
    start_date = start_date or "28daysAgo"
    end_date = end_date or "today"

    if not property_id or not str(property_id).strip():
        return {"error": "This project has no GA4 property ID set.", "dimension": dimension}

    # Imported lazily, same as get_analytics, so the rest of the app (and
    # `python -m py_compile`) doesn't hard-depend on google-analytics-data.
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
        client = BetaAnalyticsDataClient.from_service_account_json(GOOGLE_SERVICE_ACCOUNT_JSON)
    except Exception as exc:
        return {"error": f"Could not load the Google service-account key: {exc}", "dimension": dimension}

    # GA4 wants the property as "properties/<id>"; accept either form.
    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"

    try:
        request = RunReportRequest(
            property=resource,
            dimensions=[Dimension(name=dimension)],
            metrics=[Metric(name=m) for m in _METRICS],
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metric_aggregations=[MetricAggregation.TOTAL],
            # Order by active users descending so the cap keeps the busiest rows.
            order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="activeUsers"), desc=True)],
            limit=_BREAKDOWN_LIMIT,
            dimension_filter=build_dimension_filter(filters, match),
        )
        response = client.run_report(request)
    except Exception as exc:
        # Incompatible dimension+metric scopes, unknown dimension, quota, etc.
        return {"error": f"Google Analytics request failed: {exc}", "dimension": dimension}

    return {
        "dimension": dimension,
        "rows": _breakdown_rows(response),
        "totals": _breakdown_totals(response),
    }


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
    """Run ONE GA4 runReport for an arbitrary combination of dimensions,
    metrics and string filters — the engine behind the "Explore" report
    builder, mirroring GA4's Free-form exploration / the Data API runReport.

    `dimensions` / `metrics` are GA4 API names; `filters` is a list of
    {dimension, operator, value, exclude} where `operator` is a GA4
    StringFilter match-type name (EXACT, CONTAINS, BEGINS_WITH, ENDS_WITH,
    FULL_REGEXP) and `exclude` negates that one condition. `match`
    ("AND"/"OR") joins the conditions. start/end use the same handling as
    get_analytics (default to the last 28 days; accept any GA4 expression).

    Returns
        {
          "dimensions": [...GA4 names, request order...],
          "metrics":    [...GA4 names, request order...],
          "rows":   [{"dims": [<dim values in order>], "metrics": {name: number}}, ...],
          "totals": {name: number},
        }

    where metric values are converted to numbers (int when whole, else a
    rounded float) where possible.

    Never raises. On an unset property / missing credentials / any GA4 API
    error it returns {"error": "<message>"} (HTTP 200 at the router) so the
    frontend shows a friendly message instead of crashing."""
    # Default to the last 28 days only when a bound isn't supplied.
    start = start or "28daysAgo"
    end = end or "today"
    filters = filters or []

    if not property_id or not str(property_id).strip():
        return {"error": "This project has no GA4 property ID set."}

    # Imported lazily, same as the other reports, so the rest of the app (and
    # `python -m py_compile`) doesn't hard-depend on google-analytics-data.
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
        client = BetaAnalyticsDataClient.from_service_account_json(GOOGLE_SERVICE_ACCOUNT_JSON)
    except Exception as exc:
        return {"error": f"Could not load the Google service-account key: {exc}"}

    # GA4 wants the property as "properties/<id>"; accept either form.
    prop = str(property_id).strip()
    resource = prop if prop.startswith("properties/") else f"properties/{prop}"

    # Split the selection into real GA4 metrics and derived (computed) ones. The
    # derived names must NEVER be sent to GA4; instead we ensure their helper
    # real metrics are in the request, auto-adding any the user didn't pick.
    selected = list(metrics)
    derived_selected = [m for m in selected if m in DERIVED_METRICS]
    ga_metrics = [m for m in selected if m not in DERIVED_METRICS]
    for d in derived_selected:
        for h in DERIVED_METRICS[d]["helpers"]:
            if h not in ga_metrics:
                ga_metrics.append(h)  # auto-added helper (omitted from output later)

    try:
        kwargs = dict(
            property=resource,
            dimensions=[Dimension(name=d) for d in dimensions],
            metrics=[Metric(name=m) for m in ga_metrics],
            date_ranges=[DateRange(start_date=start, end_date=end)],
            metric_aggregations=[MetricAggregation.TOTAL],
            limit=limit or 250,
        )
        # Order by the FIRST selected metric, descending, so the cap keeps the
        # busiest rows. A derived first metric orders by its first helper (or
        # activeUsers) instead — never pass a derived name to order_bys.
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

        # Build the dimension filter ONLY when there are conditions to apply
        # (the same shared helper every other Traffic report uses).
        dimension_filter = build_dimension_filter(filters, match)
        if dimension_filter is not None:
            kwargs["dimension_filter"] = dimension_filter

        response = client.run_report(RunReportRequest(**kwargs))
    except Exception as exc:
        # Incompatible dimension/metric scopes, unknown names, bad regex, quota, etc.
        return {"error": f"Google Analytics request failed: {exc}"}

    # Parse the raw report keyed by the REAL metrics sent to GA4, then layer in
    # the derived metrics and trim back to exactly what the user selected.
    report = _custom_report(response, dimensions, ga_metrics)
    return _apply_derived(report, selected, derived_selected)


def _apply_derived(report: dict, selected: list[str], derived_selected: list[str]) -> dict:
    """Compute each derived metric from its helper values — per row (that row's
    helpers) and for the totals row (total numerator / total denominator, NOT an
    average of row ratios) — then re-key rows/totals/metrics to exactly the
    user's `selected` list, in order. Auto-added helper metrics that the user
    didn't select fall away here (they're absent from `selected`)."""
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
        # Keep only the user's selection, in selection order.
        return {name: values.get(name, 0) for name in selected}

    rows = [{"dims": r["dims"], "metrics": trim(compute(r["metrics"]))} for r in report["rows"]]
    totals = trim(compute(report["totals"]))
    return {
        "dimensions": report["dimensions"],
        "metrics": list(selected),
        "rows": rows,
        "totals": totals,
    }


def get_returning_users(
    property_id: str | None,
    start_date: str | None = None,
    end_date: str | None = None,
    filters: list[dict] | None = None,
    match: str = "AND",
) -> int:
    """Returning users for the period, read from the newVsReturning dimension.

    NOT computed as totalUsers - newUsers: in GA4 new + returning users do NOT
    sum to total users (a user can be both within one period), so subtraction
    is wrong. Instead we run a report with dimension newVsReturning and metric
    activeUsers and return the activeUsers of the row whose dimension value is
    "returning" (case-insensitive); 0 if that row is absent.

    `filters` / `match` are the optional shared dimension filter (see
    build_dimension_filter), so the returning-users card reflects the same
    conditions as the rest of the Traffic summary.

    Never raises — any unset property / missing credentials / API error -> 0."""
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
        client = BetaAnalyticsDataClient.from_service_account_json(GOOGLE_SERVICE_ACCOUNT_JSON)
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
    """Parse a runReport response into the report-builder shape:
    rows of {dims: [...], metrics: {name: number}} plus a totals dict."""
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
    """GA4 returns metric values as strings; convert to a number where
    possible (int when whole, else a rounded float), leaving anything
    unparseable as-is."""
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return raw
    return int(f) if f.is_integer() else round(f, 4)


def _breakdown_rows(response) -> list[dict]:
    """Flatten a single-dimension breakdown into
    [{label, activeUsers, newUsers, avgEngagement}, ...]."""
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
    """Read the full-period totals row (metric_aggregations=[TOTAL]) →
    {activeUsers, newUsers, avgEngagement}. Zeros if GA returned no totals."""
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
    """Flatten a breakdown response into
    [{value, activeUsers, newUsers, avgEngagementSeconds}, ...]."""
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
    """Flatten the by-date report into [{date, activeUsers, newUsers}].

    The raw GA date string (YYYYMMDD) is kept as-is; the frontend formats it."""
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
    """The single no-dimension row → {activeUsers, newUsers, avgEngagementSeconds}."""
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
    """Read the full-period totals row (metric_aggregations=[TOTAL]) →
    {activeUsers, newUsers, avgEngagementSeconds}. Zeros if GA returned
    no totals (e.g. an empty report)."""
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
    """Raw string value of the i-th metric on a row (defaults to "0")."""
    return row.metric_values[i].value if i < len(row.metric_values) else "0"


def _avg_engagement(duration: float, active: int) -> float:
    """Average engagement time per active user, in seconds. 0 when there
    are no active users (avoids divide-by-zero)."""
    if not active:
        return 0
    return round(duration / active, 1)


def _as_int(raw: str) -> int:
    """GA4 returns metric values as strings; users are counts."""
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return 0


def _as_float(raw: str) -> float:
    """GA4 returns durations as strings of seconds (may be fractional)."""
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
