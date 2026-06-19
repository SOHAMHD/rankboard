"""PROJECT ROUTES — the main website's API: projects + the Rank
Ledger keywords. Viewing is open to all signed-in users (provisional);
every mutation asks the matrix.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from ..config import DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD, RANK_LOCATION_CODE
from ..db import get_db
from ..security import require_active_user, require_permission
from ..services.analytics_provider import (
    ALLOWED_DIMENSIONS,
    ALLOWED_MATCH_TYPES,
    REPORT_METRICS,
    get_analytics,
    get_dimension_breakdown,
    get_returning_users,
    run_custom_report,
)
from ..services.rank_provider import check_ranks
from ..services.search_console_provider import get_search_console, query_performance
from ..services.excel_service import build_sample_workbook, parse_keyword_workbook
from ..services.snapshot_service import create_snapshot

router = APIRouter(dependencies=[Depends(require_active_user)])


def row_to_project(p: sqlite3.Row, keyword_count: int | None = None) -> dict:
    out = {
        "id": p["id"],
        "name": p["name"],
        "domain": p["domain"],
        "locationCode": p["location_code"],  # None = use the server default
        "gaPropertyId": p["ga_property_id"],  # None = GA4 traffic panel disabled
        "gscSiteUrl": p["gsc_site_url"],  # None = Search Console panel disabled
        "active": bool(p["active"]),
        "createdAt": p["created_at"],
    }
    if keyword_count is not None:
        out["keywordCount"] = keyword_count
    return out


def row_to_keyword(k: sqlite3.Row) -> dict:
    return {
        "id": k["id"],
        "term": k["term"],
        "currentRank": k["current_rank"],
        "previousRank": k["previous_rank"],  # None = first lookup ("New")
        "lastChecked": k["last_checked"],
    }


def row_to_snapshot(s, keyword_count: int | None = None) -> dict:
    # Accepts a sqlite3.Row or the summary dict from create_snapshot —
    # both index the same keys.
    out = {
        "id": s["id"],
        "periodKey": s["period_key"],
        "label": s["label"],
        "capturedAt": s["captured_at"],
        "source": s["source"],
        "locked": bool(s["locked"]),
    }
    if keyword_count is not None:
        out["keywordCount"] = keyword_count
    return out


def row_to_snapshot_rank(r: sqlite3.Row) -> dict:
    return {
        "term": r["term"],
        "rank": r["rank"],  # None = keyword had never been checked when frozen
        "lastChecked": r["last_checked"],
    }


@router.get("")
def list_projects(db: sqlite3.Connection = Depends(get_db)):
    """LEFT JOIN + GROUP BY: each project with its keywo
    rd count in one
    query. LEFT (not INNER) so projects with zero keywords still appear."""
    rows = db.execute(
        """SELECT p.*, COUNT(k.id) AS keyword_count
           FROM projects p
           LEFT JOIN keywords k ON k.project_id = p.id
           GROUP BY p.id
           ORDER BY p.created_at DESC, p.id DESC"""
    ).fetchall()
    return {"projects": [row_to_project(r, r["keyword_count"]) for r in rows]}


@router.get("/{project_id}")
def project_detail(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    keywords = db.execute(
        "SELECT * FROM keywords WHERE project_id = ? ORDER BY created_at, id", (project_id,)
    ).fetchall()
    return {"project": {**row_to_project(project), "keywords": [row_to_keyword(k) for k in keywords]}}


# ── Shared request bodies for the GA4 reads ─────────────────────────
# All three analytics endpoints (summary, single-dimension breakdown, and the
# Explore report) take the SAME structured filter payload — a list of
# {dimension, operator, value, exclude} conditions joined by `match` — so a
# filter set once in the UI applies across the whole Traffic section. POST
# bodies (not query strings) carry the structured filters cleanly.

class ReportFilterIn(BaseModel):
    dimension: str
    operator: str
    value: str = ""
    exclude: bool = False


class AnalyticsIn(BaseModel):
    start: str | None = None
    end: str | None = None
    filters: list[ReportFilterIn] = []
    match: str = "AND"


class BreakdownIn(AnalyticsIn):
    dimension: str


class ReportIn(AnalyticsIn):
    dimensions: list[str] = []
    metrics: list[str] = []
    limit: int = 250


def _validate_filters(filters: list[ReportFilterIn], match: str) -> str | None:
    """Validate the SHARED filter payload exactly the way /report does: every
    filter.dimension in ALLOWED_DIMENSIONS, every filter.operator in
    ALLOWED_MATCH_TYPES, and `match` one of AND/OR — so we never hand GA4 an
    arbitrary string. Returns an error string for the first problem, or None
    when the payload is acceptable."""
    if any(f.dimension not in ALLOWED_DIMENSIONS for f in filters):
        return "Unsupported filter dimension"
    if any(f.operator not in ALLOWED_MATCH_TYPES for f in filters):
        return "Unsupported filter operator"
    if match not in {"AND", "OR"}:
        return "Match must be AND or OR"
    return None


@router.post("/{project_id}/analytics")
def project_analytics(
    project_id: int,
    body: AnalyticsIn,
    db: sqlite3.Connection = Depends(get_db),
):
    """GA4 traffic for this project — the headline summary, the trend
    time-series, and every fixed breakdown (channels, country, city, language,
    browser, device, landing pages) in one response. Viewing is open to any
    signed-in user (the router-level require_auth), matching the other reads.

    A POST so the SHARED dimension filter (body.filters + body.match) rides
    along as structured JSON; the same payload /report accepts, validated the
    same way. With filters set, the cards, trend and breakdowns all reflect
    them. The default range is the last 28 days; start/end accept any GA4 date
    expression (e.g. "30daysAgo", "2026-06-01", "today"). If the project has no
    GA4 property ID — or GA4 isn't configured / errors out / the filter yields
    no data — the provider returns a clear message instead of crashing, and we
    pass it straight through."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    err = _validate_filters(body.filters, body.match)
    if err:
        return {"analytics": {"error": err}}

    filters = [f.model_dump() for f in body.filters]
    analytics = get_analytics(
        project["ga_property_id"],
        start_date=body.start,
        end_date=body.end,
        filters=filters,
        match=body.match,
    )
    # Returning users is a separate headline value, derived from the
    # newVsReturning dimension (see get_returning_users). Add it alongside the
    # other summary numbers when the summary report succeeded — filtered the
    # same way so the card matches the rest of the summary.
    if isinstance(analytics, dict) and isinstance(analytics.get("summary"), dict):
        analytics["summary"]["returningUsers"] = get_returning_users(
            project["ga_property_id"],
            start_date=body.start,
            end_date=body.end,
            filters=filters,
            match=body.match,
        )
    return {"analytics": analytics}


