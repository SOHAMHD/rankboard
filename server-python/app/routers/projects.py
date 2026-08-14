import logging
import re
import sqlite3
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..access import accessible_project_ids
from ..db import INTEGRITY_ERRORS, get_db
from ..permissions import SENDER_ROLES
from ..security import (
    require_active_user,
    require_open_project,
    require_permission,
    require_project_access,
    require_roles,
)
from ..services.analytics_provider import (
    ALLOWED_DIMENSIONS,
    ALLOWED_MATCH_TYPES,
    REPORT_METRICS,
    get_analytics,
    get_dimension_breakdown,
    get_returning_users,
    run_custom_report,
)
from ..services.search_console_provider import (
    default_range as sc_default_range,
    get_search_console,
    list_sites,
    query_performance,
)
from ..services.excel_service import build_sample_workbook, parse_keyword_workbook
from ..services.images import normalize_logo
from ..services import keyword_rank_service
from ..services.email_service import clean_recipient_set, upsert_project_recipients

router = APIRouter(dependencies=[Depends(require_active_user)])


def row_to_project(p: sqlite3.Row, keyword_count: int | None = None) -> dict:
    out = {
        "id": p["id"],
        "name": p["name"],
        "clientName": p["client_name"],
        "domain": p["domain"],
        # A data URI, so this is by far the largest field on the row. Included in
        # the list response regardless: the projects grid renders every card's
        # logo, and fetching them one by one would be 14 extra round trips to
        # paint one screen.
        "clientLogo": p["client_logo"],
        "gaPropertyId": p["ga_property_id"],
        "gscSiteUrl": p["gsc_site_url"],
        "active": bool(p["active"]),
        "createdAt": p["created_at"],
    }
    if keyword_count is not None:
        out["keywordCount"] = keyword_count
    return out


def row_to_keyword(k: sqlite3.Row) -> dict:
    # current_rank / previous_rank are legacy columns kept for the historical
    # data they hold; nothing writes them any more and reports read the monthly
    # grid instead. They stay in the response so an older client build doesn't
    # break on a missing key.
    return {
        "id": k["id"],
        "term": k["term"],
        "currentRank": k["current_rank"],
        "previousRank": k["previous_rank"],
        "lastChecked": k["last_checked"],
    }


@router.get("")
def list_projects(
    user: sqlite3.Row = Depends(require_active_user),
    db: sqlite3.Connection = Depends(get_db),
):
    allowed = accessible_project_ids(user, db)
    if allowed is None:
        rows = db.execute(
            """SELECT p.*, COUNT(k.id) AS keyword_count
               FROM projects p
               LEFT JOIN keywords k ON k.project_id = p.id
               GROUP BY p.id
               ORDER BY p.created_at DESC, p.id DESC"""
        ).fetchall()
    elif not allowed:
        rows = []
    else:
        placeholders = ",".join("?" * len(allowed))
        rows = db.execute(
            f"""SELECT p.*, COUNT(k.id) AS keyword_count
               FROM projects p
               LEFT JOIN keywords k ON k.project_id = p.id
               WHERE p.id IN ({placeholders})
               GROUP BY p.id
               ORDER BY p.created_at DESC, p.id DESC""",
            tuple(allowed),
        ).fetchall()
    return {"projects": [row_to_project(r, r["keyword_count"]) for r in rows]}


