"""REPORT SERVICE — the gather → validate → freeze pipeline plus generate/fork.

This is the DATA FOUNDATION for reports. Ranks/Moz/keywords come from data ALREADY
IN THE DB (a saved snapshot's snapshot_ranks; the period's moz_metrics row; the
keyword comparison from those frozen ranks) — generation NEVER makes a live rank
call. GA4 + GSC are the exception: they are fetched LIVE from Google at generate
time (see report_google.py) and then FROZEN into the blob, identical in treatment
to ranks/Moz once gathered. Forking reuses the frozen blob and never re-fetches.

  gather()           assemble the in-memory blob (+ month-over-month deltas)
  validate()         STRICT yes/no with a human-readable reason — writes nothing
  freeze()           the ONLY writer: serialise the blob into a report_version row
  generate()         gather → validate → freeze, with a no-duplicate guard
  fork_for_changes() copy a frozen version verbatim into a new editable draft

All SQL goes through the db.py bridge (SQLite-dialect, `?` placeholders) so it
runs on both SQLite and Supabase Postgres.
"""
import json
import sqlite3

from fastapi import HTTPException

from . import report_blobs
from . import report_google
from . import report_registry as registry

# Blob schema version — bump if the frozen structure changes so a later reader
# can branch on it.
BLOB_SCHEMA_VERSION = 1

# A non-sent version of a report already owns the project+period; generate must
# not silently make a second. (Sent versions are historical and don't block.)
UNSENT_STATUSES = ("draft", "in_review")


# ── small helpers ─────────────────────────────────────────────────────────────
def _delta(current, previous):
    """Raw arithmetic change `current - previous`, or None when either side is
    missing. Stored as-is: for RANK fields a NEGATIVE delta is an IMPROVEMENT
    (the position number got smaller); for count fields positive is growth. The
    render slice interprets direction per field type — we only store the number."""
    if current is None or previous is None:
        return None
    return current - previous


def _period_upper_bound(period_key: str) -> str | None:
    """ "2026-06" -> "2026-07" (exclusive upper bound = first day of next month).
    Used to pick the Moz row captured at-or-before the period's end: an ISO
    `fetched_at` string sorts lexicographically, and any "2026-06-..T.." < the
    "2026-07" bound while any "2026-07-..T.." is not. None if the key isn't the
    expected YYYY-MM shape (caller then falls back to the latest Moz row)."""
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


# ── source pickers (all read-only) ────────────────────────────────────────────
def _pick_snapshot(db, project_id: int, period_key: str):
    """The usable rank snapshot for this project+period: the LATEST one saved for
    the month (snapshots are not one-per-month). None if the month was never
    saved. `locked` is intentionally NOT required — nothing in the codebase ever
    sets it to 1, so it's an informational flag; a snapshot is usable by virtue
    of existing with its frozen snapshot_ranks rows."""
    return db.execute(
        "SELECT * FROM snapshots WHERE project_id = ? AND period_key = ?"
        " ORDER BY created_at DESC, id DESC LIMIT 1",
        (project_id, period_key),
    ).fetchone()


def _pick_prev_snapshot(db, project_id: int, snap):
    """The snapshot immediately BEFORE `snap` chronologically (any period) — the
    month-over-month baseline for rank deltas. None if `snap` is the first."""
    if snap is None:
        return None
    return db.execute(
        "SELECT * FROM snapshots WHERE project_id = ?"
        " AND (created_at < ? OR (created_at = ? AND id < ?))"
        " ORDER BY created_at DESC, id DESC LIMIT 1",
        (project_id, snap["created_at"], snap["created_at"], snap["id"]),
    ).fetchone()


