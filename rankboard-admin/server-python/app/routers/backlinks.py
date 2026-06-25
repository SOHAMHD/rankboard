"""BACKLINK ROUTES — per-project backlinks, maintained MONTH-WISE.

Sibling to the Rank Ledger keyword routes. Mounted under /api/projects (like the
moz router), so paths nest as /api/projects/{project_id}/backlinks/...

Auth, per the brief:
  • READS  (list)            — any signed-in user who can see the project
                               (require_project_access).
  • WRITES (import, delete)  — AUTHOR roles only (require_roles(*AUTHOR_ROLES)):
                               Super Admin / Admin / Team. The Client role is
                               VIEW-ONLY. (Note: writes are AUTHOR-gated, NOT the
                               keyword permission matrix — Team may write here.)
"""
import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import get_db
from ..permissions import AUTHOR_ROLES
from ..security import require_active_user, require_project_access, require_roles
from ..services import backlink_service

router = APIRouter(dependencies=[Depends(require_active_user)])


class BacklinkImportIn(BaseModel):
    month: str  # "YYYY-MM" — the month this whole batch belongs to
    urls: list[str] = []  # the pasted lines, already split one-per-line by the client


@router.post(
    "/{project_id}/backlinks/import",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def import_backlinks(project_id: int, body: BacklinkImportIn, db: sqlite3.Connection = Depends(get_db)):
    """Mass-import a month's backlinks. De-dupes within project+month; the same
    URL may exist under a different month. Returns {month, added, skipped}.
    400 on a malformed month, 404 if the project is gone."""
    return backlink_service.import_backlinks(db, project_id, body.month, body.urls)


@router.get("/{project_id}/backlinks", dependencies=[Depends(require_project_access)])
def list_backlinks(project_id: int, month: str | None = None, db: sqlite3.Connection = Depends(get_db)):
    """A project's backlinks grouped by month (newest first) with per-month
    counts. Optional ?month=YYYY-MM filters to one month. Read-only; visible to
    anyone who can see the project."""
    return {"months": backlink_service.list_backlinks(db, project_id, month)}


@router.delete(
    "/{project_id}/backlinks/{backlink_id}",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def delete_backlink(project_id: int, backlink_id: int, db: sqlite3.Connection = Depends(get_db)):
    """Remove a single backlink by id (scoped to its project). 404 if not found."""
    return backlink_service.delete_backlink(db, project_id, backlink_id)
