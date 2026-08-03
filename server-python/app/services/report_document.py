from .snapshot_service import _label_for

DOC_SCHEMA_VERSION = 1


_GA4_METRIC_META = {
    "activeUsers": ("Active users", "count"),
    "newUsers": ("New users", "count"),
    "totalUsers": ("Total users", "count"),
    "returningUsers": ("Returning users", "count"),
    "sessions": ("Sessions", "count"),
    "engagedSessions": ("Engaged sessions", "count"),
    "userEngagementDuration": ("Engagement time", "duration"),
    "avgEngagementSeconds": ("Avg. engagement", "duration"),
    "engagementRate": ("Engagement rate", "percent"),
    "screenPageViews": ("Page views", "count"),
}

_GA4_TABLES = (
    ("by_channel", "Traffic by Channel", ["Channel"],
     ["totalUsers", "newUsers", "activeUsers", "engagedSessions", "avgEngagementSeconds"]),
    ("by_country_city", "Users by Country & City", ["Country", "Region", "City"],
     ["activeUsers", "newUsers", "engagedSessions", "engagementRate", "avgEngagementSeconds"]),
    ("by_landing_page", "Top Landing Pages", ["Landing page"],
     ["sessions", "activeUsers", "newUsers", "avgEngagementSeconds"]),
    ("by_device", "Users by Device", ["Device"],
     ["activeUsers", "newUsers"]),
    ("by_browser", "Users by Browser", ["Browser"],
     ["activeUsers", "newUsers"]),
    ("by_operating_system", "Users by Operating System", ["OS"],
     ["activeUsers", "newUsers"]),
    ("by_language", "Users by Language", ["Language"],
     ["activeUsers", "newUsers"]),
)

_GA4_OVERVIEW = ("totalUsers", "activeUsers", "newUsers", "returningUsers",
                 "sessions", "engagedSessions", "avgEngagementSeconds")


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _delta(cur, prev):
    if not _is_num(cur) or not _is_num(prev):
        return None
    value = cur - prev
    return round(value, 4) if isinstance(value, float) else value


def _clean_dim(v):
    return v if (v is not None and str(v).strip()) else "(not set)"


def _int(n):
    return f"{int(round(n)):,}" if _is_num(n) else "—"


def _metric(key, label, type_, current, previous=None, delta=None):
    if delta is None:
        delta = _delta(current, previous)
    return {
        "key": key,
        "label": label,
        "type": type_,
        "currentValue": current,
        "previousValue": previous,
        "deltaValue": delta,
        "available": current is not None,
    }


def _ga4_month_sections(ga4, which):
    if not ga4:
        return {}
    return (ga4.get(which) or {}).get("sections") or {}


def _totals(sections, key):
    return ((sections.get(key) or {}).get("totals")) or {}


def _ga4_overview_grid(ga4, present, reason):
    cur = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
    prev = _totals(_ga4_month_sections(ga4, "prior_month"), "users_overview")
    metrics = []
    for mk in _GA4_OVERVIEW:
        label, type_ = _GA4_METRIC_META.get(mk, (mk, "count"))
        metrics.append(_metric(mk, label, type_, cur.get(mk), prev.get(mk)))
    return {
        "id": "ga4-overview",
        "type": "metric_grid",
        "title": "GA4 — Audience Overview",
        "source": "ga4.users_overview",
        "available": present,
        "unavailableReason": None if present else reason,
        "metrics": metrics,
    }


def _ga4_table(key, title, dim_labels, metric_keys, ga4, present, reason):
    columns = []
    for i, dim_label in enumerate(dim_labels):
        columns.append({"key": f"dim{i}", "label": dim_label, "kind": "dim", "type": "text"})
    for mk in metric_keys:
        label, type_ = _GA4_METRIC_META.get(mk, (mk, "count"))
        columns.append({"key": mk, "label": label, "kind": "metric", "type": type_})

    rows = []
    if present:
        sec = _ga4_month_sections(ga4, "report_month").get(key) or {}
        for r in sec.get("rows", []):
            dims = r.get("dims", []) or []
            mvals = r.get("metrics", {}) or {}
            cells = {}
            for i in range(len(dim_labels)):
                cells[f"dim{i}"] = _clean_dim(dims[i] if i < len(dims) else None)
            for mk in metric_keys:
                cells[mk] = mvals.get(mk)
            rows.append({"cells": cells})
    return {
        "id": f"ga4-{key}",
        "type": "data_table",
        "title": title,
        "source": f"ga4.{key}",
        "available": present,
        "unavailableReason": None if present else reason,
        "columns": columns,
        "rows": rows,
    }


