import concurrent.futures
import json
import sqlite3

from fastapi import HTTPException

from . import backlink_service
from . import report_blobs
from . import report_document
from . import report_google
from . import report_registry as registry
from . import keyword_rank_service

BLOB_SCHEMA_VERSION = 1

UNSENT_STATUSES = ("draft", "in_review")


def _delta(current, previous):
    if current is None or previous is None:
        return None
    return current - previous


def _period_upper_bound(period_key: str) -> str | None:
    try:
        y_str, m_str = period_key.split("-")
        y, m = int(y_str), int(m_str)
    except (ValueError, AttributeError):
        return None
    if m == 12:
        y, m = y + 1, 1
    else:
        m += 1
    return f"{y:04d}-{m:02d}"


#: moz_metrics.raw_json holds the whole Moz API response. Nothing downstream
#: reads it, so it stays out of these queries.
_MOZ_COLS = "id, domain, domain_authority, linking_domains, inbound_links, fetched_at"


def _pick_moz(db, project_id: int, period_key: str):
    bound = _period_upper_bound(period_key)
    if bound is None:
        return db.execute(
            f"SELECT {_MOZ_COLS} FROM moz_metrics WHERE project_id = ?"
            " ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return db.execute(
        f"SELECT {_MOZ_COLS} FROM moz_metrics WHERE project_id = ? AND fetched_at < ?"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id, bound),
    ).fetchone()


def _pick_prev_moz(db, project_id: int, moz):
    if moz is None:
        return None
    return db.execute(
        f"SELECT {_MOZ_COLS} FROM moz_metrics WHERE project_id = ?"
        " AND (fetched_at < ? OR (fetched_at = ? AND id < ?))"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id, moz["fetched_at"], moz["fetched_at"], moz["id"]),
    ).fetchone()


