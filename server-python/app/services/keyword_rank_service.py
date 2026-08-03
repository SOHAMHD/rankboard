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
    _require_project(db, project_id)
    for m in months:
        if not _valid_month(m):
            raise HTTPException(400, f"Month must be in YYYY-MM format, got {m!r}.")

    kws = db.execute(
        "SELECT id, term FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    # The month filter used to be applied in Python after fetching the project's
    # entire rank history. Pushing it into SQL keeps the payload proportional to
    # what was asked for and lets idx_keyword_ranks_month do some work.
    placeholders = ", ".join("?" for _ in months) or "NULL"
    rows = db.execute(
        "SELECT r.keyword_id, r.month, r.rank FROM keyword_ranks r"
        " JOIN keywords k ON k.id = r.keyword_id"
        f" WHERE k.project_id = ? AND r.month IN ({placeholders})",
        (project_id, *months),
    ).fetchall()

    by_kw: dict[int, dict] = {}
    for r in rows:
        by_kw.setdefault(r["keyword_id"], {})[r["month"]] = r["rank"]

    return {
        "months": months,
        "keywords": [
            {"id": k["id"], "term": k["term"], "ranks": by_kw.get(k["id"], {})}
            for k in kws
        ],
    }


def save_cells(db, project_id: int, cells: list[dict]) -> dict:
    _require_project(db, project_id)

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
                db.execute(
                    "UPDATE keyword_ranks SET rank = ? WHERE keyword_id = ? AND month = ?",
                    (rank, kw_id, month),
                )
        saved += 1

    return {"saved": saved, "cleared": cleared}


def ranks_for_month(db, project_id: int, month: str) -> dict:
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