def _pick_moz(db, project_id: int, period_key: str):
    """The Moz row for the period: the latest refresh captured AT OR BEFORE the
    period's end (fetched_at < first day of next month). Falls back to the
    latest Moz row overall when the period key isn't YYYY-MM. None if the
    project has no Moz history at all."""
    bound = _period_upper_bound(period_key)
    if bound is None:
        return db.execute(
            "SELECT * FROM moz_metrics WHERE project_id = ?"
            " ORDER BY fetched_at DESC, id DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return db.execute(
        "SELECT * FROM moz_metrics WHERE project_id = ? AND fetched_at < ?"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id, bound),
    ).fetchone()


def _pick_prev_moz(db, project_id: int, moz):
    """The Moz row immediately BEFORE `moz` — the baseline for DA / link deltas.
    None if `moz` is the project's first refresh."""
    if moz is None:
        return None
    return db.execute(
        "SELECT * FROM moz_metrics WHERE project_id = ?"
        " AND (fetched_at < ? OR (fetched_at = ? AND id < ?))"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id, moz["fetched_at"], moz["fetched_at"], moz["id"]),
    ).fetchone()


# ── gather ────────────────────────────────────────────────────────────────────
def gather(
    db,
    project_id: int,
    period_key: str | None = None,
    *,
    now=None,
    ga4_fetch=None,
    gsc_fetch=None,
) -> dict:
    """Assemble the frozen report data: ranks/Moz/keywords from the DB, GA4 + GSC
    fetched LIVE from Google for the report month AND prior month, then folded into
    the same in-memory structure that gets frozen. Computes month-over-month deltas
    now (DA, per-keyword rank, GA4 overview, GSC totals) so they're stored, not
    recomputed at render time. Writes NOTHING.

    The returned dict carries the `blob` plus presence flags + per-source outcomes
    validate() reads to tell "legitimately empty" (freeze it) from "absent /
    access-failed / transport-failed" (fail, with the specific reason). 404 if the
    project doesn't exist.

    `now` (for the maturation guard) and `ga4_fetch`/`gsc_fetch` are injectable for
    testing; production uses the real clock and report_google fetchers."""
    # Resolve the live fetchers at call time (so tests can monkeypatch them on
    # report_google); production uses the real GA4/GSC fetchers.
    ga4_fetch = ga4_fetch or report_google.fetch_ga4
    gsc_fetch = gsc_fetch or report_google.fetch_gsc

    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    # Default the month server-side (same convention as snapshot_service).
    if not period_key:
        (period_key,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()

    snap = _pick_snapshot(db, project_id, period_key)
    prev_snap = _pick_prev_snapshot(db, project_id, snap)
    moz = _pick_moz(db, project_id, period_key)
    prev_moz = _pick_prev_moz(db, project_id, moz)

    # ── ranks + keywords (both from the chosen snapshot's frozen rows) ─────────
    ranks_section = None
    keywords_section = None
    if snap is not None:
        rank_rows = db.execute(
            "SELECT keyword_id, term, rank, last_checked FROM snapshot_ranks"
            " WHERE snapshot_id = ? ORDER BY rank IS NULL, rank ASC, term",
            (snap["id"],),
        ).fetchall()

        # Previous-period ranks, keyed by keyword_id (preferred) then term, so a
        # keyword still matches across months even if its id changed.
        prev_by_kw, prev_by_term = {}, {}
        if prev_snap is not None:
            for r in db.execute(
                "SELECT keyword_id, term, rank FROM snapshot_ranks WHERE snapshot_id = ?",
                (prev_snap["id"],),
            ).fetchall():
                if r["keyword_id"] is not None:
                    prev_by_kw[r["keyword_id"]] = r["rank"]
                prev_by_term[r["term"]] = r["rank"]

        rank_items, keyword_items = [], []
        for r in rank_rows:
            cur = r["rank"]
            if r["keyword_id"] is not None and r["keyword_id"] in prev_by_kw:
                prev = prev_by_kw[r["keyword_id"]]
            else:
                prev = prev_by_term.get(r["term"])
            rank_items.append({
                "term": r["term"],
                "rank": cur,                       # None = never checked when frozen
                "last_checked": r["last_checked"],
            })
            keyword_items.append({
                "term": r["term"],
                "current_rank": cur,
                "previous_rank": prev,             # None = no prior snapshot / new keyword
                "rank_delta": _delta(cur, prev),   # current - previous (negative = improved)
            })

        ranks_section = {
            "source": registry.SOURCE_SNAPSHOT_RANKS,
            "snapshot_id": snap["id"],
            "snapshot_label": snap["label"],
            "captured_at": snap["captured_at"],
            "items": rank_items,
        }
        keywords_section = {
            "source": registry.SOURCE_KEYWORDS,
            "snapshot_id": snap["id"],
            "prev_snapshot_id": prev_snap["id"] if prev_snap is not None else None,
            "items": keyword_items,
        }

    # ── moz (with deltas vs the previous refresh) ─────────────────────────────
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

    # ── GA4 + GSC (fetched LIVE from Google, then frozen) ─────────────────────
    # Maturation guard FIRST: never fetch (or freeze) an incomplete/future month —
    # GA4 data is still settling. A complete past month proceeds to fetch.
    prev_period = report_google.previous_period(period_key)
    cur_range = report_google.month_bounds(period_key)
    prev_range = report_google.month_bounds(prev_period)
    period_complete = report_google.period_is_complete(period_key, now)

    ga4_section = None
    gsc_section = None
    # outcome: {"ok", "reason", "status"} — status drives generate's HTTP code
    # (422 = fix it / access / maturation; 503 = transport, retryable).
    maturation_reason = (
        f"period {period_key} is not a complete past month; GA4 data still maturing"
        " — generate after the month closes."
    )
    # Only spend GA4/GSC API quota when the cheaper prerequisites already hold:
    # a snapshot + Moz must be present (else validate() fails on those first) AND
    # the month must be complete (else we'd freeze immature data). When skipped,
    # the outcome's reason is never surfaced — validate() reports the real cause.
    prerequisites_ok = snap is not None and moz is not None
    if not prerequisites_ok:
        skip = {"ok": False, "reason": "not fetched (snapshot/Moz prerequisite missing)", "status": 422}
        ga4_outcome = dict(skip)
        gsc_outcome = dict(skip)
    elif not period_complete:
        ga4_outcome = {"ok": False, "reason": maturation_reason, "status": 422}
        gsc_outcome = {"ok": False, "reason": maturation_reason, "status": 422}
    else:
        ga4_section, ga4_outcome = _fetch_section(
            ga4_fetch, project["ga_property_id"], cur_range, prev_range, registry.SOURCE_GA4
        )
        gsc_section, gsc_outcome = _fetch_section(
            gsc_fetch, project["gsc_site_url"], cur_range, prev_range, registry.SOURCE_GSC
        )

    blob = {
        "schema_version": BLOB_SCHEMA_VERSION,
        "period_key": period_key,
        "prev_period_key": prev_period,
        "project": {
            "id": project["id"],
            "name": project["name"],
            "domain": project["domain"],
            "location_code": project["location_code"],
        },
        "rank_snapshot_id": snap["id"] if snap is not None else None,
        # Per-section presence. Nothing is deferred any more — GA4/GSC are real
        # sources whose absence fails validation.
        "sources": {
            "ranks":    {"present": snap is not None, "deferred": False},
            "keywords": {"present": snap is not None, "deferred": False},
            "moz":      {"present": moz is not None,  "deferred": False},
            "ga4":      {"present": ga4_outcome["ok"], "deferred": False},
            "gsc":      {"present": gsc_outcome["ok"], "deferred": False},
        },
        "sections": {
            "ranks": ranks_section,
            "keywords": keywords_section,
            "moz": moz_section,
            "ga4": ga4_section,   # live-fetched + frozen (None when the fetch failed)
            "gsc": gsc_section,   # live-fetched + frozen (None when the fetch failed)
        },
        "registry": registry.manifest(),
    }

    return {
        "project_id": project_id,
        "period_key": period_key,
        "rank_snapshot_id": snap["id"] if snap is not None else None,
        "snapshot_present": snap is not None,
        "moz_present": moz is not None,
        "period_complete": period_complete,
        "ga4_outcome": ga4_outcome,
        "gsc_outcome": gsc_outcome,
        "blob": blob,
    }


def _fetch_section(fetch, target, cur_range, prev_range, source) -> tuple[dict | None, dict]:
    """Run one live Google fetch, classifying the outcome into the three cases.
    Returns (section_dict_or_None, outcome). SUCCESS (incl. a legitimate empty/
    zero result) → the section + ok outcome; GoogleAccessError → 422 (fix access);
    GoogleTransportError → 503 (retryable). The specific reason naming the API +
    property is carried straight from the exception."""
    try:
        section = fetch(target, cur_range, prev_range)
        section["source"] = source
        return section, {"ok": True, "reason": None, "status": 200}
    except report_google.GoogleFetchError as exc:
        status = 503 if exc.retryable else 422
        return None, {"ok": False, "reason": exc.reason_text(), "status": status}


# ── validate ──────────────────────────────────────────────────────────────────
def validate(gathered: dict) -> tuple[bool, str | None, int]:
    """STRICT validation. Returns (True, None, 200) when the blob may be frozen, or
    (False, reason, http_status) with a specific, human-readable reason when it may
    not. A report freezes ONLY if ranks + Moz + GA4 + GSC all gathered successfully.

    Rules:
      • A usable rank snapshot MUST exist for the period (else 422: run a rank check).
      • A Moz row for the period MUST be present (else 422).
      • The period MUST be a complete past month (else 422: GA4 still maturing) —
        we never freeze unsettled GA4/GSC data.
      • GA4 and GSC MUST have fetched successfully. An ACCESS failure (403 / wrong
        property / missing creds) → 422 with which-API/which-property reason; a
        TRANSPORT failure (timeout/5xx/network) → 503 with a retryable reason.
      • An ABSENT section fails; a section present but legitimately EMPTY (zero
        keywords, a real Moz 0, a new site with 0 GSC clicks) is valid — zero is
        data, not failure.
    """
    period = gathered["period_key"]
    if not gathered["snapshot_present"]:
        return False, f"no rank snapshot for {period}; run a rank check first.", 422
    if not gathered["moz_present"]:
        return False, f"no Moz metrics for {period}; refresh Moz for this project first.", 422
    if not gathered["period_complete"]:
        return (
            False,
            f"period {period} is not a complete past month; GA4 data still maturing"
            " — generate after the month closes.",
            422,
        )
    ga4 = gathered["ga4_outcome"]
    if not ga4["ok"]:
        return False, ga4["reason"], ga4["status"]
    gsc = gathered["gsc_outcome"]
    if not gsc["ok"]:
        return False, gsc["reason"], gsc["status"]
    return True, None, 200


# ── freeze (the only writer) ──────────────────────────────────────────────────
def freeze(db, gathered: dict, user_id: int, parent_version_id: int | None = None) -> int:
    """Serialise the gathered blob into a NEW report_version row (status 'draft',
    frozen_at set, rank_snapshot_id recorded, content_json empty) and return its
    id. ONLY call after validate() passed — freeze never re-validates. `frozen_at`
    uses datetime('now') (bridge-translated) so it matches house timestamp text
    on both backends; created_at takes its column default."""
    data_json = json.dumps(gathered["blob"])
    cur = db.execute(
        "INSERT INTO report_version"
        " (project_id, period_key, status, parent_version_id, data_json, content_json,"
        "  rank_snapshot_id, created_by, frozen_at)"
        " VALUES (?, ?, 'draft', ?, ?, '{}', ?, ?, datetime('now'))",
        (
            gathered["project_id"],
            gathered["period_key"],
            parent_version_id,
            data_json,
            gathered["rank_snapshot_id"],
            user_id,
        ),
    )
    return cur.lastrowid


# ── operations ────────────────────────────────────────────────────────────────
def generate(db, project_id: int, period_key: str | None, user_id: int) -> dict:
    """Generate a fresh frozen version for a project+period: gather → validate →
    freeze. Fails LOUDLY (writes nothing) when validation fails. Enforces the
    no-duplicate rule in code: if a non-sent (draft/in_review) version already
    exists for this project+period, returns a 409 conflict rather than silently
    making a second — use fork_for_changes to iterate on it instead.

      404 unknown project · 409 unsent version already exists ·
      422 not freezable (missing snapshot/Moz, immature period, GA4/GSC access) ·
      503 GA4/GSC transport error (retryable)
    """
    # Resolve the period up front so the duplicate check runs BEFORE any live
    # Google fetch — a known conflict must not spend GA4/GSC API calls.
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

    # No conflict → gather (this is where GA4/GSC are fetched live) then validate.
    gathered = gather(db, project_id, period)
    ok, reason, status = validate(gathered)
    if not ok:
        raise HTTPException(status, reason)

    version_id = freeze(db, gathered, user_id)
    return get_version(db, version_id, include_data=True)


def fork_for_changes(db, version_id: int, user_id: int) -> dict:
    """"Changes" == same frozen data, new editable file. Create a NEW
    report_version that COPIES the source's data_json AND content_json verbatim
    (forking never re-gathers or re-fetches — the data stays frozen), status
    'draft', parent_version_id = source id. The source row is untouched.

      404 if the source version doesn't exist.
    """
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
            src["data_json"],     # frozen data copied verbatim
            src["content_json"],  # editable layer copied verbatim
            src["rank_snapshot_id"],
            user_id,
        ),
    )
    return get_version(db, cur.lastrowid, include_data=True)