@router.post("/{project_id}/analytics/breakdown")
def project_analytics_breakdown(
    project_id: int,
    body: BreakdownIn,
    db: sqlite3.Connection = Depends(get_db),
):
    """GA4 traffic broken down by ONE requested `dimension` (plus the same
    three metrics as /analytics), powering the dynamic dimension picker.

    A POST carrying the SAME shared filter payload (body.filters + body.match)
    as /report and /analytics, validated the same way. `body.dimension` is a
    GA4 API name validated against ALLOWED_DIMENSIONS; an unknown one
    short-circuits to {"error": "Unsupported dimension"} so we never hand GA4
    arbitrary input. start/end reuse the SAME date handling as /analytics. Like
    the other GA reads it never crashes — an incompatible combination, an
    invalid filter, or any GA4 API error comes back as {"error": ...} for the
    client to show as a friendly message."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    if body.dimension not in ALLOWED_DIMENSIONS:
        return {"breakdown": {"error": "Unsupported dimension", "dimension": body.dimension}}
    err = _validate_filters(body.filters, body.match)
    if err:
        return {"breakdown": {"error": err, "dimension": body.dimension}}
    breakdown = get_dimension_breakdown(
        project["ga_property_id"],
        body.dimension,
        start_date=body.start,
        end_date=body.end,
        filters=[f.model_dump() for f in body.filters],
        match=body.match,
    )
    return {"breakdown": breakdown}


@router.post("/{project_id}/analytics/report")
def project_analytics_report(
    project_id: int,
    body: ReportIn,
    db: sqlite3.Connection = Depends(get_db),
):
    """The "Explore" report builder — ONE GA4 runReport for an arbitrary
    combination of dimensions, metrics and string filters (GA4's Free-form
    exploration / Data API runReport). Viewing is open to any signed-in user
    (the router-level require_auth), matching the other project reads.

    Every dimension and filter.dimension must be in ALLOWED_DIMENSIONS, every
    metric in REPORT_METRICS, every filter.operator in ALLOWED_MATCH_TYPES,
    and `match` one of AND/OR — so we never hand GA4 an arbitrary string. An
    invalid request short-circuits to {"report": {"error": ...}}. start/end
    reuse the SAME date handling as /analytics. Like the other GA reads it
    never crashes — any GA4 API error comes back as {"error": ...} for the
    client to show as a friendly message."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not body.dimensions:
        return {"report": {"error": "Pick at least one dimension."}}
    if not body.metrics:
        return {"report": {"error": "Pick at least one metric."}}
    if any(d not in ALLOWED_DIMENSIONS for d in body.dimensions):
        return {"report": {"error": "Unsupported dimension"}}
    if any(m not in REPORT_METRICS for m in body.metrics):
        return {"report": {"error": "Unsupported metric"}}
    err = _validate_filters(body.filters, body.match)
    if err:
        return {"report": {"error": err}}

    report = run_custom_report(
        project["ga_property_id"],
        start=body.start,
        end=body.end,
        dimensions=body.dimensions,
        metrics=body.metrics,
        filters=[f.model_dump() for f in body.filters],
        match=body.match,
        limit=body.limit,
    )
    return {"report": report}


