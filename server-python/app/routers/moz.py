import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..db import get_db
from ..security import require_active_user, require_permission, require_project_access
from ..services.moz_provider import MozApiError, fetch_moz_metrics

router = APIRouter(dependencies=[Depends(require_active_user)])


def row_to_moz(row: sqlite3.Row) -> dict:
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
