"""REPORT BLOCK DOCUMENT BUILDER — turns a frozen report blob into the EDITABLE
block document stored in report_version.content_json.

WHY THIS EXISTS (this slice): generate() used to leave content_json empty ('{}').
Now it builds the FULL templated report as an ordered list of BLOCKS, each SEEDED
from the frozen data_json, and stores it here. The block document is the editable
layer the author will work on in a LATER slice (add/delete/reorder, text edits,
cell edits); THIS slice only renders it read-only.

THE BLOCK DOCUMENT CONTRACT (content_json shape)
------------------------------------------------
{
  "type": "report_document",          # discriminator the frontend branches on
  "schema_version": 1,
  "period_key": "2026-05",
  "period_label": "May 2026",
  "prev_period_key": "2026-04",
  "prev_period_label": "April 2026",
  "prev2_period_key": "2026-03",
  "prev2_period_label": "March 2026",
  "project": {id, name, domain},
  "blocks": [ <block>, ... ]          # ordered; render top-to-bottom
}

Every block carries a STABLE `id` (for the next slice's reorder/edit), a `type`,
and a `title`. Data-bearing blocks additionally carry `available` (false when the
section's source wasn't gathered for this period) + `unavailableReason`, and a
`source` provenance string naming which frozen section seeded them.

DATA vs CONTENT (the product rule). Block VALUES (numbers, table rows, chart
points, backlink URLs) are SEEDED from the immutable data_json at generate time —
they are rendered READ-ONLY and the editor will never let them be changed. Only
narrative prose / titles are editable content. data_json stays the single frozen
source the seeds came from; fork copies BOTH verbatim with no re-fetch.

Block types:
  report_header  {projectName, domain, periodLabel, prevPeriodLabel}
  narrative      {role, title, paragraphs:[str], bullets:[str], editable:true}
  metric_grid    {title, available, unavailableReason, metrics:[metric]}
                 metric = {key,label,type,currentValue,previousValue,deltaValue,available}
  data_table     {title, available, unavailableReason, source, columns:[col], rows:[{cells}]}
                 col = {key,label,kind:'dim'|'metric'|'delta',type}
  chart          {title, available, unavailableReason, source, chartKind, series:[{key,label,type}], points:[{x,...}]}
  backlinks_list {title, available, month, count, items:[{url}]}

`type` on metric/column cells is a blobFormats display category (count / duration /
percent / rank / text) so the read-only renderer formats consistently with the
scalar chip editor.
"""
from .snapshot_service import _label_for

# Bump if the block-document structure changes so a later reader can branch.
DOC_SCHEMA_VERSION = 1


# ── GA4 metric display metadata: api name -> (label, format type) ─────────────
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

# GA4 row-level tables: (section key, title, [dim column labels], [metric api names]).
# Mirrors report_google.GA4_SECTIONS; only the columns we surface in the report.
_GA4_TABLES = (
    ("by_channel", "Traffic by Channel", ["Channel"],
     ["totalUsers", "newUsers", "activeUsers", "engagedSessions", "avgEngagementSeconds"]),
    ("by_country_city", "Users by Country & City", ["Country", "Region", "City"],
     ["activeUsers", "newUsers", "engagedSessions", "engagementRate", "avgEngagementSeconds"]),
    ("by_landing_page", "Top Landing Pages", ["Landing page"],
     ["sessions", "activeUsers", "newUsers", "avgEngagementSeconds"]),
    # Sessions column removed from these four — they show user reach only.
    ("by_device", "Users by Device", ["Device"],
     ["activeUsers", "newUsers"]),
    ("by_browser", "Users by Browser", ["Browser"],
     ["activeUsers", "newUsers"]),
    ("by_operating_system", "Users by Operating System", ["OS"],
     ["activeUsers", "newUsers"]),
    ("by_language", "Users by Language", ["Language"],
     ["activeUsers", "newUsers"]),
)

# Overview metrics (the GA4 "Audience Overview" grid + Progress Summary numbers).
_GA4_OVERVIEW = ("totalUsers", "activeUsers", "newUsers", "returningUsers",
                 "sessions", "engagedSessions", "avgEngagementSeconds")


# ── small helpers ─────────────────────────────────────────────────────────────
def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _delta(cur, prev):
    """current - previous, or None when either side isn't a number."""
    if not _is_num(cur) or not _is_num(prev):
        return None
    value = cur - prev
    return round(value, 4) if isinstance(value, float) else value


