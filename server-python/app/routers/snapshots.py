"""SNAPSHOT EXPORT — download a single saved snapshot as CSV.

Lives at /api/snapshots/{id}/... (addressed by snapshot id alone, not nested
under a project) because the menu in the UI downloads a snapshot by its id.
Access is still per-project: we look up the snapshot's project and reuse the
same rule as every /{project_id}/... route (user_can_access_project).
"""
import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from ..access import user_can_access_project
from ..db import get_db
from ..security import require_active_user

router = APIRouter(dependencies=[Depends(require_active_user)])


@router.get("/{snapshot_id}/download")
def download_snapshot(
    snapshot_id: int,
    user: sqlite3.Row = Depends(require_active_user),
    db: sqlite3.Connection = Depends(get_db),
):
    """Return one snapshot's frozen rows as a CSV file. Same per-project
    access rule as the rest of the snapshot endpoints; 404 if it doesn't
    exist, 403 if the caller can't see its project."""
    snap = db.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_id,)).fetchone()
    if snap is None:
        raise HTTPException(404, "Snapshot not found.")
    if not user_can_access_project(user, snap["project_id"], db):
        raise HTTPException(403, "You don't have access to this project.")

    rows = db.execute(
        # Same ordering as the detail view: ranked best-first, never-checked last.
        "SELECT term, rank, last_checked FROM snapshot_ranks WHERE snapshot_id = ?"
        " ORDER BY rank IS NULL, rank ASC, term",
        (snapshot_id,),
    ).fetchall()

    # stdlib csv into an in-memory buffer — no new packages, no temp files.
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Keyword", "Rank", "Last checked"])
    for r in rows:
        writer.writerow([r["term"], "" if r["rank"] is None else r["rank"], r["last_checked"] or ""])

    filename = f"snapshot-{snap['period_key']}-{snapshot_id}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
