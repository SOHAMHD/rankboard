"""BACKLINK SERVICE — per-project backlinks, maintained MONTH-WISE.

The SEO team pastes a month's batch of backlink URLs; this assembles/reads them
grouped by month. `month` is "YYYY-MM" — the SAME key format snapshots/reports
use (so the report's backlinks section can filter by period_key).

De-dupe is enforced in CODE per (project_id, month): a URL already present for
that project+month is skipped, never re-inserted and never an error. The SAME
url MAY exist under a DIFFERENT month (URLs repeat across months). The UNIQUE
(project_id, month, url) in the schema only backs this up — a racing duplicate
is caught (INTEGRITY_ERRORS) and counted as skipped, never a 500.

All SQL goes through the db.py bridge (? placeholders) so it runs on both
SQLite and Postgres.
"""
import re

from fastapi import HTTPException

from ..db import INTEGRITY_ERRORS
# Reuse the established "2026-06" -> "June 2026" labeler (same convention as
# snapshots/reports) instead of duplicating the month-name table.
from .snapshot_service import _label_for

# Strict "YYYY-MM" with a real month (01–12).
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _valid_month(month: str | None) -> bool:
    return bool(month and _MONTH_RE.match(month))


def _require_project(db, project_id: int) -> None:
    """404 if the project doesn't exist — mirrors the keyword handlers (the
    per-route access guard deliberately leaves existence to the handler)."""
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")


def import_backlinks(db, project_id: int, month: str, urls: list[str]) -> dict:
    """Mass-import a month's backlinks for a project.

    - Validates `month` is "YYYY-MM" (400 otherwise) and the project exists (404).
    - Trims each URL line; blank lines are skipped silently (not counted).
    - DE-DUPES within project+month: a URL already stored for this project+month
      (or repeated earlier in this same paste) is skipped, not inserted.
    - Returns {month, added, skipped} — skipped = duplicate lines only.
    """
    if not _valid_month(month):
        raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-06.")
    _require_project(db, project_id)

    # Existing URLs for this project+month; grows as we insert so an in-paste
    # repeat is also recognised as a duplicate.
    existing = {
        r["url"]
        for r in db.execute(
            "SELECT url FROM backlinks WHERE project_id = ? AND month = ?",
            (project_id, month),
        ).fetchall()
    }

    added, skipped = 0, 0
    for line in urls or []:
        url = (line or "").strip()
        if not url:
            continue  # blank line — silently ignored, not a "duplicate"
        if url in existing:
            skipped += 1
            continue
        try:
            db.execute(
                "INSERT INTO backlinks (project_id, url, month) VALUES (?, ?, ?)",
                (project_id, url, month),
            )
        except INTEGRITY_ERRORS:
            # UNIQUE(project_id, month, url) lost a race — treat as a duplicate.
            skipped += 1
            continue
        existing.add(url)
        added += 1

    return {"month": month, "added": added, "skipped": skipped}


def list_backlinks(db, project_id: int, month: str | None = None) -> list[dict]:
    """A project's backlinks grouped by month, newest month first; within a month
    a stable insertion order. Pass `month` to filter to a single month.

    Each group: {month, label, count, backlinks: [{id, url, createdAt}, ...]}.
    404 if the project doesn't exist; 400 if `month` is malformed."""
    _require_project(db, project_id)

    if month is not None:
        if not _valid_month(month):
            raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-06.")
        rows = db.execute(
            "SELECT id, url, month, created_at FROM backlinks"
            " WHERE project_id = ? AND month = ? ORDER BY id",
            (project_id, month),
        ).fetchall()
    else:
        # month DESC sorts "YYYY-MM" strings into newest-first chronological order.
        rows = db.execute(
            "SELECT id, url, month, created_at FROM backlinks"
            " WHERE project_id = ? ORDER BY month DESC, id",
            (project_id,),
        ).fetchall()

    groups: list[dict] = []
    index: dict[str, dict] = {}
    for r in rows:
        m = r["month"]
        group = index.get(m)
        if group is None:
            group = {"month": m, "label": _label_for(m), "count": 0, "backlinks": []}
            index[m] = group
            groups.append(group)
        group["backlinks"].append({"id": r["id"], "url": r["url"], "createdAt": r["created_at"]})
        group["count"] += 1
    return groups


def delete_backlink(db, project_id: int, backlink_id: int) -> dict:
    """Delete one backlink by id, scoped to its project (a backlink is only
    removable through its own project). 404 if it doesn't exist there."""
    cur = db.execute(
        "DELETE FROM backlinks WHERE id = ? AND project_id = ?",
        (backlink_id, project_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "Backlink not found.")
    return {"ok": True}


def backlinks_for_month(db, project_id: int, month: str) -> dict:
    """REPORT READ-PATH (additive, standalone): a project's backlinks for ONE
    month (= a report's period_key) plus the COUNT. The report's "new backlinks"
    list and number both come from HERE — separate from moz_metrics.inbound_links.

    Returns {month, count, urls: [...], items: [{id, url, createdAt}, ...]}.
    NOTE: this is intentionally NOT wired into report_service.gather() in this
    slice — see the router/audit notes."""
    rows = db.execute(
        "SELECT id, url, created_at FROM backlinks"
        " WHERE project_id = ? AND month = ? ORDER BY id",
        (project_id, month),
    ).fetchall()
    return {
        "month": month,
        "count": len(rows),
        "urls": [r["url"] for r in rows],
        "items": [{"id": r["id"], "url": r["url"], "createdAt": r["created_at"]} for r in rows],
    }