# require_open_project, not require_project_access: this is the call the dashboard
# makes to open a project, so refusing it here is what makes "inactive" mean
# something rather than being a coloured pill. The PATCH that reactivates and the
# DELETE that removes still use the plain access check.
@router.get("/{project_id}", dependencies=[Depends(require_open_project)])
def project_detail(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    keywords = db.execute(
        "SELECT * FROM keywords WHERE project_id = ? ORDER BY created_at, id", (project_id,)
    ).fetchall()
    return {"project": {**row_to_project(project), "keywords": [row_to_keyword(k) for k in keywords]}}


class ReportFilterIn(BaseModel):
    dimension: str
    operator: str
    value: str = ""
    exclude: bool = False


class AnalyticsIn(BaseModel):
    start: str | None = None
    end: str | None = None
    # Number of days for a preset window ("last 28 days" -> 28). When present,
    # the range is sent to GA4 as relative tokens instead of the explicit dates,
    # so GA4 resolves the days in the PROPERTY's reporting timezone rather than
    # trusting dates the browser computed in the viewer's timezone. start/end are
    # still sent and still used for display; they're ignored for the query.
    preset: int | None = None
    filters: list[ReportFilterIn] = []
    match: str = "AND"


class BreakdownIn(AnalyticsIn):
    dimension: str


class ReportIn(AnalyticsIn):
    dimensions: list[str] = []
    metrics: list[str] = []
    limit: int = 250


#: Longest preset window we'll turn into a relative token. Guards against a
#: client sending something absurd that GA4 would reject.
_MAX_PRESET_DAYS = 730


#: A plain calendar date. GA4 also accepts relative tokens ("yesterday"),
#: which must pass through untouched.
_YMD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _clamp_to_today(value: str | None) -> str | None:
    """Trim a YYYY-MM-DD to today, since no provider has tomorrow's data.

    The date pickers now cap themselves, but this is the server saying the same
    thing: a range ending next month is not a question anyone can answer, and
    silently returning an empty window for it reads as a broken integration
    rather than an impossible request.

    Clamped rather than rejected — the useful part of "1st to the 31st" on the
    13th is the first thirteen days, and refusing the whole range would lose it.
    Anything that isn't a plain date is passed through for the provider to judge;
    GA4 also accepts relative tokens like "yesterday".
    """
    if not value or not _YMD_RE.match(value):
        return value
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return today if value > today else value


def _ga_range(body) -> tuple[str | None, str | None]:
    """The start/end to send to GA4.

    For a preset window we hand GA4 relative tokens ("28daysAgo" -> "yesterday")
    instead of calendar dates. GA4 resolves those against the property's own
    reporting timezone, which is the only timezone that actually decides which
    day a session belongs to. The dates the browser computed are in the viewer's
    timezone, so near midnight — or for anyone not in the property's timezone —
    they selected a subtly different window than the user asked for, and the
    figures drifted from what the GA4 UI showed.

    Explicit (custom) ranges are passed through untouched: there the user means
    specific calendar days.
    """
    preset = getattr(body, "preset", None)
    if isinstance(preset, int) and 1 <= preset <= _MAX_PRESET_DAYS:
        return f"{preset}daysAgo", "yesterday"
    return _clamp_to_today(body.start), _clamp_to_today(body.end)


def _validate_filters(filters: list[ReportFilterIn], match: str) -> str | None:
    if any(f.dimension not in ALLOWED_DIMENSIONS for f in filters):
        return "Unsupported filter dimension"
    if any(f.operator not in ALLOWED_MATCH_TYPES for f in filters):
        return "Unsupported filter operator"
    if match not in {"AND", "OR"}:
        return "Match must be AND or OR"
    return None


@router.post("/{project_id}/analytics", dependencies=[Depends(require_project_access)])
def project_analytics(
    project_id: int,
    body: AnalyticsIn,
    db: sqlite3.Connection = Depends(get_db),
):
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    err = _validate_filters(body.filters, body.match)
    if err:
        return {"analytics": {"error": err}}

    filters = [f.model_dump() for f in body.filters]
    ga_start, ga_end = _ga_range(body)
    kw = dict(start_date=ga_start, end_date=ga_end, filters=filters, match=body.match)

    with ThreadPoolExecutor(max_workers=2) as pool:
        analytics_job = pool.submit(get_analytics, project["ga_property_id"], **kw)
        returning_job = pool.submit(get_returning_users, project["ga_property_id"], **kw)
        analytics = analytics_job.result()
        if isinstance(analytics, dict) and isinstance(analytics.get("summary"), dict):
            analytics["summary"]["returningUsers"] = returning_job.result()

    return {"analytics": analytics}


@router.post("/{project_id}/analytics/breakdown", dependencies=[Depends(require_project_access)])
def project_analytics_breakdown(
    project_id: int,
    body: BreakdownIn,
    db: sqlite3.Connection = Depends(get_db),
):
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
        start_date=_ga_range(body)[0],
        end_date=_ga_range(body)[1],
        filters=[f.model_dump() for f in body.filters],
        match=body.match,
    )
    return {"breakdown": breakdown}


