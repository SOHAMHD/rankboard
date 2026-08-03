import sqlite3

from fastapi import HTTPException

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _label_for(period_key: str) -> str:
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
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")

    if not period_key:
        (period_key,) = db.execute("SELECT strftime('%Y-%m','now')").fetchone()
    label = _label_for(period_key)

    keywords = db.execute(
        "SELECT id, term, current_rank, last_checked FROM keywords WHERE project_id = ? ORDER BY created_at, id",
        (project_id,),
    ).fetchall()

    cur = db.execute(
        "INSERT INTO snapshots (project_id, period_key, label, captured_at, source)"
        " VALUES (?, ?, ?, date('now'), ?)",
        (project_id, period_key, label, source),
    )
    snapshot_id = cur.lastrowid

    if keywords:
        db.executemany(
            "INSERT INTO snapshot_ranks (snapshot_id, keyword_id, term, rank, last_checked)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (snapshot_id, k["id"], k["term"], k["current_rank"], k["last_checked"])
                for k in keywords
            ],
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
