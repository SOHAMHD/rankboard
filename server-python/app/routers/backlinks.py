import sqlite3

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..db import get_db
from ..permissions import AUTHOR_ROLES
from ..security import require_active_user, require_project_access, require_roles
from ..services import backlink_service

router = APIRouter(dependencies=[Depends(require_active_user)])


class BacklinkImportIn(BaseModel):
    month: str
    urls: list[str] = []


@router.post(
    "/{project_id}/backlinks/import",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def import_backlinks(project_id: int, body: BacklinkImportIn, db: sqlite3.Connection = Depends(get_db)):
    return backlink_service.import_backlinks(db, project_id, body.month, body.urls)


@router.get("/{project_id}/backlinks", dependencies=[Depends(require_project_access)])
def list_backlinks(project_id: int, month: str | None = None, db: sqlite3.Connection = Depends(get_db)):
    return {"months": backlink_service.list_backlinks(db, project_id, month)}


@router.delete(
    "/{project_id}/backlinks/month/{month}",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def delete_month_backlinks(project_id: int, month: str, db: sqlite3.Connection = Depends(get_db)):
    return backlink_service.delete_month_backlinks(db, project_id, month)


@router.delete(
    "/{project_id}/backlinks/{backlink_id}",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def delete_backlink(project_id: int, backlink_id: int, db: sqlite3.Connection = Depends(get_db)):
    return backlink_service.delete_backlink(db, project_id, backlink_id)
