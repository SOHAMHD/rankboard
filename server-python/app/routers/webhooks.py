import secrets
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request

from ..config import BREVO_WEBHOOK_SECRET
from ..db import get_db
from ..services import email_tracking

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

    stored = duplicates = ignored = 0
    for item in events:
        try:
            result = email_tracking.ingest_event(db, item)
        except Exception as exc:  # noqa: BLE001 — one bad event must not stop the batch
            print("Brevo webhook: could not record event:", exc)
            ignored += 1
            continue
        if result == "stored":
            stored += 1
        elif result == "duplicate":
            duplicates += 1
        else:
            ignored += 1

    return {"received": len(events), "stored": stored,
            "duplicates": duplicates, "ignored": ignored}