@router.get("/{project_id}/search-console")
def project_search_console(
    project_id: int,
    start: str | None = None,
    end: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    """Google Search Console performance for this project — the headline
    totals, the per-query and per-page breakdowns, and a by-date trend in one
    response. Viewing is open to any signed-in user (the router-level
    require_auth), matching the other reads.

    start/end are YYYY-MM-DD query params reusing the SAME date handling as the
    GA4 analytics endpoint (default to the last 28 days; passed straight to the
    provider). If the project has no GSC site URL we short-circuit to a clear
    message; otherwise the provider returns {totals, queries, pages, trend} — or
    {error} on any failure (no access, API not enabled, bad site URL), which we
    pass straight through so the client shows a friendly message, never a 500."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    if not project["gsc_site_url"]:
        return {"error": "No Search Console property configured for this project"}
    data = get_search_console(project["gsc_site_url"], start_date=start, end_date=end)
    return data


# ── Search Console Performance report (Google's "Search results" report) ──
# The four enum sets the Search Analytics API accepts, validated here so we
# never hand Google an arbitrary string. Values are the lowercase forms
# Google documents (the provider sends them verbatim).
SC_SEARCH_TYPES = {"web", "image", "video", "news", "discover", "googleNews"}
SC_DIMENSIONS = {"query", "page", "country", "device", "searchAppearance", "date"}
SC_OPERATORS = {"equals", "contains", "notContains", "includingRegex", "excludingRegex"}


class SearchConsoleFilterIn(BaseModel):
    dimension: str
    operator: str
    expression: str = ""


class SearchConsolePerformanceIn(BaseModel):
    start: str | None = None
    end: str | None = None
    searchType: str = "web"
    dimension: str = "query"  # the active table breakdown
    filters: list[SearchConsoleFilterIn] = []


@router.post("/{project_id}/search-console/performance")
def project_search_console_performance(
    project_id: int,
    body: SearchConsolePerformanceIn,
    db: sqlite3.Connection = Depends(get_db),
):
    """The Search Console Performance ("Search results") report for this
    project — the headline totals, a by-date trend, and the active dimension
    breakdown, ALL over the same property + date range + search type + filter
    set, so the cards, chart and table always agree. Viewing is open to any
    signed-in user (the router-level require_auth), matching the other reads.

    A POST so the stackable filter list (each {dimension, operator, expression}
    joined by AND) rides along as structured JSON. searchType, dimension and
    every filter.dimension / filter.operator are validated against the
    allowlists above; an unknown one short-circuits to {"error": ...} so we
    never hand Google an arbitrary string. start/end are YYYY-MM-DD, defaulting
    to the last 28 days (matching the GA4 panel). If the project has no GSC
    site URL we short-circuit to a clear message; otherwise we run THREE
    queries and return {totals, trend, rows, dimension}. Like the other reads
    it never crashes — a 403, the API not being enabled, or an empty result
    comes back as {"error": ...} for the client to show as a friendly message."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if body.searchType not in SC_SEARCH_TYPES:
        return {"error": "Unsupported search type"}
    if body.dimension not in SC_DIMENSIONS:
        return {"error": "Unsupported dimension"}
    if any(f.dimension not in SC_DIMENSIONS for f in body.filters):
        return {"error": "Unsupported filter dimension"}
    if any(f.operator not in SC_OPERATORS for f in body.filters):
        return {"error": "Unsupported filter operator"}
    if not project["gsc_site_url"]:
        return {"error": "No Search Console property configured"}

    # Search Console wants concrete YYYY-MM-DD dates — default to the last 28
    # days when a bound isn't supplied (matches the GA4 panel).
    end = body.end
    start = body.start
    if not start or not end:
        from datetime import date, timedelta

        today = date.today()
        end = end or today.isoformat()
        start = start or (today - timedelta(days=27)).isoformat()

    site_url = project["gsc_site_url"]
    filters = [f.model_dump() for f in body.filters]

    def metrics_only(row: dict) -> dict:
        return {k: row[k] for k in ("clicks", "impressions", "ctr", "position")}

    try:
        def run(dimensions: list[str]) -> list[dict]:
            res = query_performance(
                site_url, start, end, body.searchType, dimensions, filters
            )
            # The provider returns {error} on any failure — surface it.
            if isinstance(res, dict) and res.get("error"):
                raise RuntimeError(res["error"])
            return res

        totals_rows = run([])  # no dimensions → a single summary row
        trend_rows = run(["date"])
        rows_data = run([body.dimension])
    except Exception as exc:
        return {"error": str(exc)}

    totals = metrics_only(totals_rows[0]) if totals_rows else {
        "clicks": 0, "impressions": 0, "ctr": 0, "position": 0,
    }
    trend = sorted(
        ({"date": (r["keys"] or [""])[0], **metrics_only(r)} for r in trend_rows),
        key=lambda d: d["date"],
    )
    rows = [{"key": (r["keys"] or [""])[0], **metrics_only(r)} for r in rows_data]

    return {"totals": totals, "trend": trend, "rows": rows, "dimension": body.dimension}


def normalize_domain(raw: str | None) -> str | None:
    """ "https://www.Sattva-Connect.com/about" -> "sattva-connect.com".
    Store one canonical form so SERP matching is reliable."""
    if not raw or not raw.strip():
        return None
    d = raw.strip().lower()
    d = d.split("://")[-1].split("/")[0].split("?")[0]
    if d.startswith("www."):
        d = d[4:]
    return d or None


def normalize_ga_property_id(raw: str | None) -> str | None:
    """Store the GA4 property ID as a bare trimmed string, or NULL when
    blank. The provider accepts either "123456789" or "properties/123456789"."""
    if not raw or not raw.strip():
        return None
    return raw.strip()


def normalize_gsc_site_url(raw: str | None) -> str | None:
    """Store the Search Console site URL as a bare trimmed string, or NULL when
    blank. The provider accepts either a URL-prefix property
    ("https://www.example.com/") or a domain property ("sc-domain:example.com"),
    so we keep it verbatim — GSC matches it exactly."""
    if not raw or not raw.strip():
        return None
    return raw.strip()


class ProjectIn(BaseModel):
    name: str
    domain: str | None = None
    locationCode: int | None = None
    gaPropertyId: str | None = None
    gscSiteUrl: str | None = None


@router.post("", status_code=201, dependencies=[Depends(require_permission("addProject"))])
def create_project(body: ProjectIn, db: sqlite3.Connection = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required.")
    cur = db.execute(
        "INSERT INTO projects (name, domain, location_code, ga_property_id, gsc_site_url, active) VALUES (?, ?, ?, ?, ?, 1)",
        (
            name,
            normalize_domain(body.domain),
            body.locationCode,
            normalize_ga_property_id(body.gaPropertyId),
            normalize_gsc_site_url(body.gscSiteUrl),
        ),
    )
    project = db.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"project": row_to_project(project)}


class ProjectUpdateIn(BaseModel):
    active: bool | None = None
    domain: str | None = None
    locationCode: int | None = None
    gaPropertyId: str | None = None
    gscSiteUrl: str | None = None


@router.patch("/{project_id}", dependencies=[Depends(require_permission("toggleProject"))])
def update_project(project_id: int, body: ProjectUpdateIn, db: sqlite3.Connection = Depends(get_db)):
    """Started life as the active/inactive toggle; now also updates the
    domain. (Uses the toggleProject permission as a general "manage
    project settings" right for now — revisit when the matrix is decided.)"""
    fields, values = [], []
    if body.active is not None:
        fields.append("active = ?")
        values.append(1 if body.active else 0)
    if body.domain is not None:
        fields.append("domain = ?")
        values.append(normalize_domain(body.domain))
    if body.locationCode is not None:
        fields.append("location_code = ?")
        values.append(body.locationCode)
    if body.gaPropertyId is not None:
        fields.append("ga_property_id = ?")
        values.append(normalize_ga_property_id(body.gaPropertyId))
    if body.gscSiteUrl is not None:
        fields.append("gsc_site_url = ?")
        values.append(normalize_gsc_site_url(body.gscSiteUrl))
    if not fields:
        raise HTTPException(400, "Nothing to update.")

    values.append(project_id)
    cur = db.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
    if cur.rowcount == 0:
        raise HTTPException(404, "Project not found.")
    return {"ok": True}


@router.delete("/{project_id}", dependencies=[Depends(require_permission("deleteProject"))])
def delete_project(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """The FK cascade in the schema deletes the project's keywords
    automatically — no manual cleanup, no orphans."""
    cur = db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "Project not found.")
    return {"ok": True}


@router.post(
    "/{project_id}/check-ranks",
    dependencies=[Depends(require_permission("addKeyword"))],
)
def check_project_ranks(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Check every keyword in the project against the rank provider and
    record the lookups (current -> previous rotation). This is the same
    write path as manual entry — a future cron job just calls this
    endpoint on a schedule and the dashboard fills itself in."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    kws = db.execute(
        "SELECT * FROM keywords WHERE project_id = ? ORDER BY created_at, id", (project_id,)
    ).fetchall()
    if not kws:
        raise HTTPException(400, "No keywords to check yet.")

    real_mode = bool(DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD)
    if real_mode and not project["domain"]:
        raise HTTPException(
            400,
            "This project has no domain set, so the checker doesn't know which site to look for. "
            "Add one when creating the project, or via PATCH /api/projects/:id {\"domain\": \"yoursite.com\"}.",
        )

    # Per-project country if set, otherwise the global server default.
    location_code = project["location_code"] if project["location_code"] is not None else RANK_LOCATION_CODE

    try:
        ranks, source = check_ranks(
            project["domain"],
            [{"term": k["term"], "currentRank": k["current_rank"]} for k in kws],
            location_code,
        )
    except Exception as exc:
        raise HTTPException(502, f"Rank check failed: {exc}")

    updated, not_found = 0, []
    for k in kws:
        rank = ranks.get(k["term"])
        if rank is None:
            # Not in the checked depth: report it, leave the ledger row
            # untouched rather than inventing a number.
            not_found.append(k["term"])
            continue
        db.execute(
            "UPDATE keywords SET previous_rank = current_rank, current_rank = ?, last_checked = date('now') WHERE id = ?",
            (rank, k["id"]),
        )
        updated += 1

    return {"source": source, "checked": len(kws), "updated": updated, "notFound": not_found}


# ── Bulk import via Excel ───────────────────────────────────────────

@router.get("/keywords/sample-template")
def download_sample_template(user=Depends(require_active_user)):
    """Serve the .xlsx template. A GET that returns a file, not JSON:
    the Content-Disposition header tells the browser to download it
    with a filename instead of trying to render it."""
    data = build_sample_workbook()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="rankboard-keywords-template.xlsx"'},
    )


