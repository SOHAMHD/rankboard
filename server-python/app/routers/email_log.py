"""The Email Log — every message the system has sent, and what became of it.

Super Admin only, enforced at the router level so a route added later can't
forget the check. See `_redact` for the one thing even a Super Admin can't read.
"""

import re
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..security import require_permission
from ..services.email_tracking import (
    CATEGORIES,
    DELIVERED_STATUSES,
    LIST_STATUSES,
    PENDING_STATUSES,
    PROBLEM_STATUSES,
)


def _in_list(statuses: tuple[str, ...]) -> str:
    """Render a tuple of statuses as a SQL IN list.

    Interpolated rather than parameterised, which is safe *only* because these
    tuples are module constants defined a few lines above — no request data ever
    reaches this function. Doing it with placeholders instead would mean
    threading a variable number of params through every caller of `_filters`,
    where a single miscount silently shifts every other parameter.
    """
    return ", ".join(f"'{s}'" for s in statuses)

# Router-level, not per-route. Every endpoint in this file reads other people's
# mail; making the dependency opt-out rather than opt-in means the next route
# added here is protected by default.
router = APIRouter(dependencies=[Depends(require_permission("viewEmailLog"))])

MAX_LIMIT = 100

#: Categories whose body is a live credential rather than correspondence.
_SECRET_CATEGORIES = {"login_code", "password_code", "invite"}

_CODE_RE = re.compile(r"\b\d{4,10}\b")
_TEMP_PW_RE = re.compile(r"(?i)(temporary password:\s*)(\S+)")


def _redact(body: str | None, category: str | None) -> str | None:
    """Blank out sign-in codes and temporary passwords in a stored body.

    A Super Admin can already reset anyone's password, so this is not about
    trust — it's about what an unattended screen is worth to someone walking
    past it, and about not turning a stolen admin session into a way to read
    live 2FA codes for other accounts. The rest of the message is untouched, so
    "was the code actually sent, and did they open it" still answers itself,
    which is the reason anyone opens this row.
    """
    if not body or category not in _SECRET_CATEGORIES:
        return body
    body = _TEMP_PW_RE.sub(r"\1••••••••", body)
    return _CODE_RE.sub("••••••", body)


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _row_to_item(row) -> dict:
    return {
        "id": row["id"],
        "to": row["to_email"],
        "cc": row["cc_email"],
        "subject": row["subject"],
        "category": row["category"],
        "status": row["status"],
        "provider": row["provider"],
        "messageId": row["message_id"],
        "error": row["error"],
        "sentAt": row["sent_at"],
        "deliveredAt": row["delivered_at"],
        "firstOpenedAt": row["first_opened_at"],
        "lastOpenedAt": row["last_opened_at"],
        "lastEventAt": row["last_event_at"],
        "openCount": row["open_count"],
        "clickCount": row["click_count"],
        "attachmentCount": row["attachment_count"],
        "projectId": row["project_id"],
        "projectName": row.get("project_name"),
        "sentByName": row.get("sent_by_name"),
    }


def _filters(q: str | None, status: str | None, category: str | None, days: int):
    """Build the shared WHERE clause. Returns (sql_fragment, params).

    One builder for the list, the count and the stats so a filter can't drift
    into meaning one thing on the table and another on the cards above it.
    """
    where = ["e.sent_at >= ?"]
    params: list = [_cutoff(days)]

    if status:
        if status not in LIST_STATUSES:
            raise HTTPException(422, "Unknown status filter.")
        where.append("e.status = ?")
        params.append(status)

    if category:
        if category not in CATEGORIES:
            raise HTTPException(422, "Unknown category filter.")
        where.append("e.category = ?")
        params.append(category)

    if q:
        # Wildcards go in the parameter, never in the SQL string: a literal %
        # in the statement collides with psycopg's own %s placeholders.
        term = f"%{q.strip()}%"
        where.append(
            "(e.to_email ILIKE ? OR COALESCE(e.cc_email,'') ILIKE ? OR e.subject ILIKE ?)"
        )
        params += [term, term, term]

    return " AND ".join(where), params


#: Exactly the columns _row_to_item reads, and no more.
#:
#: This was `SELECT e.*`, which dragged `body` and `html_body` along with it —
#: and a report's html_body is around 10 KB of table markup (see the schema note
#: on the column). Fifty of those is half a megabyte fetched from a remote
#: database and then dropped on the floor, because _row_to_item never looks at
#: either field. The bodies are read by the detail endpoint, for the one row the
#: drawer is actually showing.
_LIST_COLUMNS = """
    e.id, e.to_email, e.cc_email, e.subject, e.category, e.status, e.provider,
    e.message_id, e.error, e.sent_at, e.delivered_at, e.first_opened_at,
    e.last_opened_at, e.last_event_at, e.open_count, e.click_count,
    e.attachment_count, e.project_id
"""