def _gsc_grid(gsc, present, reason):
    cur = (gsc or {}).get("report_month", {}).get("totals", {}) if gsc else {}
    prev = (gsc or {}).get("prior_month", {}).get("totals", {}) if gsc else {}
    metrics = [
        _metric("clicks", "Clicks", "count", cur.get("clicks"), prev.get("clicks")),
        _metric("impressions", "Impressions", "count", cur.get("impressions"), prev.get("impressions")),
        _metric("ctr", "CTR", "percent", cur.get("ctr"), prev.get("ctr")),
        _metric("position", "Avg. position", "rank", cur.get("position"), prev.get("position")),
    ]
    return {
        "id": "gsc-overview",
        "type": "metric_grid",
        "title": "Search Console — Performance",
        "source": "gsc.totals",
        "available": present,
        "unavailableReason": None if present else reason,
        "metrics": metrics,
    }


def _gsc_chart(gsc, present, reason):
    trend = (gsc or {}).get("report_month", {}).get("trend", []) if gsc else []
    points = [
        {"x": (r.get("date") or ""), "clicks": r.get("clicks"), "impressions": r.get("impressions"),
         "ctr": r.get("ctr"), "position": r.get("position")}
        for r in trend
    ]
    return {
        "id": "gsc-trend",
        "type": "chart",
        "title": "Search Console — Daily Trend",
        "source": "gsc.trend",
        "chartKind": "line",
        "available": present and bool(points),
        "unavailableReason": None if (present and points) else (reason or "no daily trend for this period"),
        "series": [
            {"key": "clicks", "label": "Clicks", "type": "count"},
            {"key": "impressions", "label": "Impressions", "type": "count"},
            {"key": "ctr", "label": "CTR", "type": "percent"},
            {"key": "position", "label": "Avg. position", "type": "rank"},
        ],
        "normalize": "series",
        "points": points,
    }


def _ga4_users_chart(ga4, present, reason):
    sec = _ga4_month_sections(ga4, "report_month").get("users_trend") or {}
    rows = sec.get("rows", []) or []

    def _fmt_date(d):
        s = str(d or "")
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else s

    points = []
    for r in rows:
        dims = r.get("dims", []) or []
        mvals = r.get("metrics", {}) or {}
        points.append({
            "x": _fmt_date(dims[0] if dims else ""),
            "activeUsers": mvals.get("activeUsers"),
            "newUsers": mvals.get("newUsers"),
        })
    points.sort(key=lambda p: p["x"])
    return {
        "id": "ga4-users-trend",
        "type": "chart",
        "title": "GA4 — Users Overview",
        "source": "ga4.users_trend",
        "chartKind": "line",
        "available": present and bool(points),
        "unavailableReason": None if (present and points) else (reason or "no daily users for this period"),
        "series": [
            {"key": "activeUsers", "label": "Active users", "type": "count"},
            {"key": "newUsers", "label": "New users", "type": "count"},
        ],
        "points": points,
    }


def _moz_grid(moz, present, reason):
    deltas = (moz or {}).get("deltas", {}) if moz else {}

    def cell(key, label):
        cur = (moz or {}).get(key) if moz else None
        d = deltas.get(key)
        prev = (cur - d) if (_is_num(cur) and _is_num(d)) else None
        return _metric(key, label, "count", cur, prev, d)

    return {
        "id": "moz-overview",
        "type": "metric_grid",
        "title": "Domain Authority & Backlinks (Moz)",
        "source": "moz",
        "available": present,
        "unavailableReason": None if present else reason,
        "metrics": [
            cell("domain_authority", "Domain Authority"),
            cell("linking_domains", "Linking domains"),
            cell("inbound_links", "Total backlinks"),
        ],
    }