@router.post(
    "/{project_id}/keywords/bulk-import",
    dependencies=[Depends(require_permission("addKeyword"))],
)
async def bulk_import_keywords(project_id: int, file: UploadFile, db: sqlite3.Connection = Depends(get_db)):
    """Accept an uploaded .xlsx, validate every row, insert the good
    ones, and report a per-row reason for every skipped one.

    Partial success is intentional: importing 47 of 50 keywords and
    naming the 3 problems beats rejecting the whole file over one typo.
    """
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload an .xlsx file (the sample template format).")

    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:  # 5 MB ceiling
        raise HTTPException(400, "That file is too large (limit 5 MB).")

    try:
        valid, errors = parse_keyword_workbook(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    # Skip terms already tracked on this project (idempotent re-imports).
    existing = {
        r["term"]
        for r in db.execute("SELECT term FROM keywords WHERE project_id = ?", (project_id,)).fetchall()
    }
    to_insert = [v for v in valid if v["term"] not in existing]
    skipped_existing = len(valid) - len(to_insert)

    for v in to_insert:
        # Keyword only — current/previous rank stay NULL until a rank
        # check fills them in (same as adding a keyword by hand).
        db.execute(
            "INSERT INTO keywords (project_id, term) VALUES (?, ?)",
            (project_id, v["term"]),
        )

    return {
        "imported": len(to_insert),
        "skippedExisting": skipped_existing,
        "errors": errors,  # [{row, reason}, ...]
        "totalRows": len(valid) + len(errors),
    }


class KeywordIn(BaseModel):
    term: str = ""
    currentRank: int | None = None
    previousRank: int | None = None


@router.post(
    "/{project_id}/keywords", status_code=201,
    dependencies=[Depends(require_permission("addKeyword"))],
)
def add_keyword(project_id: int, body: KeywordIn, db: sqlite3.Connection = Depends(get_db)):
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    term = body.term.strip().lower()
    if not term:
        raise HTTPException(400, "Keyword is required.")
    if body.currentRank is not None and body.currentRank < 1:
        raise HTTPException(400, "Current rank must be a whole number of 1 or more.")
    if body.previousRank is not None and body.previousRank < 1:
        raise HTTPException(400, "Previous rank must be a whole number of 1 or more.")

    cur = db.execute(
        "INSERT INTO keywords (project_id, term, current_rank, previous_rank) VALUES (?, ?, ?, ?)",
        (project_id, term, body.currentRank, body.previousRank),
    )
    keyword = db.execute("SELECT * FROM keywords WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"keyword": row_to_keyword(keyword)}


class NewRankIn(BaseModel):
    newRank: int | None = None


@router.patch(
    "/{project_id}/keywords/{keyword_id}",
    dependencies=[Depends(require_permission("addKeyword"))],
)
def record_lookup(project_id: int, keyword_id: int, body: NewRankIn, db: sqlite3.Connection = Depends(get_db)):
    """Record a NEW LOOKUP: current -> previous, new number -> current,
    stamp the date. A future automated rank-checker calls this same
    write path — only WHO supplies the number changes."""
    if body.newRank is None or body.newRank < 1:
        raise HTTPException(400, "New rank must be a whole number of 1 or more.")

    kw = db.execute(
        "SELECT * FROM keywords WHERE id = ? AND project_id = ?", (keyword_id, project_id)
    ).fetchone()
    if kw is None:
        raise HTTPException(404, "Keyword not found.")

    db.execute(
        "UPDATE keywords SET previous_rank = current_rank, current_rank = ?, last_checked = date('now') WHERE id = ?",
        (body.newRank, keyword_id),
    )
    updated = db.execute("SELECT * FROM keywords WHERE id = ?", (keyword_id,)).fetchone()
    return {"keyword": row_to_keyword(updated)}


@router.delete(
    "/{project_id}/keywords/{keyword_id}",
    dependencies=[Depends(require_permission("deleteKeyword"))],
)
def delete_keyword(project_id: int, keyword_id: int, db: sqlite3.Connection = Depends(get_db)):
    # Both ids in the WHERE clause: a keyword can only be deleted
    # through its own project — matters once per-project access exists.
    cur = db.execute(
        "DELETE FROM keywords WHERE id = ? AND project_id = ?", (keyword_id, project_id)
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "Keyword not found.")
    return {"ok": True}


# ── Snapshots — frozen monthly copies of the ledger (read-only views) ─

@router.post(
    "/{project_id}/snapshots", status_code=201,
    dependencies=[Depends(require_permission("addKeyword"))],
)
def save_snapshot(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Freeze the current month's ranks for this project. Gated by the
    same write permission as adding a keyword. The capture itself lives
    in snapshot_service.create_snapshot (404 unknown project, 409 if the
    month is locked)."""
    summary = create_snapshot(db, project_id)
    return {"snapshot": row_to_snapshot(summary, summary["keyword_count"])}


@router.get("/{project_id}/snapshots")
def list_snapshots(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """All saved snapshots for the project, newest month first, each with
    its frozen keyword count. Read-only."""
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    rows = db.execute(
        """SELECT s.*, COUNT(sr.id) AS keyword_count
           FROM snapshots s
           LEFT JOIN snapshot_ranks sr ON sr.snapshot_id = s.id
           WHERE s.project_id = ?
           GROUP BY s.id
           ORDER BY s.period_key DESC""",
        (project_id,),
    ).fetchall()
    return {"snapshots": [row_to_snapshot(r, r["keyword_count"]) for r in rows]}


@router.get("/{project_id}/snapshots/{snapshot_id}")
def snapshot_detail(project_id: int, snapshot_id: int, db: sqlite3.Connection = Depends(get_db)):
    """One snapshot's meta plus its frozen rows (term, rank, last_checked),
    ranked best-first with never-checked keywords (NULL rank) last.
    Read-only."""
    snap = db.execute(
        "SELECT * FROM snapshots WHERE id = ? AND project_id = ?", (snapshot_id, project_id)
    ).fetchone()
    if snap is None:
        raise HTTPException(404, "Snapshot not found.")
    rows = db.execute(
        # `rank IS NULL` sorts 0 (has a rank) before 1 (never checked).
        "SELECT * FROM snapshot_ranks WHERE snapshot_id = ? ORDER BY rank IS NULL, rank ASC, term",
        (snapshot_id,),
    ).fetchall()
    return {
        "snapshot": {
            **row_to_snapshot(snap, len(rows)),
            "ranks": [row_to_snapshot_rank(r) for r in rows],
        }
    }