@router.post("/{project_id}/analytics/report", dependencies=[Depends(require_project_access)])
def project_analytics_report(
    project_id: int,
    body: ReportIn,
    db: sqlite3.Connection = Depends(get_db),
):
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not body.dimensions:
        return {"report": {"error": "Pick at least one dimension."}}
    if not body.metrics:
        return {"report": {"error": "Pick at least one metric."}}
    if any(d not in ALLOWED_DIMENSIONS for d in body.dimensions):
        # Name the offending value. A bare "Unsupported dimension" is
        # indistinguishable from a GA4 error, and it hides the common cause:
        # the frontend was rebuilt but this process wasn't restarted, so the
        # two disagree about which dimensions exist.
        bad = [d for d in body.dimensions if d not in ALLOWED_DIMENSIONS]
        return {"report": {"error": (
            f"Unsupported dimension: {', '.join(bad)}. This server accepts "
            f"{len(ALLOWED_DIMENSIONS)} dimensions; if you expect this one to work, "
            "the API process may need restarting to pick up a newer allowlist."
        )}}
    if any(m not in REPORT_METRICS for m in body.metrics):
        return {"report": {"error": "Unsupported metric"}}
    err = _validate_filters(body.filters, body.match)
    if err:
        return {"report": {"error": err}}

    report = run_custom_report(
        project["ga_property_id"],
        start=_ga_range(body)[0],
        end=_ga_range(body)[1],
        dimensions=body.dimensions,
        metrics=body.metrics,
        filters=[f.model_dump() for f in body.filters],
        match=body.match,
        limit=body.limit,
    )
    return {"report": report}