def gather(
    db,
    project_id: int,
    period_key: str | None = None,
    *,
    now=None,
    ga4_fetch=None,
    gsc_fetch=None,
) -> dict:
    ga4_fetch = ga4_fetch or report_google.fetch_ga4
    gsc_fetch = gsc_fetch or report_google.fetch_gsc

    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not period_key:
        (period_key,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()

    prev_period = report_google.previous_period(period_key)
    prev2_period = report_google.previous_period(prev_period)
    moz = _pick_moz(db, project_id, period_key)
    prev_moz = _pick_prev_moz(db, project_id, moz)

    kw_rows = db.execute(
        "SELECT id, term FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    keywords_section = None
    if kw_rows:
        # One lookup shared across the three months. Any term held by more than
        # one keyword is excluded from the term-based fallback below, so a
        # duplicate can't inherit its twin's rank.
        ambiguous = keyword_rank_service.ambiguous_terms(db, project_id)
        cur_m = keyword_rank_service.ranks_for_month(db, project_id, period_key, ambiguous)
        prev_m = keyword_rank_service.ranks_for_month(db, project_id, prev_period, ambiguous)
        prev2_m = keyword_rank_service.ranks_for_month(db, project_id, prev2_period, ambiguous)

        def _rank_of(maps, kw_id, term):
            if kw_id in maps["by_keyword_id"]:
                return maps["by_keyword_id"][kw_id]
            return maps["by_term"].get(term)

        keyword_items = []
        for k in kw_rows:
            kw_id, term = k["id"], k["term"]
            cur = _rank_of(cur_m, kw_id, term)
            prev = _rank_of(prev_m, kw_id, term)
            prev2 = _rank_of(prev2_m, kw_id, term)
            keyword_items.append({
                "term": term,
                "current_rank": cur,
                "previous_rank": prev,
                "previous2_rank": prev2,
                "rank_delta": _delta(cur, prev),
            })

        keyword_items.sort(
            key=lambda it: (it["current_rank"] is None, it["current_rank"] or 0, it["term"])
        )

        keywords_section = {
            "source": registry.SOURCE_KEYWORDS,
            "month": period_key,
            "prev_month": prev_period,
            "prev2_month": prev2_period,
            "items": keyword_items,
        }

    moz_section = None
    if moz is not None:
        da, ld, il = moz["domain_authority"], moz["linking_domains"], moz["inbound_links"]
        p_da = prev_moz["domain_authority"] if prev_moz is not None else None
        p_ld = prev_moz["linking_domains"] if prev_moz is not None else None
        p_il = prev_moz["inbound_links"] if prev_moz is not None else None
        moz_section = {
            "source": registry.SOURCE_MOZ,
            "moz_id": moz["id"],
            "prev_moz_id": prev_moz["id"] if prev_moz is not None else None,
            "fetched_at": moz["fetched_at"],
            "domain": moz["domain"],
            "domain_authority": da,
            "linking_domains": ld,
            "inbound_links": il,
            "deltas": {
                "domain_authority": _delta(da, p_da),
                "linking_domains": _delta(ld, p_ld),
                "inbound_links": _delta(il, p_il),
            },
        }

    prev_period = report_google.previous_period(period_key)
    cur_range = report_google.report_window(period_key, now)
    prev_range = report_google.month_bounds(prev_period)
    period_complete = report_google.period_is_complete(period_key, now)
    period_started = report_google.period_has_started(period_key, now)
    period_in_progress = period_started and not period_complete

    ga4_section = None
    gsc_section = None
    future_reason = (
        f"period {period_key} hasn't started yet — there is no data to report."
    )
    if not period_started:
        ga4_outcome = {"ok": False, "reason": future_reason, "status": 422}
        gsc_outcome = {"ok": False, "reason": future_reason, "status": 422}
    else:
        # GA4 and Search Console are unrelated APIs, so wait on them together
        # rather than one after the other. Each provider caches its client in
        # thread-local storage, so running them on separate threads gives each
        # its own client — no shared, non-thread-safe state.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            ga4_future = pool.submit(
                _fetch_section, ga4_fetch, project["ga_property_id"],
                cur_range, prev_range, registry.SOURCE_GA4,
            )
            gsc_future = pool.submit(
                _fetch_section, gsc_fetch, project["gsc_site_url"],
                cur_range, prev_range, registry.SOURCE_GSC,
            )
            # An outer budget as well as the per-call one inside the fan-out.
            # _fetch_section can't raise, so a timeout here means the whole
            # section's worth of calls overran together — degrade it the same way
            # rather than letting the wait be unbounded.
            ga4_section, ga4_outcome = _await_section(ga4_future, registry.SOURCE_GA4)
            gsc_section, gsc_outcome = _await_section(gsc_future, registry.SOURCE_GSC)

    backlinks_data = backlink_service.backlinks_for_month(db, project_id, period_key)
    # The previous month's count as well, so the Key Metrics tile can show a
    # month-over-month comparison. It used to be hard-coded as absent, which made
    # New backlinks the only metric in that grid with no previous figure.
    prev_backlinks_data = backlink_service.backlinks_for_month(db, project_id, prev_period)
    backlinks_section = {
        "source": "backlinks",
        "month": period_key,
        "count": backlinks_data["count"],
        "prev_month": prev_period,
        "prev_count": prev_backlinks_data["count"],
        "items": [{"url": u} for u in backlinks_data["urls"]],
    }

    post_rows = db.execute(
        "SELECT kind, url, title FROM posts"
        " WHERE project_id = ? AND COALESCE(month, substr(created_at, 1, 7)) = ?"
        " ORDER BY created_at DESC, id DESC",
        (project_id, period_key),
    ).fetchall()
    posts_section = {
        "blogs": [{"url": r["url"], "title": r["title"]} for r in post_rows if r["kind"] == "blog"],
        "linkedin": [{"url": r["url"], "title": r["title"]} for r in post_rows if r["kind"] == "linkedin"],
    }

    blob = {
        "schema_version": BLOB_SCHEMA_VERSION,
        "period_key": period_key,
        "prev_period_key": prev_period,
        "prev2_period_key": prev2_period,
        # `location_code` used to sit here too. Nothing downstream read it —
        # not report_document, not report_blobs, not the PDF templates — so it was
        # copied into every stored report blob and never looked at again.
        "project": {
            "id": project["id"],
            "name": project["name"],
            "domain": project["domain"],
        },
        "rank_snapshot_id": None,
        "period_complete": period_complete,
        "period_in_progress": period_in_progress,
        "sources": {
            "keywords":  {"present": keywords_section is not None,
                          "reason": None if keywords_section is not None else "no keywords added for this project yet"},
            "moz":       {"present": moz is not None,
                          "reason": None if moz is not None else f"no Moz metrics captured for {period_key}"},
            "ga4":       {"present": ga4_outcome["ok"],
                          "reason": None if ga4_outcome["ok"] else ga4_outcome["reason"]},
            "gsc":       {"present": gsc_outcome["ok"],
                          "reason": None if gsc_outcome["ok"] else gsc_outcome["reason"]},
            "backlinks": {"present": True, "reason": None},
            "posts": {"present": True, "reason": None},
        },
        # `ranks` used to sit alongside `keywords` here, holding the same terms
        # and current ranks in a second shape. Nothing ever read it — not
        # report_document, not report_blobs — so it was pure weight in every
        # stored data_json. Older versions still carry it; they render the same,
        # because the renderer never looked at it.
        "sections": {
            "keywords": keywords_section,
            "moz": moz_section,
            "ga4": ga4_section,
            "gsc": gsc_section,
            "backlinks": backlinks_section,
            "posts": posts_section,
        },
        "registry": registry.manifest(),
    }

    return {
        "project_id": project_id,
        "period_key": period_key,
        "rank_snapshot_id": None,
        "snapshot_present": keywords_section is not None,
        "moz_present": moz is not None,
        "period_complete": period_complete,
        "period_in_progress": period_in_progress,
        "ga4_outcome": ga4_outcome,
        "gsc_outcome": gsc_outcome,
        "blob": blob,
    }


#: Wall-clock budget for one provider section, covering all of its calls. Wider
#: than report_google.GA4_CALL_TIMEOUT because a section is many calls; a report
#: that takes longer than this is one nobody is still waiting for.
SECTION_BUDGET = 120


def _await_section(future, source) -> tuple[dict | None, dict]:
    try:
        return future.result(timeout=SECTION_BUDGET)
    except concurrent.futures.TimeoutError:
        return None, {
            "ok": False,
            "reason": f"{source} took longer than {SECTION_BUDGET}s — try generating the report again.",
            "status": 503,
        }


def _fetch_section(fetch, target, cur_range, prev_range, source) -> tuple[dict | None, dict]:
    """Fetch one provider section, or explain why it isn't available.

    Never raises. A report with a missing GA4 section is a report the renderer
    already knows how to draw; a report that 500s because Google was slow is not.
    """
    try:
        section = fetch(target, cur_range, prev_range)
        section["source"] = source
        return section, {"ok": True, "reason": None, "status": 200}
    except report_google.GoogleFetchError as exc:
        status = 503 if exc.retryable else 422
        return None, {"ok": False, "reason": exc.reason_text(), "status": status}
    except concurrent.futures.TimeoutError:
        # Raised by the per-call timeout inside report_google's fan-out. Treated
        # as retryable because that is what it is: the request was fine, Google
        # was slow.
        return None, {
            "ok": False,
            "reason": f"{source} did not respond in time — try generating the report again.",
            "status": 503,
        }
    except Exception as exc:  # noqa: BLE001
        # Anything unforeseen from a third-party client. The section is marked
        # absent with the reason attached rather than taking the whole report
        # down, and the traceback still reaches the log.
        print(f"report {source} fetch failed:", repr(exc))
        return None, {
            "ok": False,
            "reason": f"{source} could not be read ({exc.__class__.__name__}).",
            "status": 502,
        }


def validate(gathered: dict) -> tuple[bool, str | None, int]:
    return True, None, 200


def freeze(db, gathered: dict, user_id: int, content: dict | None = None,
           parent_version_id: int | None = None) -> int:
    data_json = json.dumps(gathered["blob"])
    content_json = json.dumps(content if content is not None else {})
    cur = db.execute(
        "INSERT INTO report_version"
        " (project_id, period_key, status, parent_version_id, data_json, content_json,"
        "  rank_snapshot_id, created_by, frozen_at)"
        " VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, datetime('now'))",
        (
            gathered["project_id"],
            gathered["period_key"],
            parent_version_id,
            data_json,
            content_json,
            gathered["rank_snapshot_id"],
            user_id,
        ),
    )
    return cur.lastrowid


def generate(db, project_id: int, period_key: str | None, user_id: int) -> dict:
    period = period_key
    if not period:
        (period,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()

    placeholders = ",".join("?" * len(UNSENT_STATUSES))
    existing = db.execute(
        f"SELECT id FROM report_version WHERE project_id = ? AND period_key = ?"
        f" AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
        (project_id, period, *UNSENT_STATUSES),
    ).fetchone()
    if existing is not None:
        raise HTTPException(
            409,
            f"an unsent report for {period} exists; use changes to fork it.",
        )

    gathered = gather(db, project_id, period)
    ok, reason, status = validate(gathered)
    if not ok:
        raise HTTPException(status, reason)

    content = report_document.build_document(gathered)
    _seed_header_logo(db, project_id, content)
    version_id = freeze(db, gathered, user_id, content=content)
    return get_version(db, version_id, include_data=True)


def _seed_header_logo(db, project_id: int, content: dict) -> None:
    """Copy the project's client logo into the new report's header block.

    Written into the report rather than looked up when the PDF renders, so a
    report is a fixed record of what was sent: changing a project's logo doesn't
    silently restyle reports a client already received. The editor's own logo
    control edits this same field, so per-report overrides keep working.

    Injected here instead of being carried through the gathered blob on purpose —
    the blob becomes data_json, and routing a ~100 KB data URI through it would
    store the logo twice in every row. content_json is the only copy, and the only
    one anything reads.

    Never overwrites a logo the document already has, so a fork keeps whatever the
    author chose.
    """
    row = db.execute(
        "SELECT client_logo FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    logo = row["client_logo"] if row else None
    if not logo:
        return

    for block in (content or {}).get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "report_header" and not block.get("clientLogo"):
            block["clientLogo"] = logo
            return


def delete_version(db, version_id: int) -> dict:
    row = db.execute(
        "SELECT id, status FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    db.execute("DELETE FROM report_version WHERE id = ?", (version_id,))
    return {"deleted": True, "id": version_id, "status": row["status"]}


def fork_for_changes(db, version_id: int, user_id: int) -> dict:
    src = db.execute("SELECT * FROM report_version WHERE id = ?", (version_id,)).fetchone()
    if src is None:
        raise HTTPException(404, "Report version not found.")

    cur = db.execute(
        "INSERT INTO report_version"
        " (project_id, period_key, status, parent_version_id, data_json, content_json,"
        "  rank_snapshot_id, created_by, frozen_at)"
        " VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, datetime('now'))",
        (
            src["project_id"],
            src["period_key"],
            src["id"],
            src["data_json"],
            src["content_json"],
            src["rank_snapshot_id"],
            user_id,
        ),
    )
    return get_version(db, cur.lastrowid, include_data=True)


def version_to_dict(row, include_data: bool = False) -> dict:
    out = {
        "id": row["id"],
        "projectId": row["project_id"],
        "periodKey": row["period_key"],
        "status": row["status"],
        "parentVersionId": row["parent_version_id"],
        "rankSnapshotId": row["rank_snapshot_id"],
        "createdBy": row["created_by"],
        "createdAt": row["created_at"],
        "frozenAt": row["frozen_at"],
    }
    if include_data:
        out["data"] = json.loads(row["data_json"]) if row["data_json"] else None
        out["content"] = json.loads(row["content_json"]) if row["content_json"] else None
    return out


def get_version(db, version_id: int, include_data: bool = False) -> dict:
    row = db.execute("SELECT * FROM report_version WHERE id = ?", (version_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    return version_to_dict(row, include_data=include_data)


#: Every column version_to_dict() reads when include_data is False. Listing used
#: to be SELECT *, which dragged data_json and content_json — the entire GA4 +
#: GSC payload, hundreds of kilobytes per version — over the wire only for
#: version_to_dict to ignore them.
_VERSION_COLS = (
    "id, project_id, period_key, status, parent_version_id,"
    " rank_snapshot_id, created_by, created_at, frozen_at"
)


def list_versions(db, project_id: int) -> list[dict]:
    rows = db.execute(
        f"SELECT {_VERSION_COLS} FROM report_version WHERE project_id = ?"
        " ORDER BY created_at DESC, id DESC",
        (project_id,),
    ).fetchall()
    return [version_to_dict(r) for r in rows]


def available_blobs(db, version_id: int) -> list[dict]:
    row = db.execute(
        "SELECT data_json FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    data = json.loads(row["data_json"]) if row["data_json"] else None
    return report_blobs.resolve_scalar_blobs(data)


def template_blocks(db, version_id: int) -> list[dict]:
    row = db.execute(
        "SELECT data_json FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    data = json.loads(row["data_json"]) if row["data_json"] else None
    return report_document.build_document_from_data(data)["blocks"]


def save_content(db, version_id: int, content: dict, user_id: int) -> dict:
    row = db.execute(
        "SELECT status FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    if row["status"] != "draft":
        raise HTTPException(
            409,
            f"This report is {row['status']} and locked — only drafts can be edited.",
        )
    db.execute(
        "UPDATE report_version SET content_json = ? WHERE id = ?",
        (json.dumps(content), version_id),
    )
    return get_version(db, version_id, include_data=True)
