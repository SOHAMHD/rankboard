"""Pull delivery events from Brevo instead of waiting to be pushed them.

Why this exists
---------------
`POST /api/webhooks/brevo` is the intended path: Brevo pushes each event the
moment it happens. That requires Brevo to be able to reach us, and on this
deployment it can't — the domain sits behind a Cloudflare zone we don't
administer, and Cloudflare answers machine-to-machine POSTs with a managed
challenge (an HTML page, HTTP 200) or a 403. Brevo can't solve a JavaScript
challenge, so it never gets a 2xx and no event is ever recorded.

Brevo exposes the same event stream over its API — `GET /v3/smtp/statistics/events`
— which is an *outbound* call. Nothing has to reach us, so Cloudflare is not
involved at all.

Polling is arguably the better design here regardless:

* Nothing inbound to expose, and no shared secret in a URL to leak.
* It self-heals. Miss an hour to a restart and the next run picks the events up,
  whereas Brevo eventually stops retrying a webhook that keeps failing and
  disables it.
* It is safe to run as often as you like: `ingest_event` dedupes on
  (message_id, event, recipient, occurred_at), so re-reading a window that has
  already been read changes nothing.

The two feeds can coexist. If the webhook is ever unblocked, whichever arrives
first wins and the other is discarded as a duplicate.

The one wrinkle: the API and the webhook disagree about field names. The webhook
sends `message-id` and `ts_event`; the API returns `messageId` and `date`.
`to_webhook_payload` is the whole of that translation, kept here rather than in
email_tracking so the ingest side has exactly one payload shape to understand.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from ..config import BREVO_API_KEY

EVENTS_URL = "https://api.brevo.com/v3/smtp/statistics/events"

#: Brevo's documented ceiling for this endpoint.
MAX_PAGE = 2500

#: How many days back a run looks by default. Two, not one, so a run just after
#: midnight still sees yesterday evening's events — the endpoint's window is
#: date-granular, so there is no finer knob than this.
DEFAULT_DAYS = 2


class BrevoEventsError(RuntimeError):
    """Raised when Brevo cannot be reached or refuses the request."""


def to_webhook_payload(item: dict) -> dict:
    """Reshape one API event into the payload `email_tracking.ingest_event` expects.

    Only the keys that differ are translated; everything else is passed through
    untouched so a field Brevo adds later still reaches the `raw` column without
    a change here.

    On timestamps: the API's `date` carries a UTC offset (e.g.
    "2026-08-11T15:34:02.000+05:30"), and `_to_utc_string` converts it properly.
    That matters — `email_tracking` documents that a *naive* Brevo date string is
    rendered in the account's own timezone and would silently shift every event
    by hours if parsed as UTC. Passing `date` through under its own name lets
    `_event_time` find it in its normal fallback order.
    """
    out = dict(item)

    message_id = item.get("messageId") or item.get("message-id") or item.get("message_id")
    if message_id:
        out["message-id"] = str(message_id)

    # The API says "url" for a clicked link; the webhook says "link".
    if not out.get("link") and item.get("url"):
        out["link"] = item["url"]

    return out


def _request(params: dict) -> dict:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    req = urllib.request.Request(
        f"{EVENTS_URL}?{query}",
        headers={
            "api-key": BREVO_API_KEY,
            "Accept": "application/json",
            "User-Agent": "SEODashboard/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001 — the status alone is still useful
            pass
        # 401 here is the same authentication failure the Email Log shows against
        # a failed send: the key is wrong, expired, or has whitespace around it.
        raise BrevoEventsError(f"Brevo returned HTTP {exc.code}. {detail}") from exc
    except urllib.error.URLError as exc:
        raise BrevoEventsError(f"Could not reach Brevo: {exc.reason}") from exc


def fetch_events(*, days: int = DEFAULT_DAYS, page_size: int = 1000,
                 max_pages: int = 50, email: str | None = None) -> list[dict]:
    """Every event Brevo has for the last `days`, oldest first.

    Paginated because the endpoint caps a single response. `max_pages` is a
    stop so a misconfiguration can't turn a cron job into an unbounded loop;
    hitting it is reported by the caller rather than passing silently.
    """
    if not BREVO_API_KEY:
        raise BrevoEventsError(
            "BREVO_API_KEY is not set — there is nothing to authenticate with. "
            "Add it to server-python/.env."
        )

    page_size = max(1, min(page_size, MAX_PAGE))
    collected: list[dict] = []

    for page in range(max_pages):
        data = _request({
            "limit": page_size,
            "offset": page * page_size,
            "days": days,
            "sort": "asc",          # oldest first, so a truncated run still
            "email": email,         # leaves the newest events for the next one
        })
        events = data.get("events") or []
        collected.extend(events)
        if len(events) < page_size:
            return collected

    raise BrevoEventsError(
        f"Stopped after {max_pages} pages ({len(collected)} events). "
        "Narrow the window with --days, or raise --max-pages if this is genuinely "
        "that much traffic."
    )


def ingest_all(db, events: list[dict]) -> dict:
    """Feed API events through the normal ingest path. Returns a tally."""
    from . import email_tracking

    tally = {"received": len(events), "stored": 0, "duplicates": 0, "ignored": 0, "errors": 0}
    for item in events:
        if not isinstance(item, dict):
            tally["ignored"] += 1
            continue
        try:
            result = email_tracking.ingest_event(db, to_webhook_payload(item))
        except Exception as exc:  # noqa: BLE001 — one bad event must not stop the run
            print(f"  ! could not record {item.get('event')} for {item.get('email')}: {exc}")
            tally["errors"] += 1
            continue
        if result == "stored":
            tally["stored"] += 1
        elif result == "duplicate":
            tally["duplicates"] += 1
        else:
            tally["ignored"] += 1
    return tally
