"""SNAPSHOT SERVICE — freezes the Rank Ledger for a project at a point
in time.

create_snapshot() reads the keywords table's LAST-CHECKED values and
copies them into snapshot_ranks; it never triggers a live rank lookup
(that's check_ranks' job — see rank_provider.py). Every call inserts a
NEW, immutable snapshot — snapshots are no longer one-per-month, so a
month can hold many saves, each distinguished by its created_at
timestamp. period_key/label still group them by month for the UI.
"""
import sqlite3

from fastapi import HTTPException

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _label_for(period_key: str) -> str:
    """"2026-06" -> "June 2026". Falls back to the raw key if it's not
    the expected YYYY-MM shape."""
    try:
        year, month = period_key.split("-")
        return f"{MONTH_NAMES[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return period_key


def create_snapshot(
    db: sqlite3.Connection,
    project_id: int,
    period_key: str | None = None,
    source: str = "manual",
) -> dict:
    """Freeze every keyword's current rank for `project_id` as a NEW
    snapshot. Returns a summary of the saved snapshot.

      404 if the project doesn't exist.

    Always inserts — never overwrites. The same month can be saved any
    number of times; each save is its own row, ordered by created_at.
    """
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    # Default the month server-side so the stored key matches the
    # server clock, not the caller's timezone.
    if not period_key:
        (period_key,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()
    label = _label_for(period_key)

    # Freeze the LAST-CHECKED values — no live lookup here.
    keywords = db.execute(
        "SELECT id, term, current_rank, last_checked FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    # captured_at (day) and created_at (full timestamp) both default in the
    # schema; created_at is what distinguishes multiple saves in one month.
    cur = db.execute(
        "INSERT INTO snapshots (project_id, period_key, label, captured_at, source)"
        " VALUES (?, ?, ?, date('now'), ?)",
        (project_id, period_key, label, source),
    )
    snapshot_id = cur.lastrowid

    for k in keywords:
        # current_rank -> rank (NULL stays NULL); term + last_checked copied.
        db.execute(
            "INSERT INTO snapshot_ranks (snapshot_id, keyword_id, term, rank, last_checked)"
            " VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, k["id"], k["term"], k["current_rank"], k["last_checked"]),
        )

    snap = db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    return {
        "id": snap["id"],
        "period_key": snap["period_key"],
        "label": snap["label"],
        "captured_at": snap["captured_at"],
        "created_at": snap["created_at"],
        "source": snap["source"],
        "locked": snap["locked"],
        "keyword_count": len(keywords),
    }
