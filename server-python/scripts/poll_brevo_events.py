"""Pull Brevo delivery/open events and file them against the Email Log.

Why
---
The webhook at POST /api/webhooks/brevo can't be reached on this deployment:
the domain sits behind a Cloudflare zone we don't administer, and Cloudflare
answers Brevo's POSTs with a managed challenge or a 403. Brevo can't solve a
JavaScript challenge, so no event ever arrives and every message stays on the
status its own send call set — "Sent" forever, with a dash under Opened.

This reads the same events from Brevo's API instead, which is an outbound call
and therefore invisible to Cloudflare. See app/services/brevo_events.py for the
reasoning and the field translation.

Safe to run as often as you like: ingest dedupes on
(message_id, event, recipient, occurred_at), so overlapping windows are free.

Usage
-----
    cd server-python
    python -m scripts.poll_brevo_events                 # last 2 days
    python -m scripts.poll_brevo_events --days 7
    python -m scripts.poll_brevo_events --dry-run       # fetch, change nothing
    python -m scripts.poll_brevo_events --email you@example.com
    python -m scripts.poll_brevo_events --quiet         # for cron

Cron (every 15 minutes)
-----------------------
    */15 * * * * cd /home/infyappseodashbo/rankboard/server-python && \
      .venv/bin/python -m scripts.poll_brevo_events --quiet >> ~/logs/brevo-poll.log 2>&1

Exits non-zero when Brevo can't be reached or refuses the key, so cron will
mail you rather than failing silently.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.services.brevo_events import (  # noqa: E402
    DEFAULT_DAYS,
    BrevoEventsError,
    fetch_events,
    ingest_all,
)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"How many days back to read (default {DEFAULT_DAYS}).")
    ap.add_argument("--email", default=None,
                    help="Only events for one recipient — handy when testing.")
    ap.add_argument("--page-size", type=int, default=1000,
                    help="Events per API request (max 2500).")
    ap.add_argument("--max-pages", type=int, default=50,
                    help="Safety stop so a misconfiguration can't loop forever.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Fetch and summarise without writing anything.")
    ap.add_argument("--quiet", action="store_true",
                    help="Print only when something changed or broke. For cron.")
    args = ap.parse_args()

    def say(message: str) -> None:
        if not args.quiet:
            print(message)

    try:
        say(f"Fetching the last {args.days} day(s) of events from Brevo…")
        events = fetch_events(
            days=args.days,
            page_size=args.page_size,
            max_pages=args.max_pages,
            email=args.email,
        )
    except BrevoEventsError as exc:
        # Always printed, even with --quiet: a silent failure here means the
        # Email Log quietly stops updating and nobody notices for weeks.
        print(f"Brevo events could not be fetched: {exc}", file=sys.stderr)
        return 1

    if not events:
        say("No events in that window.")
        return 0

    kinds: dict[str, int] = {}
    for item in events:
        if isinstance(item, dict):
            kinds[str(item.get("event") or "?")] = kinds.get(str(item.get("event") or "?"), 0) + 1
    say(f"{len(events)} event(s): " + ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))

    if args.dry_run:
        print("Dry run — nothing was written.")
        return 0

    conn = db.get_connection()
    try:
        tally = ingest_all(conn, events)
    finally:
        conn.close()

    summary = (f"stored {tally['stored']}, duplicates {tally['duplicates']}, "
               f"ignored {tally['ignored']}, errors {tally['errors']}")
    # Under --quiet, only speak up when there is news. A cron job that logs
    # "nothing changed" every 15 minutes trains you to ignore its output.
    if args.quiet:
        if tally["stored"] or tally["errors"]:
            print(summary)
    else:
        print(summary)

    return 1 if tally["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