def _keyword_table(kw, present, reason, period_label, prev_label, prev2_label=""):
    columns = [{"key": "term", "label": "Keyword", "kind": "dim", "type": "text"}]
    if prev2_label:
        columns.append({"key": "previous2_rank", "label": f"Rank · {prev2_label}",
                        "kind": "metric", "type": "rank"})
    columns += [
        {"key": "previous_rank", "label": f"Rank · {prev_label}", "kind": "metric", "type": "rank"},
        {"key": "current_rank", "label": f"Rank · {period_label}", "kind": "metric", "type": "rank"},
    ]
    rows = []
    if present:
        for it in (kw or {}).get("items", []):
            rows.append({"cells": {
                "term": it.get("term"),
                "previous2_rank": it.get("previous2_rank"),
                "current_rank": it.get("current_rank"),
                "previous_rank": it.get("previous_rank"),
                "rank_delta": it.get("rank_delta"),
            }})
    return {
        "id": "keywords",
        "type": "data_table",
        "title": "Keyword Rankings",
        "source": "keywords",
        "available": present,
        "unavailableReason": None if present else reason,
        "columns": columns,
        "rows": rows,
    }


def _backlinks_block(bl):
    items = (bl or {}).get("items", []) or []
    count = (bl or {}).get("count", len(items))
    return {
        "id": "backlinks",
        "type": "backlinks_list",
        "title": "New Backlinks",
        "source": "backlinks",
        "available": True,
        "unavailableReason": None,
        "month": (bl or {}).get("month"),
        "count": count,
        "items": [{"url": it.get("url")} for it in items],
    }


def _progress_summary(period_label, prev_label, ga4, ga4_present, moz, moz_present, bl_count):
    cur = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
    prev = _totals(_ga4_month_sections(ga4, "prior_month"), "users_overview")
    paragraphs = []
    if ga4_present and cur:
        s = (f"In {period_label}, the site recorded {_int(cur.get('sessions'))} sessions "
             f"from {_int(cur.get('totalUsers'))} total users "
             f"({_int(cur.get('newUsers'))} new, {_int(cur.get('returningUsers'))} returning).")
        if prev.get("sessions") is not None:
            s += f" The prior month ({prev_label}) saw {_int(prev.get('sessions'))} sessions."
        paragraphs.append(s)
    else:
        paragraphs.append(f"Google Analytics traffic is not available for {period_label}.")
    if moz_present and moz:
        paragraphs.append(
            f"Domain Authority stands at {_int(moz.get('domain_authority'))}, "
            f"with {_int(moz.get('inbound_links'))} total backlinks tracked.")
    if bl_count:
        paragraphs.append(f"{bl_count} new backlink{'s' if bl_count != 1 else ''} "
                          f"were recorded during {period_label}.")
    return {
        "id": "progress-summary",
        "type": "narrative",
        "role": "progress_summary",
        "title": "Progress Summary",
        "paragraphs": paragraphs,
        "bullets": [],
        "editable": True,
    }


def _achievements(kw, kw_present, period_label):
    bullets = []
    if kw_present:
        improved = [it for it in (kw or {}).get("items", [])
                    if _is_num(it.get("rank_delta")) and it["rank_delta"] < 0]
        improved.sort(key=lambda it: it["rank_delta"])
        for it in improved[:5]:
            places = abs(it["rank_delta"])
            bullets.append(
                f"“{it.get('term')}” improved {places} place{'s' if places != 1 else ''} "
                f"to position #{it.get('current_rank')}.")
    paragraphs = ([] if bullets else
                  [f"Key wins for {period_label} will be summarised here."])
    return {
        "id": "achievements",
        "type": "narrative",
        "role": "achievements",
        "title": "Achievements",
        "paragraphs": paragraphs,
        "bullets": bullets,
        "editable": True,
    }


