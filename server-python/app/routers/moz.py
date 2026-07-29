"""MOZ ROUTES — per-project domain Authority overview from the Moz API.

Two endpoints, mirroring the cache-then-refresh pattern the feature needs
(Moz's quota is tiny, so we never call it on a plain page load):

  GET  /api/projects/{id}/moz          -> the most recent STORED row (no Moz call)
  POST /api/projects/{id}/moz/refresh  -> call Moz, store a new row, return it

The refresh is the only path that spends quota, and it fails gracefully — a bad
token or a Moz outage comes back as a 502 with a readable message, never a 500.
"""
import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..security import require_active_user, require_permission, require_project_access
from ..services.moz_provider import MozApiError, fetch_moz_metrics

router = APIRouter(dependencies=[Depends(require_active_user)])


def row_to_moz(row: sqlite3.Row) -> dict:
    """One moz_metrics row → the camelCase shape the client reads (raw_json is
    debug-only and intentionally NOT exposed)."""
    return {
        "domain": row["domain"],
        "domainAuthority": row["domain_authority"],
        "linkingDomains": row["linking_domains"],
        "inboundLinks": row["inbound_links"],
        "spamScore": row["spam_score"],
        "fetchedAt": row["fetched_at"],
    }


@router.get("/{project_id}/moz", dependencies=[Depends(require_project_access)])
def get_moz(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """The most recent stored Moz row for the project, or {"data": null} when
    none exists yet. Never calls Moz — cached values only."""
    project = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    row = db.execute(
        "SELECT * FROM moz_metrics WHERE project_id = ? ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    return {"data": row_to_moz(row) if row else None}


@router.post(
    "/{project_id}/moz/refresh",
    dependencies=[Depends(require_project_access), Depends(require_permission("addKeyword"))],
)
def refresh_moz(project_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Look up the project's domain on Moz, store a NEW moz_metrics row, and
    return the freshly stored values. Gated by the same write right as the rank
    check (it's the other on-demand external pull). On any Moz failure → 502
    with a readable message so the app never 500-crashes."""
    project = db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if project is None:
        raise HTTPException(404, "Project not found.")
    if not project["domain"]:
        raise HTTPException(400, "This project has no domain set, so there's nothing to look up on Moz.")

    try:
        metrics = fetch_moz_metrics(project["domain"])
    except MozApiError as exc:
        raise HTTPException(502, str(exc))

    fetched_at = datetime.now(timezone.utc).isoformat()
    # ranking_keywords is intentionally left NULL: Moz exposes no keyword-count
    # method, so the provider no longer fetches it (see moz_provider). The column
    # is kept (nullable) so existing rows and the schema are undisturbed.
    cur = db.execute(
        """INSERT INTO moz_metrics
             (project_id, domain, domain_authority, linking_domains, inbound_links,
              spam_score, raw_json, fetched_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            project_id,
            metrics["domain"],
            metrics["domain_authority"],
            metrics["linking_domains"],
            metrics["inbound_links"],
            metrics["spam_score"],
            json.dumps(metrics["raw"]),
            fetched_at,
        ),
    )
    row = db.execute("SELECT * FROM moz_metrics WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"data": row_to_moz(row)}
