import json
import logging
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
        # refresh=True bypasses the 900-second response cache. Without it this
        # endpoint didn't refresh anything: pressing the button twice inside the
        # TTL returned the cached numbers and inserted a second moz_metrics row
        # with identical values and a newer fetched_at. report_service's
        # _pick_prev_moz then chose that duplicate as "previous month", so every
        # Moz delta in the next report rendered as zero.
        metrics = fetch_moz_metrics(project["domain"], refresh=True)
    except MozApiError:
        # The provider's message can carry credential and account detail from
        # Moz's response, so it stays in the log and the caller gets a fixed line.
        logging.getLogger(__name__).exception("Moz refresh failed for project %s", project_id)
        raise HTTPException(502, "Couldn't reach Moz — try again shortly.")

    # A genuinely unchanged reading is not worth a row. Moz updates monthly, so
    # most refreshes return the same figures, and each duplicate is another
    # candidate for _pick_prev_moz to mistake for the previous period.
    latest = db.execute(
        "SELECT * FROM moz_metrics WHERE project_id = ?"
        " ORDER BY fetched_at DESC, id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    if latest is not None and (
        latest["domain_authority"] == metrics["domain_authority"]
        and latest["linking_domains"] == metrics["linking_domains"]
        and latest["inbound_links"] == metrics["inbound_links"]
        and latest["spam_score"] == metrics["spam_score"]
    ):
        # Same response shape as the insert path — the client reads `data`.
        return {"data": row_to_moz(latest), "unchanged": True}

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
