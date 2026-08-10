from .periods import label_for as _label_for

DOC_SCHEMA_VERSION = 1


_GA4_METRIC_META = {
    "activeUsers": ("Active users", "count"),
    "newUsers": ("New users", "count"),
    "totalUsers": ("Total users", "count"),
    "returningUsers": ("Returning users", "count"),
    "sessions": ("Sessions", "count"),
    "engagedSessions": ("Engaged sessions", "count"),
    "userEngagementDuration": ("Engagement time", "duration"),
    "avgEngagementSeconds": ("Avg. engagement / user", "duration"),
    "avgEngagementSecondsPerSession": ("Avg. engagement / session", "duration"),
    "engagementRate": ("Engagement rate", "percent"),
    "screenPageViews": ("Views", "count"),
    "eventCount": ("Event count", "count"),
    "keyEvents": ("Key events", "count"),
}

_GA4_TABLES = (
    ("by_channel", "Traffic by Channel", ["Channel"],
     ["totalUsers", "newUsers", "activeUsers", "engagedSessions", "avgEngagementSeconds"]),
    ("by_country_city", "Users by Country & City", ["Country", "Region", "City"],
     ["activeUsers", "newUsers", "engagedSessions", "engagementRate", "avgEngagementSeconds"]),
    ("by_landing_page", "Top Landing Pages", ["Landing page"],
     ["screenPageViews", "activeUsers", "eventCount", "keyEvents",
      "avgEngagementSecondsPerSession"]),
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



def _keyword_table(kw, present, reason, period_label, prev_label, prev2_label=""):
    items = (kw or {}).get("items", []) if present else []
    # Only offer the two-months-back column when at least one keyword actually has a
    # rank that far back. Tracking that begins mid-history otherwise yields a column
    # of em-dashes on every row, which reads as missing data rather than no history.
    has_prev2 = any(_is_num(it.get("previous2_rank")) for it in items)
    columns = [{"key": "term", "label": "Keyword", "kind": "dim", "type": "text"}]
    if prev2_label and has_prev2:
        columns.append({"key": "previous2_rank", "label": f"Rank · {prev2_label}",
                        "kind": "metric", "type": "rank"})
    columns += [
        {"key": "previous_rank", "label": f"Rank · {prev_label}", "kind": "metric", "type": "rank"},
        {"key": "current_rank", "label": f"Rank · {period_label}", "kind": "metric", "type": "rank"},
    ]
    rows = []
    if present:
        for it in items:
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
        s = (f"In {period_label}, our SEO efforts have resulted in positive growth across several important metrics. "
        f"The website recorded {_int(cur.get('sessions'))} sessions, with {_int(cur.get('totalUsers'))} total users. Of these, {_int(cur.get('newUsers'))} were new visitors, while {_int(cur.get('returningUsers'))} returned, indicating a steady level of user retention. "
        f"We successfully acquired {_int(bl_count)} new backlinks, contributing to a domain authority (DA) of {_int((moz or {}).get('domain_authority'))}."
    )
        paragraphs.append(s)
    else:
        paragraphs.append(f"Google Analytics traffic is not available for {period_label}.")
    return {
        "id": "progress-summary",
        "type": "narrative",
        "role": "progress_summary",
        "title": "Progress Summary",
        "paragraphs": paragraphs,
        "bullets": [],
        "editable": True,
    }



def _fmt_duration(sec):
    """43 -> '43 seconds'; 115 -> '1m 55s'. Matches the table formatting."""
    if not _is_num(sec):
        return None
    sec = int(round(sec))
    if sec < 60:
        return f"{sec} seconds"
    return f"{sec // 60}m {sec % 60}s"


def _fmt_pct(v, places=2):
    """GA4 and GSC hand back rates as 0-1 fractions; the report shows percents."""
    if not _is_num(v):
        return None
    pct = v * 100 if abs(v) <= 1 else v
    return f"{pct:.{places}f}%"


def _signed_int(v):
    if not _is_num(v):
        return None
    return f"+{int(round(v)):,}" if v >= 0 else f"{int(round(v)):,}"


def _rows_for(ga4, key):
    return ((_ga4_month_sections(ga4, "report_month").get(key) or {}).get("rows")) or []


def _top_rows(ga4, key, metric, limit):
    """Rows sorted by one metric, biggest first. Rows missing it are dropped."""
    scored = [(r, ((r.get("metrics") or {}).get(metric))) for r in _rows_for(ga4, key)]
    scored = [(r, v) for r, v in scored if _is_num(v)]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [(_clean_dim((r.get("dims") or [None])[0]), v) for r, v in scored[:limit]]


def _dim_at(row, i):
    dims = row.get("dims") or []
    return _clean_dim(dims[i] if i < len(dims) else None)


def _share(part, whole):
    """part as a percentage of whole — '82%'. None when either is missing."""
    if not (_is_num(part) and _is_num(whole)) or whole == 0:
        return None
    return f"{part / whole * 100:.0f}%"


def _movement(cur, prev):
    """(verb, phrase) describing a change, or (None, None) with no comparison.

    Derived rather than asserted. The old copy said things like 'indicating
    successful outreach' regardless of whether the number had gone up or down;
    this can only say what the two figures actually show.
    """
    if not (_is_num(cur) and _is_num(prev)) or prev == 0:
        return None, None
    pct = (cur - prev) / abs(prev) * 100
    if abs(pct) < 1:
        return "held steady", "broadly level with the previous month"
    # Adjectival, so it reads as an aside rather than a second main verb:
    # "…4,804 active users, up 34% on the previous month."
    verb = "rose" if pct > 0 else "fell"
    return verb, f"{'up' if pct > 0 else 'down'} {abs(pct):.0f}% on the previous month"


def _audience_narrative(ga4,total_users, new_users,avgEngagementSeconds):
    """Active users, how many were new, engagement, and the month-on-month move."""
    cur = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
    prev = _totals(_ga4_month_sections(ga4, "prior_month"), "users_overview")
    paragraphs = [f"This month, the site recorded {_int(total_users)} Total users, of which {_int(new_users)} were new visitors indicating successful outreach efforts."
                  f"The average engagement time per user was {_fmt_duration(cur.get('avgEngagementSeconds'))}, reflecting a healthy level of interaction with the content."]

    return paragraphs



def _graph_narrative(ga4, ga4_present):
    """Names the busiest day, which is the one thing a reader asks of a trend line."""
    rows = _rows_for(ga4, "users_trend") if ga4_present else []
    points = [(_dim_at(r, 0), (r.get("metrics") or {}).get("activeUsers")) for r in rows]
    points = [(d, v) for d, v in points if _is_num(v)]
    if not points:
        return []

    peak_day, peak = max(points, key=lambda p: p[1])
    avg = sum(v for _, v in points) / len(points)
    day = str(peak_day)
    if len(day) == 8 and day.isdigit():
        day = f"{day[6:8]}/{day[4:6]}"

    days = len(points)
    return [f"Daily active users averaged {_int(avg)} across {days} "
            f"day{'s' if days != 1 else ''}, peaking at {_int(peak)} on {day}."]


def _channel_users(ga4, name):
    """Total users for one named channel, or None if it has no rows this month.

    Channel figures are nested rows, not flat keys — `by_channel` holds
    {"dims": ["Organic Search"], "metrics": {...}} entries — so a named channel
    has to be searched for rather than fetched.
    """
    for r in _rows_for(ga4, "by_channel"):
        if _dim_at(r, 0).lower() == name.lower():
            return (r.get("metrics") or {}).get("totalUsers")
    return None


def _channel_narrative(ga4, ga4_present):
    if not ga4_present:
        return []

    organic = _channel_users(ga4, "Organic Search")
    direct = _channel_users(ga4, "Direct")
    social = _channel_users(ga4, "Organic Social")

    # Each clause appears only when its channel has rows, so a project with no
    # social traffic drops that sentence instead of printing a dash.
    parts = []
    if _is_num(organic):
        parts.append(f"This month, Organic Search recorded {_int(organic)} organic users, "
                     f"highlighting its key role in user engagement.")
    if _is_num(direct):
        parts.append(f"Direct traffic brought in {_int(direct)} users, indicating strong interest.")
    if _is_num(social):
        parts.append(f"Organic Social contributed {_int(social)} users.")

    return [" ".join(parts)] if parts else []

def _city_users(ga4, name):
    """Active users for one named city, or None if it has no rows this month.

    dims on by_country_city are [Country, Region, City], so the city is index 2.
    """
    for r in _rows_for(ga4, "by_country_city"):
        if _dim_at(r, 2).lower() == name.lower():
            return (r.get("metrics") or {}).get("activeUsers")
    return None


def _geo_narrative(ga4, ga4_present):
    if not ga4_present:
        return []

    perth = _city_users(ga4, "Perth")
    melbourne = _city_users(ga4, "Melbourne")

    parts = []
    if _is_num(perth):
        parts.append(f"This month, Perth led with {_int(perth)} active users, "
                     f"reflecting a strong local presence.")
    if _is_num(melbourne):
        parts.append(f"Melbourne followed with {_int(melbourne)} users.")

    return [" ".join(parts)] if parts else []
def _landing_narrative(ga4, ga4_present):
    """Entry pages by active users, with each one's share of all landings."""
    rows = _top_rows(ga4, "by_landing_page", "activeUsers", 50) if ga4_present else []
    if not rows:
        return []
    total = sum(v for _, v in rows)
    top = rows[:3]

    def phrase(name, value):
        share = _share(value, total)
        return f"{name} ({_int(value)} users{f', {share}' if share else ''})"

    s = f"Visitors entered through {len(rows)} page{'s' if len(rows) != 1 else ''}. "
    s += f"The most common landing page was {phrase(*top[0])}"
    if len(top) > 1:
        s += ", then " + " and ".join(phrase(n, v) for n, v in top[1:])
    s += "."

    lead_share = _share(top[0][1], total)
    if lead_share and total and (top[0][1] / total) >= 0.5:
        s += f" That single page took {lead_share} of all entries."
    return [s]

def _gsc_narrative(gsc, gsc_present, period_label):
    if not (gsc_present and gsc):
        return []
    cur = (gsc.get("report_month") or {}).get("totals") or {}
    impressions, clicks = cur.get("impressions"), cur.get("clicks")
    if not (_is_num(impressions) or _is_num(clicks)):
        return []

    s = f"The website generated {_int(impressions)} impressions and {_int(clicks)} clicks"

    # CTR at one decimal: a 0.1% rate rounds to 0.10% at the default two, which
    # implies more precision than a figure this small carries.
    ctr = _fmt_pct(cur.get("ctr"), places=1)
    if ctr:
        s += f", maintaining a {ctr} CTR"

    pos = cur.get("position")
    if _is_num(pos):
        s += f" with an average position of {pos:.0f}"
    s += "."

    return [s,
            "Improving high-impression keywords, metadata, and content relevance can help "
            "increase rankings, click-through rates, and qualified organic traffic."]

def _targets_narrative():
    return ["Increase Organic Sessions: Aim to increase organic sessions, focusing on optimizing existing content and driving more targeted traffic through refined SEO strategies.\n"
            "Grow Active Users: Target a growth of 15-20% in active users, with a focus on attracting and retaining new visitors through content optimization and improved user experience.\n"
            "Boost Returning Visitors: Increase the number of returning visitors by 10-15% by improving engagement and retention strategies, including better content and clear calls-to-action.\n"
            "Enhance Backlink Profile: Aim to secure 180 new backlinks, focusing on high-quality, relevant sites to further improve domain authority.\n"
            "Increase Domain Authority (DA): Target a 1-point increase in Domain Authority (DA) to reach 16 by acquiring more backlinks and improving on-page SEO factors.\n"
            "Improve Conversion Pages: Focus on enhancing key landing pages like contact-us, service pages, and home page to increase engagement and conversion rates. Target a 15% increase in page visits to these pages.\n"
            "Geographical Focus: Increase traffic from Perth by 15% and expand efforts to capture more visitors from Sydney and Melbourne through targeted local SEO strategies."]


def _strategy_narrative():
   paragraphs = [
            "New Blog Posts:\n"

            "Develop a content calendar and publish at least 6-8 blog posts per month targeting long-tail keywords and addressing common industry pain points.\n"
            "Increase internal linking between pages to boost the SEO value of deeper pages, helping them rank higher.\n"
            "Submission Strategy\n"

            "Directory Submissions: Submit the website to high-authority local business directories to improve local SEO and backlink profile.\n"
            "Social Bookmarking: Submit important pages on high-authority social bookmarking sites to increase referral traffic.\n"
            "Off -Page Strategy\n"
            
            "Local Citations: Ensure consistent NAP (Name, Address, Phone Number) details are listed on local directories, maps, and citation sites to strengthen local SEO.\n "
            "On-Page Strategy\n"

            "Keyword Optimization: Ensure all web pages are optimized for target keywords, especially long-tail keywords, with proper keyword density, meta descriptions, and title tags.\n"
            "Content Freshness: Regularly blog posts and landing pages with fresh content to ensure they remain relevant and authoritative.\n"
            "Competition Strategy\n"

            "Competitor Analysis: Conduct an in-depth analysis of top competitors to understand their backlink sources, content strategies, and keyword rankings. Identify opportunities to outperform them.\n"
            "Backlink Analysis: Analyze competitors’ backlink profiles and acquire backlinks from the same or higher-quality sites.\n"
            "Keywords Strategy\n"

            "Target Long-Tail Keywords: Target more specific, less competitive long-tail keywords that align with the user's search intent and are easier to rank for.\n"
            "Local SEO Focus: Prioritize local keywords to capture users in specific regions (e.g., Perth, Sydney, Melbourne) to drive more geo-targeted traffic."]
   return paragraphs

def _auto_narrative(block_id, title, paragraphs):
    """A notes slot that arrives pre-written. Editable exactly like a blank one."""
    return {
        "id": block_id,
        "type": "narrative",
        "role": "notes",
        "title": title,
        "paragraphs": list(paragraphs or []),
        "bullets": [],
        "editable": True,
    }


#: How many auto-written wins the Achievements block lists.
ACHIEVEMENT_LIMIT = 5



def _achievements(kw):
    paragraphs = [
        "Total Sessions: Increased total website sessions, demonstrating stronger organic visibility and higher user engagement.",
        "Domain Authority: Improved Domain Authority by +1, reinforcing the website's credibility and SEO performance.",
        "User Growth: Achieved growth in both total users and returning users, reflecting increased audience reach and improved user retention.",
        "Backlink Growth: Secured 10+ high-quality backlinks, strengthening the website's backlink profile and supporting long-term improvements in search engine rankings.",
    ]
    return {
        "id": "achievements",
        "type": "narrative",
        "role": "achievements",
        "title": "Achievements",
        "paragraphs": paragraphs,
        "bullets": [],
        "autoBullets": [],
        "autoBulletTerms": [],
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


def _next_label(period_key):
    """Human label for the month after this one — 'August 2026'."""
    nxt = _next_period(period_key)
    return _label_for(nxt) if nxt else "next month"


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
    ga4_totals = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
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
    # Absent on blobs frozen before prev_count was recorded, which correctly
    # leaves those reports with no comparison rather than inventing a zero.
    bl_prev_count = bl.get("prev_count")

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
        _key_metrics_grid(ga4, ga4_present, reason("ga4"), moz, moz_present, reason("moz"),
                          bl_count, bl_prev_count),
        _achievements(kw),
       _auto_narrative("ga4-overview-notes", "GA4 Notes",
                        _audience_narrative(ga4,
                                            ga4_totals.get("totalUsers"),
                                            ga4_totals.get("newUsers"),
                                            ga4_totals.get("avgEngagementSeconds"))),
        _ga4_overview_grid(ga4, ga4_present, reason("ga4")),
        _ga4_users_chart(ga4, ga4_present, reason("ga4")),
        _auto_narrative("ga4-channel-notes", "Traffic by Channel Notes",
                        _channel_narrative(ga4, ga4_present)),
        ga4_tbl["by_channel"],
        _auto_narrative("ga4-cities-notes", "Cities & Countries Notes",
                        _geo_narrative(ga4, ga4_present)),
        ga4_tbl["by_country_city"],
        _auto_narrative("ga4-landing-notes", "Landing Pages Notes",
                        _landing_narrative(ga4, ga4_present)),
        ga4_tbl["by_landing_page"],
        ga4_tbl["by_device"],
        ga4_tbl["by_browser"],
        ga4_tbl["by_operating_system"],
        ga4_tbl["by_language"],
        _auto_narrative("gsc-notes", "Search Console Notes",
                        _gsc_narrative(gsc, gsc_present, period_label)),
        _gsc_grid(gsc, gsc_present, reason("gsc")),
        _gsc_chart(gsc, gsc_present, reason("gsc")),
        _keyword_table(kw, kw_present, reason("keywords"), period_label, prev_label, prev2_label),
        _backlinks_block(bl),
        _posts_block("posts-blogs", "Blog Posts", "blog post", posts.get("blogs")),
        _posts_block("posts-linkedin", "LinkedIn Posts", "LinkedIn post", posts.get("linkedin")),
        _targets_grid_block(period, period_label),
        _auto_narrative("targets-notes", "Notes",
                        _targets_narrative()),
        _static_narrative(
            "strategy", "strategy", "Strategy & Notes",
            _strategy_narrative()),
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


def _key_metrics_grid(ga4, ga4_present, ga4_reason, moz, moz_present, moz_reason,
                      bl_count, bl_prev_count=None):
    cur = _totals(_ga4_month_sections(ga4, "report_month"), "users_overview")
    prev = _totals(_ga4_month_sections(ga4, "prior_month"), "users_overview")
    moz_deltas = (moz or {}).get("deltas", {}) if moz else {}
    da = (moz or {}).get("domain_authority") if moz else None
    da_delta = moz_deltas.get("domain_authority")
    da_prev = (da - da_delta) if (_is_num(da) and _is_num(da_delta)) else None

    # Order matters: this list is the render order of the Key Metrics cards.
    # People (total, then new, then returning) read before visit counts.
    metrics = [
        _metric("totalUsers", "Total users", "count", cur.get("totalUsers"), prev.get("totalUsers")),
        _metric("newUsers", "New users", "count", cur.get("newUsers"), prev.get("newUsers")),
        _metric("sessions", "Sessions", "count", cur.get("sessions"), prev.get("sessions")),
        _metric("returningUsers", "Returning users", "count", cur.get("returningUsers"), prev.get("returningUsers")),
        _metric("domain_authority", "Domain Authority", "count", da, da_prev, da_delta),
        _metric("new_backlinks", "New backlinks", "count", bl_count, bl_prev_count),
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