def _clean_dim(v):
    """A blank/whitespace GA4 dimension value reads as "(not set)" (matches GA)."""
    return v if (v is not None and str(v).strip()) else "(not set)"


def _int(n):
    """Grouped integer string for templated prose ("4,983"). '—' when not a num."""
    return f"{int(round(n)):,}" if _is_num(n) else "—"


def _metric(key, label, type_, current, previous=None, delta=None):
    """One metric-grid cell. Computes the delta from current/previous when not
    given. `available` is False when there's no current value (section absent)."""
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


# ── section accessors (defensive against absent/None sections) ────────────────
def _ga4_month_sections(ga4, which):
    """which = 'report_month' | 'prior_month' -> that month's per-section dict."""
    if not ga4:
        return {}
    return (ga4.get(which) or {}).get("sections") or {}


def _totals(sections, key):
    return ((sections.get(key) or {}).get("totals")) or {}


# ── block builders ────────────────────────────────────────────────────────────
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
        # Four metrics on very different scales -> normalise each line to its own
        # range so all four are visible (shape over absolute value).
        "normalize": "series",
        "points": points,
    }


def _ga4_users_chart(ga4, present, reason):
    """The GA4 "Users Overview" daily line chart (Active users / New users), seeded
    from the users_trend section. GA4 returns the date dimension as YYYYMMDD; we
    normalise to YYYY-MM-DD and sort ascending so the line reads left→right."""
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
    # THREE months of ranks, ordered oldest -> newest so the eye reads the trend
    # left to right. There is deliberately NO "Change" column: the movement is
    # shown by the green/red row tint instead (report_pdf reads rank_delta off
    # the row cells, which are still populated below).
    # SR_NO is baked 1..N here so the data-driven React table picks it up with no
    # frontend change, but every RENDERER renumbers it over the rows it actually
    # draws (see report_pdf / report_industry) — otherwise deselecting a row in the
    # editor would leave a gap like 1, 2, 4.
    columns = [
        {"key": "sr_no", "label": "Sr No.", "kind": "dim", "type": "text"},
        {"key": "term", "label": "Keyword", "kind": "dim", "type": "text"},
    ]
    if prev2_label:
        columns.append({"key": "previous2_rank", "label": f"Rank · {prev2_label}",
                        "kind": "metric", "type": "rank"})
    columns += [
        {"key": "previous_rank", "label": f"Rank · {prev_label}", "kind": "metric", "type": "rank"},
        {"key": "current_rank", "label": f"Rank · {period_label}", "kind": "metric", "type": "rank"},
    ]
    rows = []
    if present:
        for _i, it in enumerate((kw or {}).get("items", []), 1):
            rows.append({"cells": {
                "sr_no": _i,
                "term": it.get("term"),
                "previous2_rank": it.get("previous2_rank"),
                "current_rank": it.get("current_rank"),
                "previous_rank": it.get("previous_rank"),
                # NOT a displayed column — kept so report_pdf can tint the row
                # and _achievements can name the biggest movers.
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
        # Backlinks come from a plain DB read that always succeeds; an empty month
        # is "no new backlinks", NOT "section unavailable" — so always available.
        "available": True,
        "unavailableReason": None,
        "month": (bl or {}).get("month"),
        "count": count,
        "items": [{"url": it.get("url")} for it in items],
    }


# ── narrative (deterministic mail-merge — NO LLM) ─────────────────────────────
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


# ── entry point ───────────────────────────────────────────────────────────────

_TARGET_FIELDS = [
    ("organic_traffic", "Organic Traffic"),
    ("domain_authority", "Domain Authority"),
    ("keyword_rankings", "Keyword Rankings"),
    ("new_backlinks", "New Backlinks"),
    ("leads", "Leads"),
    ("new_visitors", "New Visitors"),
]


def _next_period(period_key):
    """'2026-06' -> '2026-07'. None when the key isn't YYYY-MM."""
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
    """An EMPTY editable note slot (a narrative block) the SEO team fills in the
    editor. Starts blank so it renders a light placeholder until edited."""
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
    """Editable Targets & Goals grid: six metrics x two columns (Previous Month
    actuals + Current Month Targets). Values are MANUALLY entered by the SEO team
    in the report editor, so they start empty and are NOT seeded from data. Carries
    a free-text `notes` box rendered under the grid. Editable (unlike data blocks)."""
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
        # team-entered values; empty dicts render as em-dash until filled
        "values": {"previous": {}, "current": {}},
    }


def _posts_block(block_id, title, noun, items):
    """A content-links list (blogs / LinkedIn), rendered with the same list
    block as backlinks but with its own noun. Always available; an empty list
    reads as "none added" in the report."""
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
    """Assemble the ordered block document from a gathered report (the dict
    gather() returns). Reads the FROZEN blob + presence flags; seeds every block
    with values from the blob. Pure (no DB, no fetch) so generate() can build it
    right after gather() and freeze it into content_json."""
    blob = gathered["blob"]
    period = blob["period_key"]
    prev_period = blob.get("prev_period_key")
    project = blob.get("project", {}) or {}
    sections = blob.get("sections", {}) or {}
    sources = blob.get("sources", {}) or {}

    period_label = _label_for(period)
    prev_label = _label_for(prev_period) if prev_period else "previous period"
    # Third month back. Blank for reports frozen before the 3-month keyword table
    # existed (no prev2_period_key in the blob) — _keyword_table then omits the
    # column entirely rather than emitting one headed "Rank · ".
    prev2_period = blob.get("prev2_period_key")
    prev2_label = _label_for(prev2_period) if prev2_period else ""
    # The current, in-progress month is FLAGGED (not blocked): its figures cover the
    # month so far and keep changing until it ends and Google finalises the data.
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

    # GA4 breakdown tables, built once and placed individually so note slots can
    # be interleaved and the section order matches the client-facing layout.
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
        # 1. Progress Summary
        _progress_summary(period_label, prev_label, ga4, ga4_present, moz, moz_present, bl_count),
        # 2. Key Metrics + Achievements
        _key_metrics_grid(ga4, ga4_present, reason("ga4"), moz, moz_present, reason("moz"), bl_count),
        _achievements(kw, kw_present, period_label),
        # 3. Domain Authority & Backlinks
        _moz_grid(moz, moz_present, reason("moz")),
        # 4. GA4 Overview: notes, numbers, graph, graph notes
        _notes_slot("ga4-overview-notes", "GA4 Notes"),
        _ga4_overview_grid(ga4, ga4_present, reason("ga4")),
        _ga4_users_chart(ga4, ga4_present, reason("ga4")),
        _notes_slot("ga4-graph-notes", "Graph Notes"),
        # Traffic by Channel: notes (shown left of the donut) + table
        _notes_slot("ga4-channel-notes", "Traffic by Channel Notes"),
        ga4_tbl["by_channel"],
        # 5. Users by Country & City: notes + list
        _notes_slot("ga4-cities-notes", "Cities & Countries Notes"),
        ga4_tbl["by_country_city"],
        # 6. Top Landing Pages: notes + list
        _notes_slot("ga4-landing-notes", "Landing Pages Notes"),
        ga4_tbl["by_landing_page"],
        # 7. Detailed Traffic Summary: device / browser / OS / language
        ga4_tbl["by_device"],
        ga4_tbl["by_browser"],
        ga4_tbl["by_operating_system"],
        ga4_tbl["by_language"],
        # 8. Search Console: notes, numbers, graph
        _notes_slot("gsc-notes", "Search Console Notes"),
        _gsc_grid(gsc, gsc_present, reason("gsc")),
        _gsc_chart(gsc, gsc_present, reason("gsc")),
        # 9-12
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
    """Build the block document from a FROZEN data_json dict alone (re-wrapping it
    in the minimal `gathered` shape build_document expects). Pure, read-only — used
    by the editor's "re-add a removed template section" feature to re-derive the
    canonical template blocks straight from the immutable frozen data. data_json is
    never modified."""
    if not data:
        return {"type": "report_document", "schema_version": DOC_SCHEMA_VERSION, "blocks": []}
    return build_document({"blob": data})


def _key_metrics_grid(ga4, ga4_present, ga4_reason, moz, moz_present, moz_reason, bl_count):
    """The headline prev-vs-current scalar cards (sessions / users / new /
    returning / DA / new backlinks). Available when EITHER GA4 or Moz is present;
    individual cards flag themselves absent via their None currentValue."""
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
        # New backlinks this month: a single-month count from the backlinks table,
        # so there's no prior value / delta.
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