def _static_narrative(block_id, role, title, paragraphs):
    return {
        "id": block_id,
        "type": "narrative",
        "role": role,
        "title": title,
        "paragraphs": paragraphs,
        "bullets": [],
        "editable": True,
    }


_TARGET_FIELDS = [
    ("organic_traffic", "Organic Traffic"),
    ("domain_authority", "Domain Authority"),
    ("keyword_rankings", "Keyword Rankings"),
    ("new_backlinks", "New Backlinks"),
    ("leads", "Leads"),
    ("new_visitors", "New Visitors"),
]


def _next_period(period_key):
    try:
        y_s, m_s = str(period_key).split("-")
        y, m = int(y_s), int(m_s)
        m += 1
        if m > 12:
            m, y = 1, y + 1
        return f"{y:04d}-{m:02d}"
    except Exception:
        return None


def _notes_slot(block_id, title):
    return {
        "id": block_id,
        "type": "narrative",
        "role": "notes",
        "title": title,
        "paragraphs": [],
        "bullets": [],
        "editable": True,
    }


def _targets_grid_block(period_key, period_label):
    nxt = _next_period(period_key)
    next_label = _label_for(nxt) if nxt else "next month"
    return {
        "id": "targets",
        "type": "targets_grid",
        "role": "targets",
        "title": "Targets & Goals",
        "editable": True,
        "columns": [
            {"key": "previous", "label": f"Previous Month ({period_label})"},
            {"key": "current", "label": f"Current Month Targets ({next_label})"},
        ],
        "fields": [{"key": k, "label": lbl} for k, lbl in _TARGET_FIELDS],
        "values": {"previous": {}, "current": {}},
    }


def _posts_block(block_id, title, noun, items):
    items = items or []
    return {
        "id": block_id,
        "type": "backlinks_list",
        "title": title,
        "source": "posts",
        "available": True,
        "unavailableReason": None,
        "noun": noun,
        "count": len(items),
        "items": [{"url": (it or {}).get("url"), "title": (it or {}).get("title")} for it in items],
    }


