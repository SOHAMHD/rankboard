"""MANUAL MONTHLY KEYWORD RANKS — the grid behind the Keywords page.

The team types each keyword's position per month; there is no automated rank
check anywhere in this path. `month` is "YYYY-MM", the same key reports,
backlinks and posts already use, so the report's three-month keyword table is
three reads from one table.

WHY THIS REPLACED SNAPSHOTS
    snapshots/snapshot_ranks existed to FREEZE the output of an automated check at
    a point in time. When a human enters the number for a month, the month IS the
    freeze — a separate snapshot row adds a layer with nothing in it. One row per
    (keyword, month) also makes the grid a straight read instead of a join across
    three snapshot ids.

BLANK IS NOT ZERO, AND NEITHER IS "NOT RANKING"
    rank is nullable and the CHECK enforces >= 1, mirroring the keywords table's
    own constraint. Three distinct states, deliberately:
        a row with rank = 4   -> ranked 4th
        a row with rank NULL  -> recorded, but not in the results
        NO row for that month -> never recorded
    The grid renders the last two differently, and the report's delta arithmetic
    treats both as "no comparison available" rather than as a drop to zero.

All SQL goes through the db.py bridge (? placeholders) so it runs on SQLite and
Postgres alike.
"""
import re

from fastapi import HTTPException

from ..db import INTEGRITY_ERRORS

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _valid_month(month: str | None) -> bool:
    return bool(month and _MONTH_RE.match(month))


def _require_project(db, project_id: int) -> None:
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")


def _clean_rank(value):
    """None / "" / 0 -> None (not recorded or not ranking); otherwise a positive int.

    0 is folded to None on purpose: the spreadsheets this data is pasted from use
    0 for "not ranking", but the column's CHECK requires >= 1, so storing it would
    be rejected. Anything non-numeric is a client bug, not a user typo, so it 400s
    rather than being silently dropped.
    """
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"Rank must be a whole number, got {value!r}.")
    if n <= 0:
        return None
    return n


def get_grid(db, project_id: int, months: list[str]) -> dict:
    """The whole matrix for one project: every keyword, with its rank in each of
    `months`.

    Returns {months, keywords: [{id, term, ranks: {month: rank|None}}]}. A month
    with no stored row is ABSENT from `ranks` (not None), so the client can tell
    "never recorded" from "recorded as not ranking".
    """
    _require_project(db, project_id)
    for m in months:
        if not _valid_month(m):
            raise HTTPException(400, f"Month must be in YYYY-MM format, got {m!r}.")

    kws = db.execute(
        "SELECT id, term FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    # One query for every rank in the project, then bucket in Python. The
    # alternative — a query per month, or per keyword — is the N+1 this avoids.
    rows = db.execute(
        "SELECT r.keyword_id, r.month, r.rank FROM keyword_ranks r"
        " JOIN keywords k ON k.id = r.keyword_id"
        " WHERE k.project_id = ?",
        (project_id,),
    ).fetchall()

    wanted = set(months)
    by_kw: dict[int, dict] = {}
    for r in rows:
        if r["month"] in wanted:
            by_kw.setdefault(r["keyword_id"], {})[r["month"]] = r["rank"]

    return {
        "months": months,
        "keywords": [
            {"id": k["id"], "term": k["term"], "ranks": by_kw.get(k["id"], {})}
            for k in kws
        ],
    }


def save_cells(db, project_id: int, cells: list[dict]) -> dict:
    """Bulk-upsert grid cells. Each cell is {keywordId, month, rank}.

    UPSERT, not replace: only the cells the client sends are touched, so two
    people editing different months can't clobber each other, and a partial save
    (one column, one paste) never blanks the rest of the row.

    Passing rank = None DELETES the row rather than storing NULL, so "I cleared
    this cell" round-trips as "never recorded" — matching what the grid shows.
    Returns {saved, cleared}.
    """
    _require_project(db, project_id)

    # Every keyword id must belong to THIS project. Without this check a caller
    # could write ranks onto another project's keywords by guessing ids — the
    # route's project-access guard only proves access to the project in the URL.
    owned = {
        r["id"]
        for r in db.execute("SELECT id FROM keywords WHERE project_id = ?", (project_id,)).fetchall()
    }

    saved, cleared = 0, 0
    for cell in cells or []:
        kw_id = cell.get("keywordId")
        month = cell.get("month")
        if kw_id not in owned:
            raise HTTPException(400, f"Keyword {kw_id!r} doesn't belong to this project.")
        if not _valid_month(month):
            raise HTTPException(400, f"Month must be in YYYY-MM format, got {month!r}.")

        rank = _clean_rank(cell.get("rank"))
        if rank is None:
            cur = db.execute(
                "DELETE FROM keyword_ranks WHERE keyword_id = ? AND month = ?", (kw_id, month)
            )
            cleared += cur.rowcount or 0
            continue

        # UPDATE-then-INSERT instead of INSERT .. ON CONFLICT: the ON CONFLICT
        # syntax differs between SQLite and Postgres, and everything here has to
        # run on both through the same db.py bridge.
        cur = db.execute(
            "UPDATE keyword_ranks SET rank = ? WHERE keyword_id = ? AND month = ?",
            (rank, kw_id, month),
        )
        if not cur.rowcount:
            try:
                db.execute(
                    "INSERT INTO keyword_ranks (keyword_id, month, rank) VALUES (?, ?, ?)",
                    (kw_id, month, rank),
                )
            except INTEGRITY_ERRORS:
                # Lost a race against a concurrent insert for the same
                # (keyword, month) — the other writer won, so apply ours on top.
                db.execute(
                    "UPDATE keyword_ranks SET rank = ? WHERE keyword_id = ? AND month = ?",
                    (rank, kw_id, month),
                )
        saved += 1

    return {"saved": saved, "cleared": cleared}


def ranks_for_month(db, project_id: int, month: str) -> dict:
    """REPORT READ-PATH: {keyword_id: rank} and {term: rank} for one month.

    Two maps because a keyword has to stay matched across three months even if it
    was renamed (match on id) or deleted and re-added (match on term) — the same
    belt-and-braces the snapshot reader used.
    """
    if not _valid_month(month):
        raise HTTPException(400, f"Month must be in YYYY-MM format, got {month!r}.")
    rows = db.execute(
        "SELECT r.keyword_id, k.term, r.rank FROM keyword_ranks r"
        " JOIN keywords k ON k.id = r.keyword_id"
        " WHERE k.project_id = ? AND r.month = ?",
        (project_id, month),
    ).fetchall()
    by_kw = {r["keyword_id"]: r["rank"] for r in rows}
    by_term = {r["term"]: r["rank"] for r in rows}
    return {"by_keyword_id": by_kw, "by_term": by_term, "count": len(rows)}
