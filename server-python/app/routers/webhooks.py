import logging
import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from ..config import BREVO_WEBHOOK_SECRET
from ..db import get_db
from ..services import email_tracking

logger = logging.getLogger(__name__)

router = APIRouter()


def _authorise(request: Request) -> None:
   
    if not BREVO_WEBHOOK_SECRET:
        raise HTTPException(
            503,
            "Email event tracking isn't configured. Set BREVO_WEBHOOK_SECRET on the "
            "server, then point Brevo's webhook at /api/webhooks/brevo?token=<secret>.",
        )
    presented = (
        request.query_params.get("token")
        or request.headers.get("x-webhook-token")
        or ""
    )
    if not secrets.compare_digest(presented.encode("utf-8"),
                                  BREVO_WEBHOOK_SECRET.encode("utf-8")):
        raise HTTPException(403, "Invalid webhook token.")


@router.post("/brevo")
async def brevo_events(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
   
    _authorise(request)

    try:
        payload = await request.json()
    except Exception:
        return {"received": 0, "stored": 0, "duplicates": 0, "ignored": 0,
                "note": "Body was not JSON."}

    events = payload if isinstance(payload, list) else [payload]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        events = payload["events"]

    # The handler has to be async — the body is read with `await request.json()` —
    # but ingest_event is synchronous psycopg I/O, and a batch of them running on
    # the event loop blocks every other request in the process for the duration.
    # The loop is therefore handed to the threadpool, which is where sync database
    # work belongs.
    stored, duplicates, ignored = await run_in_threadpool(_ingest_batch, db, events)

    return {"received": len(events), "stored": stored,
            "duplicates": duplicates, "ignored": ignored}


def _ingest_batch(db, events: list) -> tuple[int, int, int]:
    """Record a batch of Brevo events. Runs on a worker thread, never the loop."""
    stored = duplicates = ignored = 0
    for item in events:
        try:
            result = email_tracking.ingest_event(db, item)
        except Exception:  # noqa: BLE001 — one bad event must not stop the batch
            logger.exception("Brevo webhook: could not record event")
            ignored += 1
            continue
        if result == "stored":
            stored += 1
        elif result == "duplicate":
            duplicates += 1
        else:
            ignored += 1
    return stored, duplicates, ignored