@router.get("/{project_id}/search-console", dependencies=[Depends(require_project_access)])
def project_search_console(
    project_id: int,
    start: str | None = None,
    end: str | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    if not project["gsc_site_url"]:
        return {"error": "No Search Console property configured for this project"}
    data = get_search_console(project["gsc_site_url"], start_date=start, end_date=end)
    return data


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
    # Preset window length. GSC reports in Pacific time and lags a few days, so
    # the server rebuilds the range from this rather than trusting dates the
    # browser computed in the viewer's timezone. start/end remain for display.
    preset: int | None = None
    searchType: str = "web"
    dimension: str = "query"
    filters: list[SearchConsoleFilterIn] = []


@router.post("/{project_id}/search-console/performance", dependencies=[Depends(require_project_access)])
def project_search_console_performance(
    project_id: int,
    body: SearchConsolePerformanceIn,
    db: sqlite3.Connection = Depends(get_db),
):
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

    # Search Console reports in Pacific time and its data lags a few days, so a
    # window ending at the browser's or server's "today" asks for days that do
    # not exist and reads low. For preset windows, rebuild the range the way the
    # GSC UI does: N days ending at the last date with data. Explicit custom
    # dates are respected as given.
    # Clamped for the same reason the GA4 range is: a custom window running into
    # next month asks for days that cannot exist, and comes back looking like a
    # broken integration rather than an impossible question.
    end = _clamp_to_today(body.end)
    start = _clamp_to_today(body.start)
    preset_days = getattr(body, "preset", None)
    if isinstance(preset_days, int) and 1 <= preset_days <= _MAX_PRESET_DAYS:
        start, end = sc_default_range(preset_days)
    elif not start or not end:
        default_start, default_end = sc_default_range(28)
        end = end or default_end
        start = start or default_start

    site_url = project["gsc_site_url"]
    filters = [f.model_dump() for f in body.filters]

    def metrics_only(row: dict) -> dict:
        return {k: row[k] for k in ("clicks", "impressions", "ctr", "position")}

    try:
        def run(dimensions: list[str]) -> list[dict]:
            res = query_performance(
                site_url, start, end, body.searchType, dimensions, filters
            )
            if isinstance(res, dict) and res.get("error"):
                raise RuntimeError(res["error"])
            return res

        totals_rows = run([])
        trend_rows = run(["date"])
        rows_data = run([body.dimension])
    except Exception:
        # Logged in full, reported as a fixed string. Google's errors quote the
        # service-account principal and the quota project back at you, and this
        # response goes to any user with access to the project.
        logging.getLogger(__name__).exception("Search Console performance query failed")
        return {"error": "Couldn't reach Search Console — check the project's property setting."}

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
    if not raw or not raw.strip():
        return None
    d = raw.strip().lower()
    d = d.split("://")[-1].split("/")[0].split("?")[0]
    if d.startswith("www."):
        d = d[4:]
    return d or None


def normalize_client_name(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    return " ".join(raw.split())[:120]


def normalize_client_logo(raw: str | None) -> str | None:
    """HTTP wrapper around the shared image validator.

    The rules live in services/images.py because the PDF renderer applies the same
    ones — a format accepted here but dropped there would look like a successful
    upload and a missing logo.
    """
    try:
        return normalize_logo(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def normalize_ga_property_id(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    return raw.strip()


def normalize_gsc_site_url(raw: str | None) -> str | None:
    """Tidy the obvious, deterministic mistakes. Nothing that changes meaning.

    A URL-prefix property in Search Console always ends in `/`; Google rejects
    the same URL without it. That one is safe to add. `www` is NOT — bare and
    www are genuinely different properties, so guessing would point the project
    at someone else's data. `verify_gsc_site_url` catches those.
    """
    if not raw or not raw.strip():
        return None
    value = raw.strip()
    if value.lower().startswith("sc-domain:"):
        # Domain properties take no path and no slash.
        return "sc-domain:" + value.split(":", 1)[1].strip().strip("/").lower()
    if value.startswith(("http://", "https://")) and "/" not in value.split("://", 1)[1]:
        value += "/"
    return value


def verify_gsc_site_url(value: str | None) -> None:
    """Refuse a property the service account can't actually read.

    Saving an unusable value used to be silent: the project looked configured and
    every Search Console request failed later with a raw Google 403/400, which
    reads like broken credentials rather than a typo. Two of this install's
    projects sat mistyped for months for exactly that reason — one with a
    spurious `www.`, one missing its trailing slash.

    Advisory, deliberately: if Google can't be reached, or no key is configured,
    the value is accepted. Editing a project must not depend on a third party
    being up, and an install with no key at all still needs to record the URL.
    """
    if not value:
        return
    sites, err = list_sites()
    if err or not sites:
        return
    if value in sites:
        return

    def core(s: str) -> str:
        s = s.split("://", 1)[-1].strip("/").lower()
        return s[4:] if s.startswith("www.") else s

    near = [s for s in sites if core(s) == core(value)]
    detail = f" Did you mean “{near[0]}”?" if near else ""
    raise HTTPException(
        400,
        f"“{value}” isn't a Search Console property this service account can read."
        f"{detail} It has to match the property exactly — https://example.com/ with the"
        " trailing slash for a URL-prefix property, sc-domain:example.com for a domain"
        " one — and the service account must be added as a user on it.",
    )


def _property_core(value: str) -> str:
    """A property string reduced to the host it refers to.

    `sc-domain:example.com`, `https://example.com/` and `https://www.example.com/`
    all reduce to `example.com`, which is what lets a plain domain be matched
    against whatever form the property actually takes.
    """
    if value.lower().startswith("sc-domain:"):
        host = value.split(":", 1)[1]
    else:
        host = value.split("://", 1)[-1].split("/")[0]
    host = host.strip().strip("/").lower()
    return host[4:] if host.startswith("www.") else host


def match_gsc_properties(domain: str | None) -> list[str]:
    """Search Console properties that refer to `domain`.

    Empty when nothing matches or Google can't be reached — callers treat that as
    "couldn't decide", never as "no property".
    """
    if not domain or not domain.strip():
        return []
    sites, err = list_sites()
    if err or not sites:
        return []
    wanted = _property_core(domain)
    return [s for s in sites if _property_core(s) == wanted]


def resolve_gsc_site_url(
    domain: str | None,
    explicit: str | None,
    current: str | None = None,
) -> str | None:
    """Decide a project's Search Console property.

    Replaces a second free-text field that asked for the same site in a different
    notation — the source of both of this install's misconfigurations (one with a
    spurious `www.`, one missing the trailing slash a URL-prefix property always
    carries).

    `current` is what the project has now, and it is the answer whenever this
    can't do better. That matters more than it looks: returning None on an
    inconclusive lookup would clear a working property every time Google was
    briefly unreachable, from a form that no longer has a field to restore it
    with.

    Order:
      1. an explicit override wins — a property need not be the domain in the
         Moz/backlinks field (a subdirectory property, say)
      2. no domain to match, or Google unreachable -> keep `current`
      3. exactly one property matches the domain -> use it
      4. several match (a bare *and* a www property) -> keep `current` if it is
         one of them, otherwise give up rather than guess; picking one would
         silently report a different site's numbers
      5. none match -> None, the domain genuinely has no property
    """
    if explicit and explicit.strip():
        return normalize_gsc_site_url(explicit)

    if not domain or not domain.strip():
        return current

    sites, err = list_sites()
    if err or not sites:
        return current

    matches = [s for s in sites if _property_core(s) == _property_core(domain)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return current if current in matches else None
    return None


@router.get("/gsc-properties/match",
            dependencies=[Depends(require_permission("addProject"))])
def gsc_properties_match(domain: str = Query("", description="Bare domain, e.g. example.com")):
    """Powers the project form: what would be picked, and what else is available.

    `properties` is the full list so the form can offer a choice when `matches`
    isn't exactly one, instead of making the user retype a string Google has
    already told us.

    Gated on `addProject` because `properties` is every Search Console property
    on the service account — i.e. every client's domain. It was previously open
    to any signed-in user, including a Client who should only ever see their own.
    """
    sites, err = list_sites()
    return {
        "matches": match_gsc_properties(domain),
        "properties": sites,
        "error": err,
    }


def _clean_recipients(primary: str, ccs: list[str] | None) -> tuple[str, list[str]]:
    """HTTP wrapper around the shared validator in email_service."""
    try:
        return clean_recipient_set(primary, ccs)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


class ProjectIn(BaseModel):
    name: str
    clientName: str | None = None
    domain: str | None = None
    #: The client's logo as an uploaded data URI. See services/images.py.
    clientLogo: str | None = None
    gaPropertyId: str | None = None
    #: Optional override. Normally the property is matched from `domain`; this is
    #: for the cases where it can't be — an ambiguous domain, or a property that
    #: isn't the domain (a subdirectory, say).
    gscSiteUrl: str | None = None


@router.post("", status_code=201, dependencies=[Depends(require_permission("addProject"))])
def create_project(body: ProjectIn, db: sqlite3.Connection = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Project name is required.")
    domain = normalize_domain(body.domain)
    gsc_site_url = resolve_gsc_site_url(domain, body.gscSiteUrl)
    verify_gsc_site_url(gsc_site_url)
    cur = db.execute(
        "INSERT INTO projects (name, client_name, domain, client_logo, ga_property_id,"
        " gsc_site_url, active)"
        " VALUES (?, ?, ?, ?, ?, ?, 1)",
        (
            name,
            normalize_client_name(body.clientName),
            domain,
            normalize_client_logo(body.clientLogo),
            normalize_ga_property_id(body.gaPropertyId),
            gsc_site_url,
        ),
    )
    project = db.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"project": row_to_project(project)}


class ProjectUpdateIn(BaseModel):
    active: bool | None = None
    clientName: str | None = None
    domain: str | None = None
    clientLogo: str | None = None
    gaPropertyId: str | None = None
    gscSiteUrl: str | None = None


@router.patch("/{project_id}", dependencies=[Depends(require_project_access), Depends(require_permission("toggleProject"))])
def update_project(project_id: int, body: ProjectUpdateIn, db: sqlite3.Connection = Depends(get_db)):
    fields, values = [], []
    if body.active is not None:
        fields.append("active = ?")
        values.append(1 if body.active else 0)
    domain = normalize_domain(body.domain) if body.domain is not None else None
    if body.domain is not None:
        fields.append("domain = ?")
        values.append(domain)
    # Keyed off model_fields_set, not "is not None", so sending null clears it.
    if "clientName" in body.model_fields_set:
        fields.append("client_name = ?")
        values.append(normalize_client_name(body.clientName))
    if body.gaPropertyId is not None:
        fields.append("ga_property_id = ?")
        values.append(normalize_ga_property_id(body.gaPropertyId))
    # model_fields_set, not "is not None": null is how the form removes a logo,
    # and treating it as "unchanged" would make the remove button do nothing.
    if "clientLogo" in body.model_fields_set:
        fields.append("client_logo = ?")
        values.append(normalize_client_logo(body.clientLogo))

    # Re-resolve when either side of the decision moved. Editing the domain alone
    # used to leave gsc_site_url pointing at the old site, silently — and the form
    # no longer has a field to correct it with, so resolution has to follow the
    # domain. `current` is passed so an inconclusive lookup keeps what works.
    if {"domain", "gscSiteUrl"} & body.model_fields_set:
        row = db.execute(
            "SELECT domain, gsc_site_url FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Project not found.")
        gsc_site_url = resolve_gsc_site_url(
            domain if "domain" in body.model_fields_set else row["domain"],
            body.gscSiteUrl,
            current=row["gsc_site_url"],
        )
        verify_gsc_site_url(gsc_site_url)
        fields.append("gsc_site_url = ?")
        values.append(gsc_site_url)
    if not fields:
        raise HTTPException(400, "Nothing to update.")

    values.append(project_id)
    cur = db.execute(f"UPDATE projects SET {', '.join(fields)} WHERE id = ?", values)
    if cur.rowcount == 0:
        raise HTTPException(404, "Project not found.")
    return {"ok": True}


@router.delete("/{project_id}", dependencies=[Depends(require_project_access), Depends(require_permission("deleteProject"))])
def delete_project(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    if cur.rowcount == 0:
        raise HTTPException(404, "Project not found.")
    return {"ok": True}


@router.get("/keywords/sample-template")
def download_sample_template(user=Depends(require_active_user)):
    data = build_sample_workbook()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="seo-dashboard-keywords-template.xlsx"'},
    )


#: Read one byte past the limit so an oversized upload is rejected on the
#: strength of what has been read, rather than after the whole thing is resident.
MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.post(
    "/{project_id}/keywords/bulk-import",
    dependencies=[Depends(require_project_access), Depends(require_permission("addKeyword"))],
)
def bulk_import_keywords(project_id: int, file: UploadFile, db: sqlite3.Connection = Depends(get_db)):
    # Deliberately a plain `def`. This was the only `async def` handler in the
    # app, but its body is synchronous psycopg plus CPU-bound openpyxl parsing —
    # so it ran that work directly on the event loop and stalled every other
    # request in the process for the duration of the import. As a sync handler
    # FastAPI runs it in the threadpool instead.
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Please upload an .xlsx file (the sample template format).")

    # Bounded read: the previous version called .read() with no argument and
    # checked the length afterwards, so a 500 MB upload was fully buffered in
    # memory before being rejected.
    raw = file.file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(400, "That file is too large (limit 5 MB).")

    try:
        valid, errors = parse_keyword_workbook(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    existing = {
        r["term"]
        for r in db.execute("SELECT term FROM keywords WHERE project_id = ?", (project_id,)).fetchall()
    }
    to_insert = [v for v in valid if v["term"] not in existing]

    # One round trip instead of one per keyword. A 500-row import was previously
    # 500 separate statements against the database.
    #
    # ON CONFLICT rather than trusting the Python diff above: that diff is a
    # read followed by a write, so a concurrent import — or one racing a single
    # add — slipped between them and hit idx_keywords_project_term. Because
    # connections are autocommit, an unguarded executemany then left part of the
    # batch committed and returned a 500. The transaction makes the batch
    # all-or-nothing, and DO NOTHING makes the race a no-op instead of an error.
    #
    # No conflict target on purpose. Naming one — ON CONFLICT (project_id, term)
    # — requires that exact unique index to exist, and Postgres raises
    # InvalidColumnReference ("no unique or exclusion constraint matching the ON
    # CONFLICT specification") when it doesn't. idx_keywords_project_term is
    # optional DDL: a database that already holds duplicate terms rejects it at
    # boot, so on those installs every import died with a 500 before a single row
    # was written. The bare form conflicts on whatever unique index happens to
    # exist, which is the index where there is one and a no-op where there isn't
    # — the same behaviour the Python diff above already provides.
    imported = 0
    if to_insert:
        with db.transaction():
            cur = db.executemany(
                "INSERT INTO keywords (project_id, term) VALUES (?, ?)"
                " ON CONFLICT DO NOTHING",
                [(project_id, v["term"]) for v in to_insert],
            )
            # rowcount counts rows actually written, so a term inserted by a
            # concurrent request is reported as skipped rather than imported.
            imported = cur.rowcount if cur.rowcount is not None else len(to_insert)

    return {
        "imported": imported,
        "skippedExisting": len(valid) - imported,
        "errors": errors,
        "totalRows": len(valid) + len(errors),
    }


#: A keyword no user would ever type. Long enough for the longest real long-tail
#: phrase, short enough that a pasted paragraph is rejected as the mistake it is.
MAX_TERM_LEN = 200


class KeywordIn(BaseModel):
    term: str = ""


@router.post(
    "/{project_id}/keywords", status_code=201,
    dependencies=[Depends(require_project_access), Depends(require_permission("addKeyword"))],
)
def add_keyword(project_id: int, body: KeywordIn, db: sqlite3.Connection = Depends(get_db)):
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    term = body.term.strip().lower()
    if not term:
        raise HTTPException(400, "Keyword is required.")
    if len(term) > MAX_TERM_LEN:
        raise HTTPException(400, f"That keyword is too long (limit {MAX_TERM_LEN} characters).")

    # Bulk import has always de-duplicated; the single-add path did not, and
    # there was no unique index behind it either. Two keywords sharing a term
    # break the term-based rank fallback in reports, so refuse the duplicate
    # rather than create it. idx_keywords_project_term is the real guard — this
    # check exists to turn the resulting error into a useful message.
    if db.execute(
        "SELECT id FROM keywords WHERE project_id = ? AND term = ?", (project_id, term)
    ).fetchone() is not None:
        raise HTTPException(409, f"“{term}” is already tracked on this project.")

    try:
        cur = db.execute(
            "INSERT INTO keywords (project_id, term) VALUES (?, ?)",
            (project_id, term),
        )
    except INTEGRITY_ERRORS:
        raise HTTPException(409, f"“{term}” is already tracked on this project.")
    keyword = db.execute("SELECT * FROM keywords WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"keyword": row_to_keyword(keyword)}


@router.delete(
    "/{project_id}/keywords/{keyword_id}",
    dependencies=[Depends(require_project_access), Depends(require_permission("deleteKeyword"))],
)
def delete_keyword(project_id: int, keyword_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "DELETE FROM keywords WHERE id = ? AND project_id = ?", (keyword_id, project_id)
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "Keyword not found.")
    return {"ok": True}


class RankCellIn(BaseModel):
    keywordId: int
    month: str
    # A generous hard ceiling so an absurd integer is rejected by the parser
    # rather than reaching Postgres. keyword_rank_service.MAX_RANK is the real
    # limit and produces the message a user actually sees.
    rank: int | None = Field(default=None, ge=0, le=1_000_000)
    #: The value the client had on screen for this cell. When present the save
    #: is checked against the stored value first, so concurrent editors get a
    #: conflict instead of silently overwriting one another.
    expected: int | None = Field(default=None, ge=0, le=1_000_000)


class RankCellsIn(BaseModel):
    cells: list[RankCellIn] = []
    #: Whether the client is sending `expected` values it wants enforced. A
    #: client that doesn't set this keeps the old last-write-wins behaviour.
    checkConflicts: bool = False


@router.get("/{project_id}/keyword-ranks", dependencies=[Depends(require_project_access)])
def get_keyword_ranks(
    project_id: int,
    months: str = "",
    db: sqlite3.Connection = Depends(get_db),
):
    wanted = keyword_rank_service.clean_months(months)
    return keyword_rank_service.get_grid(db, project_id, wanted)


@router.put(
    "/{project_id}/keyword-ranks",
    dependencies=[Depends(require_project_access), Depends(require_permission("recordRank"))],
)
def save_keyword_ranks(project_id: int, body: RankCellsIn, db: sqlite3.Connection = Depends(get_db)):
    cells = []
    for c in body.cells:
        cell = {"keywordId": c.keywordId, "month": c.month, "rank": c.rank}
        # Only forward `expected` when the caller actually sent it. Forwarding the
        # default would tell save_cells "this cell was empty", so a client that
        # opted into conflict checking but omitted `expected` on some cells would
        # get a 409 on every cell that isn't empty.
        if body.checkConflicts and "expected" in c.model_fields_set:
            cell["expected"] = c.expected
        cells.append(cell)
    return keyword_rank_service.save_cells(db, project_id, cells)


class RecipientsIn(BaseModel):
    primaryEmail: str
    ccEmails: list[str] = Field(default_factory=list)


@router.get("/{project_id}/recipients", dependencies=[Depends(require_project_access)])
def get_recipients(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """A project's saved report recipients, or null if none are set yet.

    The project and client names come from the join rather than being stored
    alongside the addresses, so a rename can never leave the two disagreeing.
    """
    row = db.execute(
        """SELECT r.primary_email, r.cc_emails, r.updated_at,
                  p.name        AS project_name,
                  p.client_name AS client_name
             FROM project_recipients r
             JOIN projects p ON p.id = r.project_id
            WHERE r.project_id = ?""",
        (project_id,),
    ).fetchone()

    # No row is the ordinary state for a project nobody has set up yet, not an
    # error — the dialog opens blank instead of showing a failure.
    if row is None:
        return {"recipients": None}

    return {
        "recipients": {
            "projectName": row["project_name"],
            "clientName": row["client_name"],
            "primaryEmail": row["primary_email"],
            "ccEmails": row["cc_emails"] or [],
            "updatedAt": row["updated_at"],
        }
    }


@router.put(
    "/{project_id}/recipients",
    dependencies=[Depends(require_project_access), Depends(require_roles(*SENDER_ROLES))],
)
def save_recipients(
    project_id: int,
    body: RecipientsIn,
    db: sqlite3.Connection = Depends(get_db),
):
    """Create or replace a project's saved recipients.

    Gated on SENDER_ROLES: the people who can edit the list are the people who
    can actually send with it.
    """
    if db.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")

    primary, ccs = _clean_recipients(body.primaryEmail, body.ccEmails)
    upsert_project_recipients(db, project_id=project_id, primary=primary, ccs=ccs)
    return {"recipients": {"primaryEmail": primary, "ccEmails": ccs}}


@router.delete(
    "/{project_id}/recipients",
    dependencies=[Depends(require_project_access), Depends(require_roles(*SENDER_ROLES))],
)
def delete_recipients(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Clear a project's saved recipients; the dialog then opens blank.

    Deliberately not a 404 when there was nothing to delete — the caller asked
    for "no saved recipients" and that is now true either way.
    """
    db.execute("DELETE FROM project_recipients WHERE project_id = ?", (project_id,))
    return {"ok": True}
