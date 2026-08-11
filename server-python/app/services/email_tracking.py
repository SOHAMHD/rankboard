"""Ingest and interpret Brevo delivery events.

Brevo already renders a tracking pixel into every message it sends and watches
every link it rewrites. What it does not do is tell you about it anywhere you
can see next to your own data — you have to go and read its dashboard. This
module is the bridge: it takes the event stream Brevo pushes to
`POST /api/webhooks/brevo`, files each event against the `emails` row that
produced it, and keeps a small rollup on that row so the Email Log screen can
list a page of messages without aggregating a second table per row.

Two things are worth knowing before changing anything here:

* **Events arrive out of order.** A webhook is an at-least-once delivery with no
  ordering guarantee, and Brevo retries anything it did not get a 2xx from. An
  `opened` can land before the `delivered` that preceded it. Nothing here may
  assume sequence — hence `_STATUS_RANK`, which only ever moves a message
  forward, and the `LEAST`/`GREATEST` arithmetic on the timestamps.

* **The same event can arrive twice.** Deduping is a unique index on
  (message_id, event, recipient, occurred_at) with INSERT OR IGNORE, and the
  rollup is only applied when the insert actually wrote a row. Counting opens
  off a replayed batch would quietly inflate every number on the screen.
"""

import json
import re
from datetime import datetime, timezone

#: A bare "YYYY-MM-DD…" prefix — the loosest thing worth keeping if
#: fromisoformat refuses a timestamp string.
_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")

#: Brevo's event name -> the status we show. Several map to the same thing:
#: the screen distinguishes "did it arrive" from "did they read it", not the
#: eleven shades of failure Brevo reports.
EVENT_STATUS = {
    "request": "sent",
    "delivered": "delivered",
    "opened": "opened",
    "unique_opened": "opened",
    "proxy_open": "opened",
    "click": "clicked",
    "deferred": "deferred",
    "soft_bounce": "bounced",
    "hard_bounce": "bounced",
    "blocked": "bounced",
    "invalid_email": "failed",
    "error": "failed",
    "spam": "complaint",
    "complaint": "complaint",
    "unsubscribed": "unsubscribed",
    "list_addition": "sent",
}

#: A message only ever moves forward. Without this an `opened` webhook that
#: overtook its own `delivered` would leave the row reading "delivered" — the
#: earlier, weaker fact — because it was written last.
#:
#: The failure states sit above the success ones on purpose. A message that was
#: delivered, opened, and then reported as spam should read "complaint" on the
#: list: that is the fact someone needs to act on, and burying it under
#: "opened" is how a deliverability problem goes unnoticed for a month.
_STATUS_RANK = {
    "queued": 0,
    "outbox": 0,
    "sent": 1,
    "deferred": 2,
    "delivered": 3,
    "opened": 4,
    "clicked": 5,
    "unsubscribed": 6,
    "complaint": 7,
    "bounced": 8,
    "failed": 9,
}

#: Brevo's three flavours of "someone loaded the pixel". See _apply_rollup for
#: which of them count as a read and which only move the timestamps.
_OPEN_EVENTS = ("opened", "unique_opened", "proxy_open")

#: Statuses the Email Log filter offers. Must cover every value that can end up
#: in emails.status, including 'outbox' — which only appears on a machine with
#: no provider configured, but is unfilterable if it's missing from here.
LIST_STATUSES = ("queued", "outbox", "sent", "deferred", "delivered", "opened",
                 "clicked", "bounced", "failed", "complaint", "unsubscribed")

#: How the stats cards bucket those statuses.
#:
#: 'complaint' and 'unsubscribed' count as DELIVERED because both prove the
#: message arrived — a spam report is a delivery with an unhappy ending. Since
#: _STATUS_RANK lets those two overwrite 'opened', leaving them out would make
#: delivered undercount while the opened count (which is status-independent)
#: did not, and the open rate computed from the two would exceed 100%.
#:
#: 'complaint' therefore appears in DELIVERED_STATUSES *and* PROBLEM_STATUSES.
#: These are two different questions — "did it arrive" and "is something wrong"
#: — and a spam report is honestly a yes to both. The cards are labelled as
#: independent figures, not as parts of a whole that sum to the total.
DELIVERED_STATUSES = ("delivered", "opened", "clicked", "complaint", "unsubscribed")
PROBLEM_STATUSES = ("bounced", "failed", "complaint")
PENDING_STATUSES = ("queued", "outbox", "sent", "deferred")

CATEGORIES = ("report", "invite", "password_code", "login_code", "other")