# ── reads / shaping ───────────────────────────────────────────────────────────
def version_to_dict(row, include_data: bool = False) -> dict:
    """One report_version row → the camelCase shape the API returns (matching the
    rest of the app). data_json/content_json are parsed back to objects only
    when include_data is set (the list view omits the heavy blob)."""
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
    """Fetch a single version (404 if missing). include_data returns the frozen
    data_json + content_json blobs for inspection."""
    row = db.execute("SELECT * FROM report_version WHERE id = ?", (version_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    return version_to_dict(row, include_data=include_data)


def list_versions(db, project_id: int) -> list[dict]:
    """All versions for a project, newest first — metadata only (no blob)."""
    rows = db.execute(
        "SELECT * FROM report_version WHERE project_id = ?"
        " ORDER BY created_at DESC, id DESC",
        (project_id,),
    ).fetchall()
    return [version_to_dict(r) for r in rows]


# ── content editor support (this slice) ───────────────────────────────────────
def available_blobs(db, version_id: int) -> list[dict]:
    """The SCALAR blobs an author can insert into this version, resolved from its
    FROZEN data_json (single source for the palette AND the live preview). 404 if
    the version doesn't exist. No live fetch — frozen values only."""
    row = db.execute(
        "SELECT data_json FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    data = json.loads(row["data_json"]) if row["data_json"] else None
    return report_blobs.resolve_scalar_blobs(data)


def save_content(db, version_id: int, content: dict, user_id: int) -> dict:
    """Persist the editor's document into content_json. DRAFT-ONLY: a version in
    'in_review' or 'sent' is LOCKED — 409 if a write is attempted (enforces the
    "locked once submitted" rule at the data layer, even though submit isn't built
    yet). 404 if the version doesn't exist.

    `content` is the editor's structured document (TipTap/ProseMirror JSON: prose
    + atomic blob references carrying {name, kind, format}) — NOT rendered HTML —
    so reopening restores chips with their formats and resolution stays dynamic."""
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