def build_document(gathered: dict) -> dict:
    blob = gathered["blob"]
    period = blob["period_key"]
    prev_period = blob.get("prev_period_key")
    project = blob.get("project", {}) or {}
    sections = blob.get("sections", {}) or {}
    sources = blob.get("sources", {}) or {}

    period_label = _label_for(period)
    prev_label = _label_for(prev_period) if prev_period else "previous period"
    prev2_period = blob.get("prev2_period_key")
    prev2_label = _label_for(prev2_period) if prev2_period else ""
    period_in_progress = bool(blob.get("period_in_progress"))
    maturing_notice = (
        f"{period_label} is still in progress — figures cover the month so far and "
        "will keep changing until the month ends and Google finalises the data."
    ) if period_in_progress else None

    def present(name):
        return bool((sources.get(name) or {}).get("present"))

    def reason(name):
        return (sources.get(name) or {}).get("reason") or "not available for this period"

    ga4 = sections.get("ga4")
    gsc = sections.get("gsc")
    moz = sections.get("moz")
    kw = sections.get("keywords")
    bl = sections.get("backlinks") or {}
    posts = sections.get("posts") or {}

    ga4_present = present("ga4")
    gsc_present = present("gsc")
    moz_present = present("moz")
    kw_present = present("keywords")
    bl_count = bl.get("count", 0)

    ga4_tbl = {
        key: _ga4_table(key, title, dim_labels, metric_keys, ga4, ga4_present, reason("ga4"))
        for key, title, dim_labels, metric_keys in _GA4_TABLES
    }

    blocks = [
        {
            "id": "header",
            "type": "report_header",
            "title": "SEO Performance Report",
            "projectName": project.get("name"),
            "domain": project.get("domain"),
            "periodLabel": period_label,
            "prevPeriodLabel": prev_label,
            "maturing": period_in_progress,
            "maturingNotice": maturing_notice,
        },
        _progress_summary(period_label, prev_label, ga4, ga4_present, moz, moz_present, bl_count),
        _key_metrics_grid(ga4, ga4_present, reason("ga4"), moz, moz_present, reason("moz"), bl_count),
        _achievements(kw, kw_present, period_label),
        _moz_grid(moz, moz_present, reason("moz")),
        _notes_slot("ga4-overview-notes", "GA4 Notes"),
        _ga4_overview_grid(ga4, ga4_present, reason("ga4")),
        _ga4_users_chart(ga4, ga4_present, reason("ga4")),
        _notes_slot("ga4-graph-notes", "Graph Notes"),
        _notes_slot("ga4-channel-notes", "Traffic by Channel Notes"),
        ga4_tbl["by_channel"],
        _notes_slot("ga4-cities-notes", "Cities & Countries Notes"),
        ga4_tbl["by_country_city"],
        _notes_slot("ga4-landing-notes", "Landing Pages Notes"),
        ga4_tbl["by_landing_page"],
        ga4_tbl["by_device"],
        ga4_tbl["by_browser"],
        ga4_tbl["by_operating_system"],
        ga4_tbl["by_language"],
        _notes_slot("gsc-notes", "Search Console Notes"),
        _gsc_grid(gsc, gsc_present, reason("gsc")),
        _gsc_chart(gsc, gsc_present, reason("gsc")),
        _keyword_table(kw, kw_present, reason("keywords"), period_label, prev_label, prev2_label),
        _backlinks_block(bl),
        _posts_block("posts-blogs", "Blog Posts", "blog post", posts.get("blogs")),
        _posts_block("posts-linkedin", "LinkedIn Posts", "LinkedIn post", posts.get("linkedin")),
        _targets_grid_block(period, period_label),
        _notes_slot("targets-notes", "Notes"),
        _static_narrative(
            "strategy", "strategy", "Strategy & Notes",
            ["Planned strategy, content, and outreach notes for the coming period "
             "will be captured here."]),
    ]

    return {
        "type": "report_document",
        "schema_version": DOC_SCHEMA_VERSION,
        "period_key": period,
        "period_label": period_label,
        "prev_period_key": prev_period,
        "prev_period_label": prev_label,
        "prev2_period_key": prev2_period,
        "prev2_period_label": prev2_label,
        "period_in_progress": period_in_progress,
        "project": {"id": project.get("id"), "name": project.get("name"), "domain": project.get("domain")},
        "blocks": blocks,
    }


def build_document_from_data(data: dict | None) -> dict:
    if not data:
        return {"type": "report_document", "schema_version": DOC_SCHEMA_VERSION, "blocks": []}
    return build_document({"blob": data})


def _key_metrics_grid(ga4, ga4_present, ga4_reason, moz, moz_present, moz_reason, bl_count):
    cur = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
    prev = _totals(_ga4_month_sections(ga4, "prior_month"), "users_overview")
    moz_deltas = (moz or {}).get("deltas", {}) if moz else {}
    da = (moz or {}).get("domain_authority") if moz else None
    da_delta = moz_deltas.get("domain_authority")
    da_prev = (da - da_delta) if (_is_num(da) and _is_num(da_delta)) else None

    metrics = [
        _metric("sessions", "Sessions", "count", cur.get("sessions"), prev.get("sessions")),
        _metric("totalUsers", "Total users", "count", cur.get("totalUsers"), prev.get("totalUsers")),
        _metric("newUsers", "New users", "count", cur.get("newUsers"), prev.get("newUsers")),
        _metric("returningUsers", "Returning users", "count", cur.get("returningUsers"), prev.get("returningUsers")),
        _metric("domain_authority", "Domain Authority", "count", da, da_prev, da_delta),
        _metric("new_backlinks", "New backlinks", "count", bl_count, None, None),
    ]
    available = ga4_present or moz_present
    unavailable_reason = None if available else (ga4_reason or moz_reason)
    return {
        "id": "key-metrics",
        "type": "metric_grid",
        "title": "Key Metrics",
        "source": "summary",
        "available": available,
        "unavailableReason": unavailable_reason,
        "metrics": metrics,
    }
