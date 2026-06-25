"""REPORT SERVICE — the gather → validate → freeze pipeline plus generate/fork.

This is the DATA FOUNDATION for reports. It produces a FROZEN, versioned report
record from data ALREADY IN THE DB — it never makes a live external call (no
DataForSEO, no Moz, no GA4/GSC). Ranks come from a saved snapshot's
snapshot_ranks; Moz from the period's moz_metrics row; the keyword comparison
from those same frozen ranks.

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
def gather(db, project_id: int, period_key: str | None = None) -> dict:
    """Assemble the frozen report data from the DB ONLY (no live fetches). Returns
    an in-memory structure — writes NOTHING. Computes month-over-month deltas
    now (DA change, per-keyword rank change) so they're stored, not recomputed
    at render time.

    The returned dict carries both the `blob` to be frozen and presence flags
    validate() reads to tell "legitimately empty" apart from "section absent".
    404 if the project doesn't exist."""
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

    blob = {
        "schema_version": BLOB_SCHEMA_VERSION,
        "period_key": period_key,
        "project": {
            "id": project["id"],
            "name": project["name"],
            "domain": project["domain"],
            "location_code": project["location_code"],
        },
        "rank_snapshot_id": snap["id"] if snap is not None else None,
        # Per-section presence + deferred markers. A deferred section being
        # absent is EXPECTED this slice and never fails validation.
        "sources": {
            "ranks":    {"present": snap is not None, "deferred": False},
            "keywords": {"present": snap is not None, "deferred": False},
            "moz":      {"present": moz is not None,  "deferred": False},
            "ga4":      {"present": False, "deferred": True},
            "gsc":      {"present": False, "deferred": True},
        },
        "sections": {
            "ranks": ranks_section,
            "keywords": keywords_section,
            "moz": moz_section,
            "ga4": None,   # registered-but-deferred: wired in a later slice
            "gsc": None,   # registered-but-deferred: wired in a later slice
        },
        "registry": registry.manifest(),
    }

    return {
        "project_id": project_id,
        "period_key": period_key,
        "rank_snapshot_id": snap["id"] if snap is not None else None,
        "snapshot_present": snap is not None,
        "moz_present": moz is not None,
        "blob": blob,
    }


# ── validate ──────────────────────────────────────────────────────────────────
def validate(gathered: dict) -> tuple[bool, str | None]:
    """STRICT validation. Returns (True, None) when the blob may be frozen, or
    (False, reason) with a specific, human-readable reason when it may not.

    Rules:
      • A usable rank snapshot MUST exist for the period (else: run a rank check
        / save a snapshot first).
      • A Moz row for the period MUST be present.
      • An ABSENT non-deferred section fails; a section that's present but
        legitimately EMPTY (e.g. a snapshot of a project with zero keywords, or
        a real Moz 0) is valid data and does NOT fail.
      • GA4/GSC (source='deferred') are SKIPPED — their absence never fails
        generation in this slice.
    """
    period = gathered["period_key"]
    if not gathered["snapshot_present"]:
        return False, f"no rank snapshot for {period}; run a rank check first."
    if not gathered["moz_present"]:
        return False, f"no Moz metrics for {period}; refresh Moz for this project first."
    return True, None


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

      404 unknown project · 409 unsent version already exists · 422 not freezable
    """
    gathered = gather(db, project_id, period_key)
    period = gathered["period_key"]

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

    ok, reason = validate(gathered)
    if not ok:
        raise HTTPException(422, reason)

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
