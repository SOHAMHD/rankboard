"""POST ROUTES — per-project content links: blog posts + LinkedIn posts.

Mounted under /api/projects (like moz/backlinks), so paths nest as
/api/projects/{project_id}/posts...

Auth:
  • READS (list)          — any signed-in user who can see the project.
  • WRITES (add, delete)  — AUTHOR roles only (Super Admin / Admin / Team);
                            Clients are view-only.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db
from ..permissions import AUTHOR_ROLES
from ..security import require_active_user, require_project_access, require_roles

router = APIRouter(dependencies=[Depends(require_active_user)])

_KINDS = {"blog", "linkedin"}


def _row(r: sqlite3.Row) -> dict:
    return {"id": r["id"], "kind": r["kind"], "url": r["url"], "title": r["title"], "createdAt": r["created_at"]}


class PostIn(BaseModel):
    kind: str
    url: str
    title: str | None = None


@router.get("/{project_id}/posts", dependencies=[Depends(require_project_access)])
def list_posts(project_id: int, kind: str | None = None, db: sqlite3.Connection = Depends(get_db)):
    """A project's posts, newest first. Optional ?kind=blog|linkedin filters."""
    if kind is not None and kind not in _KINDS:
        raise HTTPException(400, "Unknown post kind.")
    if kind:
        rows = db.execute(
            "SELECT * FROM posts WHERE project_id = ? AND kind = ? ORDER BY created_at DESC, id DESC",
            (project_id, kind),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM posts WHERE project_id = ? ORDER BY created_at DESC, id DESC", (project_id,)
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
    if kind not in _KINDS:
        raise HTTPException(400, "Kind must be 'blog' or 'linkedin'.")
    if not url:
        raise HTTPException(400, "A link is required.")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(400, "Enter a full URL starting with http:// or https://.")
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")
    cur = db.execute(
        "INSERT INTO posts (project_id, kind, url, title) VALUES (?, ?, ?, ?)",
        (project_id, kind, url, title),
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
