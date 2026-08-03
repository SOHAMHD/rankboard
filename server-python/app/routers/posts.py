import re
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..permissions import AUTHOR_ROLES
from ..security import require_active_user, require_project_access, require_roles

router = APIRouter(dependencies=[Depends(require_active_user)])

_KINDS = {"blog", "linkedin"}
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SCHEMES = ("http" + "://", "https" + "://")


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _row(r: sqlite3.Row) -> dict:
    month = r["month"] or (r["created_at"] or "")[:7]
    return {"id": r["id"], "kind": r["kind"], "url": r["url"], "title": r["title"],
            "month": month, "createdAt": r["created_at"]}


class PostIn(BaseModel):
    kind: str
    url: str
    title: str | None = None
    month: str | None = None


@router.get("/{project_id}/posts", dependencies=[Depends(require_project_access)])
def list_posts(project_id: int, kind: str | None = None, month: str | None = None,
               db: sqlite3.Connection = Depends(get_db)):
    if kind is not None and kind not in _KINDS:
        raise HTTPException(400, "Unknown post kind.")
    if month is not None and not _MONTH_RE.match(month):
        raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-07.")
    clauses = ["project_id = ?"]
    params: list = [project_id]
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if month:
        clauses.append("COALESCE(month, substr(created_at, 1, 7)) = ?")
        params.append(month)
    where = " AND ".join(clauses)
    rows = db.execute(
        "SELECT * FROM posts WHERE " + where + " ORDER BY created_at DESC, id DESC",
        tuple(params),
    ).fetchall()
    return {"posts": [_row(r) for r in rows]}


@router.post(
    "/{project_id}/posts",
    status_code=201,
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def add_post(project_id: int, body: PostIn, db: sqlite3.Connection = Depends(get_db)):
    kind = (body.kind or "").strip().lower()
    url = (body.url or "").strip()
    title = (body.title or "").strip() or None
    month = (body.month or "").strip() or _current_month()
    if kind not in _KINDS:
        raise HTTPException(400, "Kind must be 'blog' or 'linkedin'.")
    if not url:
        raise HTTPException(400, "A link is required.")
    if not url.lower().startswith(_SCHEMES):
        raise HTTPException(400, "Enter a full URL starting with http or https.")
    if not _MONTH_RE.match(month):
        raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-07.")
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")
    cur = db.execute(
        "INSERT INTO posts (project_id, kind, url, title, month) VALUES (?, ?, ?, ?, ?)",
        (project_id, kind, url, title, month),
    )
    row = db.execute("SELECT * FROM posts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"post": _row(row)}


@router.delete(
    "/{project_id}/posts/{post_id}",
    dependencies=[Depends(require_project_access), Depends(require_roles(*AUTHOR_ROLES))],
)
def delete_post(project_id: int, post_id: int, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("DELETE FROM posts WHERE id = ? AND project_id = ?", (post_id, project_id))
    if cur.rowcount == 0:
        raise HTTPException(404, "Post not found.")
    return {"ok": True}