_TRACK_PREFIX = "email_log_id:"


def status_rank(status: str | None) -> int:
    return _STATUS_RANK.get((status or "").lower(), 0)


def _to_utc_string(value) -> str | None:
    """Brevo timestamp -> 'YYYY-MM-DD HH:MM:SS' UTC, the format this DB uses.

    Epoch seconds are preferred over the `date` string because `date` is
    rendered in whatever timezone the Brevo account is configured for, with no
    offset attached — parsing it as UTC silently shifts every event by hours.
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1e11:          # milliseconds, not seconds
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        # Anything that isn't recognisably a date is rejected rather than stored
        # verbatim. occurred_at is compared with LEAST/GREATEST and sorted as
        # text, so one junk value in the column poisons the ordering of every
        # timeline it appears in. `_event_time` falls through to the next key.
        return text[:19] if _DATE_LIKE.match(text) else None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _event_time(payload: dict) -> str:
    for key in ("ts_event", "ts", "ts_epoch", "date_event", "date", "date_sent"):
        stamp = _to_utc_string(payload.get(key))
        if stamp:
            return stamp
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _strip_brackets(message_id: str) -> str:
    return (message_id or "").strip().strip("<>").strip()


def _match_email_row(db, payload: dict, message_id: str):
    """Find the `emails` row an event belongs to, or None.

    Three attempts, most trustworthy first:

    1. The X-Mailin-custom header we stamped at send time. This is ours, it is
       an exact row id, and it survives Brevo reformatting the Message-ID.
    2. The message id verbatim.
    3. The message id with its angle brackets stripped. Brevo's send response
       and its webhook payload do not consistently agree on whether they are
       there, and a message that tracked fine for a year would otherwise stop
       matching after a provider-side change nobody told us about.
    """
    custom = payload.get("X-Mailin-custom") or payload.get("x-mailin-custom") or ""
    if isinstance(custom, str) and _TRACK_PREFIX in custom:
        tail = custom.split(_TRACK_PREFIX, 1)[1]
        digits = ""
        for ch in tail:
            if ch.isdigit():
                digits += ch
            else:
                break
        if digits:
            row = db.execute("SELECT * FROM emails WHERE id = ?", (int(digits),)).fetchone()
            if row is not None:
                return row

    if message_id:
        row = db.execute(
            "SELECT * FROM emails WHERE message_id = ? ORDER BY id DESC LIMIT 1",
            (message_id,),
        ).fetchone()
        if row is not None:
            return row

        # Runs even when the incoming id already looks bare. The failing case is
        # an unbracketed id arriving against a bracketed one on file — guarding
        # this on `bare != message_id` would skip exactly that case.
        bare = _strip_brackets(message_id)
        if bare:
            row = db.execute(
                "SELECT * FROM emails WHERE replace(replace(message_id, '<', ''), '>', '') = ?"
                " ORDER BY id DESC LIMIT 1",
                (bare,),
            ).fetchone()
            if row is not None:
                return row
    return None


def ingest_event(db, payload: dict) -> str:
    """Record one Brevo event. Returns 'stored', 'duplicate' or 'ignored'.

    Never raises on a payload it doesn't understand: the caller answers 2xx
    regardless, because a 4xx makes Brevo retry the same unparseable event for
    hours and eventually disable the webhook outright.
    """
    if not isinstance(payload, dict):
        return "ignored"

    event = str(payload.get("event") or "").strip().lower()
    if not event:
        return "ignored"

    message_id = str(payload.get("message-id") or payload.get("message_id") or "").strip()
    recipient = str(payload.get("email") or "").strip()
    occurred_at = _event_time(payload)
    status = EVENT_STATUS.get(event)

    row = _match_email_row(db, payload, message_id)
    email_id = row["id"] if row is not None else None
    reason = payload.get("reason") or payload.get("error") or None

    # The event row and the rollup it implies must land together. Connections
    # are autocommit, so without this the insert commits on its own and a
    # failure in the rollup below leaves the counters short *permanently*: the
    # dedupe index now matches, so Brevo's retry is discarded as a duplicate and
    # the lost increment is never reapplied.
    with db.transaction():
        # An unmatched event is still stored, with a NULL email_id. It is
        # usually a send that predates this feature; keeping it means a bounce
        # for an address we can't tie to a message is still findable.
        cur = db.execute(
            """INSERT OR IGNORE INTO email_events
                   (email_id, message_id, recipient, event, occurred_at,
                    reason, link, user_agent, ip, raw)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?::jsonb)""",
            (
                email_id,
                message_id or "",
                recipient or "",
                event,
                occurred_at,
                reason,
                (payload.get("link") or payload.get("URL") or None),
                (payload.get("user_agent") or payload.get("agent") or None),
                (payload.get("sending_ip") or payload.get("ip") or None),
                _raw_json(payload),
            ),
        )
        # rowcount is 0 when the dedupe index caught a replay. Returning early
        # is the whole point: the rollup below is not idempotent.
        if getattr(cur, "rowcount", 1) == 0:
            return "duplicate"

        if row is not None:
            _apply_rollup(db, row, event=event, status=status,
                          occurred_at=occurred_at, reason=reason)
    return "stored"


#: Anything past this and we store a stub instead of the payload.
_RAW_LIMIT = 20000


def _raw_json(payload: dict) -> str:
    """Serialise the payload for the `raw` JSONB column, bounded in size.

    Slicing the serialised string was the obvious way to bound this and it is
    wrong: a JSON document cut at 20 000 characters is not JSON, Postgres
    rejects the ::jsonb cast, and the whole event is lost — silently, because
    the webhook still answers 200 and Brevo never retries. So an oversized
    payload is replaced by a valid document that says so, keeping the fields
    anyone would actually go looking for.
    """
    text = json.dumps(payload, default=str)
    if len(text) <= _RAW_LIMIT:
        return text
    return json.dumps({
        "_truncated": True,
        "_original_bytes": len(text),
        "event": payload.get("event"),
        "email": payload.get("email"),
        "message-id": payload.get("message-id"),
        "reason": str(payload.get("reason") or "")[:500],
        "link": str(payload.get("link") or "")[:2000],
    }, default=str)


def _apply_rollup(db, row, *, event: str, status: str | None,
                  occurred_at: str, reason: str | None) -> None:
    """Fold one event into the denormalised columns on its `emails` row.

    Written as SQL expressions over the current column values rather than
    read-modify-write in Python, so two events for the same message arriving
    at once can't clobber each other's counters.
    """
    # `opened` and `proxy_open` each count as one read; `unique_opened` only
    # moves the timestamps. Brevo emits `unique_opened` *alongside* `opened` for
    # the first open of a message, so counting it too would report every first
    # read as two — but it can also arrive alone on some accounts, and a row
    # reading "Opened" with a dash in the Opened column is worse than either.
    #
    # proxy_open is Apple Mail Privacy Protection prefetching the pixel. It is
    # counted because leaving it out means an entire class of recipient shows as
    # never having opened anything; it is also the main reason the screen calls
    # the open figure a floor rather than a number.
    if event in _OPEN_EVENTS:
        counted = 1 if event in ("opened", "proxy_open") else 0
        db.execute(
            f"""UPDATE emails
                   SET open_count      = open_count + {counted},
                       first_opened_at = LEAST(COALESCE(first_opened_at, ?), ?),
                       last_opened_at  = GREATEST(COALESCE(last_opened_at, ?), ?)
                 WHERE id = ?""",
            (occurred_at, occurred_at, occurred_at, occurred_at, row["id"]),
        )
    elif event == "click":
        # LEAST/COALESCE rather than "set it if null", for the same reason the
        # open timestamps use it: events arrive out of order, so a click that
        # overtakes an earlier one must not claim to be the first.
        db.execute(
            """UPDATE emails
                  SET click_count      = click_count + 1,
                      first_clicked_at = LEAST(COALESCE(first_clicked_at, ?), ?)
                WHERE id = ?""",
            (occurred_at, occurred_at, row["id"]),
        )
    elif event == "delivered":
        db.execute(
            "UPDATE emails SET delivered_at = COALESCE(delivered_at, ?) WHERE id = ?",
            (occurred_at, row["id"]),
        )

    db.execute(
        "UPDATE emails SET last_event_at = GREATEST(COALESCE(last_event_at, ?), ?) WHERE id = ?",
        (occurred_at, occurred_at, row["id"]),
    )

    if status and status_rank(status) > status_rank(row["status"]):
        db.execute("UPDATE emails SET status = ? WHERE id = ?", (status, row["id"]))

    # Surface *why* it failed on the row itself. "Bounced" with no reason sends
    # whoever is looking into the raw event JSON to find out whether the address
    # is wrong or the domain rejected us, which is the actual question.
    if reason and status in ("bounced", "failed", "complaint"):
        db.execute("UPDATE emails SET error = ? WHERE id = ?", (str(reason)[:500], row["id"]))
