import re

from fastapi import HTTPException

from ..db import INTEGRITY_ERRORS
from .periods import label_for as _label_for

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _valid_month(month: str | None) -> bool:
    return bool(month and _MONTH_RE.match(month))


def _require_project(db, project_id: int) -> None:
    if db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
        raise HTTPException(404, "Project not found.")


def import_backlinks(db, project_id: int, month: str, urls: list[str]) -> dict:
    if not _valid_month(month):
        raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-06.")
    _require_project(db, project_id)

    existing = {
        r["url"]
        for r in db.execute(
            "SELECT url FROM backlinks WHERE project_id = ? AND month = ?",
            (project_id, month),
        ).fetchall()
    }

    to_insert: list[str] = []
    skipped, rejected = 0, 0
    for line in urls or []:
        url = (line or "").strip()
        if not url:
            continue
        if not url.lower().startswith(("http://", "https://")):
            rejected += 1
            continue
        if url in existing:
            skipped += 1
            continue
        existing.add(url)   # also de-dupes repeats inside this one paste
        to_insert.append(url)

    # One round trip instead of one per URL, and atomic. This was an INSERT per
    # URL on an autocommit connection, so a failure partway through a paste of a
    # few hundred links left the earlier ones committed and returned an error —
    # the user then had no way to tell which half had landed.
    #
    # ON CONFLICT DO NOTHING for the same reason as bulk_import_keywords: the
    # `existing` diff above is a read followed by a write, so a concurrent import
    # can slip between them. No conflict target named on purpose — the bare form
    # works whether or not a matching unique index exists on this install.
    added = 0
    if to_insert:
        try:
            with db.transaction():
                cur = db.executemany(
                    "INSERT INTO backlinks (project_id, url, month) VALUES (?, ?, ?)"
                    " ON CONFLICT DO NOTHING",
                    [(project_id, u, month) for u in to_insert],
                )
                added = cur.rowcount if cur.rowcount is not None else len(to_insert)
        except INTEGRITY_ERRORS:
            # Nothing was written — the transaction rolled the whole batch back.
            raise HTTPException(409, "Could not import these backlinks. Try again.")
    skipped += len(to_insert) - added

    return {"month": month, "added": added, "skipped": skipped, "rejected": rejected}


def list_backlinks(db, project_id: int, month: str | None = None) -> list[dict]:
    _require_project(db, project_id)

    if month is not None:
        if not _valid_month(month):
            raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-06.")
        rows = db.execute(
            "SELECT id, url, month, created_at FROM backlinks"
            " WHERE project_id = ? AND month = ? ORDER BY id",
            (project_id, month),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id, url, month, created_at FROM backlinks"
            " WHERE project_id = ? ORDER BY month DESC, id",
            (project_id,),
        ).fetchall()

    groups: list[dict] = []
    index: dict[str, dict] = {}
    for r in rows:
        m = r["month"]
        group = index.get(m)
        if group is None:
            group = {"month": m, "label": _label_for(m), "count": 0, "backlinks": []}
            index[m] = group
            groups.append(group)
        group["backlinks"].append({"id": r["id"], "url": r["url"], "createdAt": r["created_at"]})
        group["count"] += 1
    return groups


def delete_backlink(db, project_id: int, backlink_id: int) -> dict:
    cur = db.execute(
        "DELETE FROM backlinks WHERE id = ? AND project_id = ?",
        (backlink_id, project_id),
    )
    if cur.rowcount == 0:
        raise HTTPException(404, "Backlink not found.")
    return {"ok": True}


def delete_month_backlinks(db, project_id: int, month: str) -> dict:
    if not _valid_month(month):
        raise HTTPException(400, "Month must be in YYYY-MM format, e.g. 2026-06.")
    _require_project(db, project_id)

    cur = db.execute(
        "DELETE FROM backlinks WHERE project_id = ? AND month = ?",
        (project_id, month),
    )
    return {"month": month, "deleted": cur.rowcount or 0}


def backlinks_for_month(db, project_id: int, month: str) -> dict:
    rows = db.execute(
        "SELECT id, url, created_at FROM backlinks"
        " WHERE project_id = ? AND month = ? ORDER BY id",
        (project_id, month),
    ).fetchall()
    return {
        "month": month,
        "count": len(rows),
        "urls": [r["url"] for r in rows],
        "items": [{"id": r["id"], "url": r["url"], "createdAt": r["created_at"]} for r in rows],
    }