@router.get("")
def list_emails(
    q: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    db: sqlite3.Connection = Depends(get_db),
):
    clause, params = _filters(q, status, category, days)

    # One round trip, not two. COUNT(*) OVER () evaluates the same filtered set
    # the page is drawn from, so the separate COUNT query it replaces was paying
    # the ILIKE scan a second time — and against a remote database each avoided
    # round trip is worth more than the query time itself.
    rows = db.execute(
        f"""SELECT {_LIST_COLUMNS},
                   p.name AS project_name,
                   u.name AS sent_by_name,
                   COUNT(*) OVER () AS total_count
              FROM emails e
              LEFT JOIN projects p ON p.id = e.project_id
              LEFT JOIN users    u ON u.id = e.sent_by
             WHERE {clause}
             ORDER BY e.sent_at DESC, e.id DESC
             LIMIT ? OFFSET ?""",
        tuple(params + [limit, offset]),
    ).fetchall()

    # An empty page carries no window value: either there are no matches at all,
    # or the caller asked for an offset past the end. Both mean "nothing here",
    # and the client's own guard sends it back to page 0.
    total = rows[0]["total_count"] if rows else 0

    return {
        "items": [_row_to_item(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
def email_stats(
    q: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    days: int = Query(default=90, ge=1, le=365),
    db: sqlite3.Connection = Depends(get_db),
):
    """Headline numbers and a per-day series, over the same filters as the list.

    `opened` counts messages with at least one recorded open, not total opens —
    an open rate computed from raw pixel hits is inflated by whoever leaves the
    mail sitting in a preview pane.

    Open tracking is a floor, never a count: a client that blocks remote images
    never fires the pixel, and Apple Mail Privacy Protection fetches it whether
    or not a human looked. The screen says as much next to the number.
    """
    clause, params = _filters(q, status, category, days)

    row = db.execute(
        f"""SELECT COUNT(*)                                                       AS total,
                   COUNT(*) FILTER (WHERE e.status IN ({_in_list(DELIVERED_STATUSES)})) AS delivered,
                   COUNT(*) FILTER (WHERE e.open_count > 0)                       AS opened,
                   COUNT(*) FILTER (WHERE e.click_count > 0)                      AS clicked,
                   COUNT(*) FILTER (WHERE e.status IN ({_in_list(PROBLEM_STATUSES)}))   AS failed,
                   COUNT(*) FILTER (WHERE e.status IN ({_in_list(PENDING_STATUSES)}))   AS pending
              FROM emails e
             WHERE {clause}""",
        tuple(params),
    ).fetchone()

    series = db.execute(
        f"""SELECT substr(e.sent_at, 1, 10)                 AS day,
                   COUNT(*)                                 AS sent,
                   COUNT(*) FILTER (WHERE e.open_count > 0) AS opened
              FROM emails e
             WHERE {clause}
             GROUP BY 1
             ORDER BY 1""",
        tuple(params),
    ).fetchall()

    return {
        "total": row["total"],
        "delivered": row["delivered"],
        "opened": row["opened"],
        "clicked": row["clicked"],
        "failed": row["failed"],
        "pending": row["pending"],
        "series": [{"day": s["day"], "sent": s["sent"], "opened": s["opened"]} for s in series],
    }


@router.get("/{email_id}")
def email_detail(email_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute(
        """SELECT e.*, p.name AS project_name, u.name AS sent_by_name
             FROM emails e
             LEFT JOIN projects p ON p.id = e.project_id
             LEFT JOIN users    u ON u.id = e.sent_by
            WHERE e.id = ?""",
        (email_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "That email isn't in the log.")

    events = db.execute(
        """SELECT id, event, occurred_at, recipient, reason, link, user_agent, ip
             FROM email_events
            WHERE email_id = ?
            ORDER BY occurred_at ASC, id ASC""",
        (email_id,),
    ).fetchall()

    item = _row_to_item(row)
    item["body"] = _redact(row["body"], row["category"])
    # The HTML is only ever rendered inside a sandboxed iframe on the client.
    item["html"] = _redact(row["html_body"], row["category"])
    item["events"] = [
        {
            "id": e["id"],
            "event": e["event"],
            "at": e["occurred_at"],
            "recipient": e["recipient"] or None,
            "reason": e["reason"],
            "link": e["link"],
            "userAgent": e["user_agent"],
            "ip": e["ip"],
        }
        for e in events
    ]
    return item
