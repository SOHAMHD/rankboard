"""REPORT ROUTES — trigger and inspect frozen report versions.

This slice is the DATA FOUNDATION: generate a frozen version, fork one for
changes, list a project's versions, and fetch one version's frozen blob to
INSPECT it. There is NO rendering, sending, status-transition-to-sent, or public
link here — those are later slices.

Every endpoint is gated to report AUTHORS (require_roles(*AUTHOR_ROLES)); since
the author roles are all staff, they already reach every project, so no extra
per-project access check is needed.
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import get_db
from ..permissions import AUTHOR_ROLES
from ..security import require_roles
from ..services import report_service

router = APIRouter()


class GenerateIn(BaseModel):
    projectId: int
    periodKey: str | None = None  # defaults to the current month server-side


@router.post("/generate", status_code=201)
def generate_report(
    body: GenerateIn,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Generate a fresh frozen report version for a project+period.

    gather → validate → freeze. Fails loudly (writes nothing) when no usable
    rank snapshot or Moz row exists for the period (422), or when an unsent
    version already exists for that project+period (409 — fork it instead).
    Returns the new version including its frozen data blob."""
    version = report_service.generate(db, body.projectId, body.periodKey, user["id"])
    return {"version": version}


@router.post("/{version_id}/fork", status_code=201)
def fork_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Fork a version for "changes": a new draft that copies the source's frozen
    data and editable content verbatim (never re-gathers), with
    parentVersionId set to the source. 404 if the source doesn't exist."""
    version = report_service.fork_for_changes(db, version_id, user["id"])
    return {"version": version}


@router.get("")
def list_reports(
    projectId: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """List a project's report versions, newest first (metadata only: id,
    period, status, parent, created_at — no blob)."""
    return {"versions": report_service.list_versions(db, projectId)}


@router.get("/{version_id}")
def get_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Fetch one version's frozen data_json (and empty content_json) so a frozen
    report can be INSPECTED this slice — no rendering, just the stored blob.
    404 if the version doesn't exist."""
    version = report_service.get_version(db, version_id, include_data=True)
    return {"version": version}
