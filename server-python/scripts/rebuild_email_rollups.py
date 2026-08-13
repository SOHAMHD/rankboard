"""Recompute the denormalised columns on `emails` from `email_events`.

Why this is needed
------------------
`email_tracking.ingest_event` deliberately skips `_apply_rollup` when the dedupe
index catches a replay:

    if getattr(cur, "rowcount", 1) == 0:
        return "duplicate"          # the rollup below is not idempotent

That is correct — counting opens off a replayed batch would inflate every number
on the screen. But it means a rollup missed once is missed permanently: the event
row exists, so every future poll reports "duplicate" and moves on. Re-running the
poller cannot repair it.

That happens whenever the rollup logic changes after events have already landed.
Two real cases:

* `first_clicked_at` was added after clicks had been ingested, so those rows show
  no click time however many times you poll.
* Events stored under Brevo's API spellings (`clicks`, `hardBounces`) before the
  name translation existed resolved to no status at all, so a message that was
  clicked still reads "Opened" — or a bounce still reads "Sent".

This script rebuilds every rollup column from the events on record, which is the
property a denormalised column should have: recoverable from its source.

It reuses `EVENT_STATUS` and `status_rank` from email_tracking rather than
reimplementing them in SQL, so it cannot drift from the live path.

Safe to re-run. Statuses only ever move forward, so a rebuild can't downgrade a
`failed` set by the send call, or a `complaint` that outranks `opened`.

Usage
-----
    cd server-python
    python -m scripts.rebuild_email_rollups              # dry run
    python -m scripts.rebuild_email_rollups --commit
    python -m scripts.rebuild_email_rollups --commit --id 42
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.services.email_tracking import (  # noqa: E402
    EVENT_STATUS,
    _OPEN_EVENTS,
    status_rank,
)

#: Events stored under Brevo's API spelling before to_webhook_payload translated
#: them. Recognised here so a rebuild repairs those rows too rather than ignoring
#: them the way the live path now does.
_LEGACY_NAMES = {
    "clicks": "click",
    "requests": "request",
    "uniqueOpened": "unique_opened",
    "loadedByProxy": "proxy_open",
    "hardBounces": "hard_bounce",
    "softBounces": "soft_bounce",
    "bounces": "hard_bounce",
    "invalid": "invalid_email",
    "complaints": "complaint",
}

#: Which events count as one read. Mirrors _apply_rollup: unique_opened only moves
#: the timestamps, because Brevo emits it alongside `opened` for a first open.
_COUNTED_OPENS = ("opened", "proxy_open")


def canonical(event: str) -> str:
    e = (event or "").strip()
    return _LEGACY_NAMES.get(e, _LEGACY_NAMES.get(e.lower(), e))


def fetch_events(conn, email_id: int | None):
    sql = (
        "SELECT email_id, event, occurred_at, reason FROM email_events"
        " WHERE email_id IS NOT NULL"
    )
    params: list = []
    if email_id is not None:
        sql += " AND email_id = ?"
        params.append(email_id)
    sql += " ORDER BY email_id, occurred_at"
    return conn.execute(sql, tuple(params)).fetchall()


def fetch_rows(conn, email_id: int | None):
    sql = ("SELECT id, status, delivered_at, first_opened_at, last_opened_at,"
           "       first_clicked_at, last_event_at, open_count, click_count, error"
           "  FROM emails")
    params: list = []
    if email_id is not None:
        sql += " WHERE id = ?"
        params.append(email_id)
    return {r["id"]: r for r in conn.execute(sql, tuple(params)).fetchall()}


def rollup_for(events) -> dict:
    """What the columns should be, given this message's events."""
    out = {
        "status": None, "delivered_at": None, "first_opened_at": None,
        "last_opened_at": None, "first_clicked_at": None, "last_event_at": None,
        "open_count": 0, "click_count": 0, "error": None,
    }
    for e in events:
        event = canonical(e["event"])
        at = e["occurred_at"]
        status = EVENT_STATUS.get(event)

        if status and status_rank(status) > status_rank(out["status"]):
            out["status"] = status
        if e["reason"] and status in ("bounced", "failed", "complaint"):
            out["error"] = str(e["reason"])[:500]

        if event in _OPEN_EVENTS:
            if event in _COUNTED_OPENS:
                out["open_count"] += 1
            if out["first_opened_at"] is None or at < out["first_opened_at"]:
                out["first_opened_at"] = at
            if out["last_opened_at"] is None or at > out["last_opened_at"]:
                out["last_opened_at"] = at
        elif event == "click":
            out["click_count"] += 1
            if out["first_clicked_at"] is None or at < out["first_clicked_at"]:
                out["first_clicked_at"] = at
        elif event == "delivered":
            if out["delivered_at"] is None or at < out["delivered_at"]:
                out["delivered_at"] = at

        if out["last_event_at"] is None or at > out["last_event_at"]:
            out["last_event_at"] = at
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--commit", action="store_true", help="Write. Without this, nothing changes.")
    ap.add_argument("--id", type=int, default=None, help="Rebuild one emails row only.")
    args = ap.parse_args()

    conn = db.get_connection()
    try:
        rows = fetch_rows(conn, args.id)
        by_email = defaultdict(list)
        for e in fetch_events(conn, args.id):
            by_email[e["email_id"]].append(e)

        if not by_email:
            print("No matched events on record — nothing to rebuild.")
            print("If the Email Log shows no clicks, the events are either unmatched")
            print("(email_id IS NULL) or Brevo has none. Check with:")
            print("  SELECT event, COUNT(*), COUNT(email_id) FROM email_events GROUP BY event;")
            return 0

        changes = []
        for email_id, events in sorted(by_email.items()):
            row = rows.get(email_id)
            if row is None:
                continue
            want = rollup_for(events)

            # Never move a status backwards. 'failed' comes from the send call and
            # has no event behind it; 'complaint' deliberately outranks 'opened'.
            if status_rank(row["status"]) > status_rank(want["status"]):
                want["status"] = row["status"]
            if want["status"] is None:
                want["status"] = row["status"]
            if want["error"] is None:
                want["error"] = row["error"]

            diff = {k: (row[k], v) for k, v in want.items() if row[k] != v}
            if diff:
                changes.append((email_id, want, diff))

        if not changes:
            print(f"{len(by_email)} message(s) checked — every rollup already correct.")
            return 0

        print(f"{len(changes)} of {len(by_email)} message(s) need rebuilding:\n")
        for email_id, _want, diff in changes:
            print(f"  #{email_id}")
            for col, (old, new) in sorted(diff.items()):
                print(f"      {col:17} {str(old):24} -> {new}")

        if not args.commit:
            print("\nDry run — nothing was written. Re-run with --commit to apply.")
            return 0

        with conn.transaction():
            for email_id, want, _diff in changes:
                conn.execute(
                    """UPDATE emails
                          SET status = ?, delivered_at = ?, first_opened_at = ?,
                              last_opened_at = ?, first_clicked_at = ?,
                              last_event_at = ?, open_count = ?, click_count = ?,
                              error = ?
                        WHERE id = ?""",
                    (want["status"], want["delivered_at"], want["first_opened_at"],
                     want["last_opened_at"], want["first_clicked_at"],
                     want["last_event_at"], want["open_count"], want["click_count"],
                     want["error"], email_id),
                )
        print(f"\nRebuilt {len(changes)} message(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
