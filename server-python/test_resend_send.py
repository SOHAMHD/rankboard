"""THROWAWAY DEV SCRIPT — verify the Resend wiring end-to-end.

This does NOT reimplement anything. It:
  * loads env the same way the app does (importing app.config runs the
    app's own .env loader),
  * calls the EXISTING send function app.services.email_service.send_invite_email
    with minimal dummy values + a minimal in-memory SQLite db (the function
    logs every send to an `emails` row, so it needs a connection),
  * installs an OBSERVE-ONLY spy on urllib.request.urlopen so we can print
    the full raw body Resend returns (message id on success / error JSON on
    failure) — the existing function only keeps the HTTP status, so the spy
    reads the response stream the function already fetched without changing
    its behaviour or its code.

Usage (from anywhere — the script adds its own dir to sys.path):
    server-python\\.venv\\Scripts\\python.exe server-python\\test_resend_send.py [recipient]

Recipient defaults to delivered@resend.dev (Resend's always-succeeds sink).
Delete this file when you're done verifying.
"""
import sqlite3
import sys
import urllib.error
import urllib.request

# Importing app.config runs the app's OWN dotenv loader (config.py reads
# server-python/.env into os.environ) — this is the app's env mechanism,
# not a reinvented one. It also exposes the exact values the send code uses.
from app import config
from app.services.email_service import send_invite_email


def main() -> int:
    recipient = sys.argv[1] if len(sys.argv) > 1 else "delivered@resend.dev"

    # ---- (a) Did RESEND_API_KEY load in THIS process? (never print the value) ----
    key = config.RESEND_API_KEY
    print("=" * 70)
    print("RESEND WIRING TEST")
    print("=" * 70)
    print(f"(a) RESEND_API_KEY loaded in this process : {bool(key)}"
          + (f"  (length {len(key)}, value hidden)" if key else "  -> empty"))
    print(f"    EMAIL_FROM (sender)                   : {config.EMAIL_FROM}")
    print(f"    Recipient                             : {recipient}")
    print("-" * 70)

    # Minimal context the existing function needs: a connection with the
    # `emails` table and Row factory (so dict(row) works). In-memory so we
    # don't touch the real rankboard.db.
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE emails ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  to_email TEXT NOT NULL,"
        "  subject TEXT NOT NULL,"
        "  body TEXT NOT NULL,"
        "  sent_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )

    # OBSERVE-ONLY spy: capture the raw Resend response/error body that the
    # existing function fetches but discards. We do not build or send any
    # request ourselves — _real_urlopen IS the call the function makes.
    captured: dict = {}
    _real_urlopen = urllib.request.urlopen

    def _spy(req, *args, **kwargs):
        try:
            res = _real_urlopen(req, *args, **kwargs)
            captured["http_status"] = getattr(res, "status", None)
            captured["raw_body"] = res.read().decode("utf-8", "replace")
            return res  # function only reads res.status, so consuming body is safe
        except urllib.error.HTTPError as exc:
            captured["http_status"] = exc.code
            try:
                captured["raw_body"] = exc.read().decode("utf-8", "replace")
            except Exception as read_exc:  # pragma: no cover
                captured["raw_body"] = f"<could not read error body: {read_exc!r}>"
            raise  # re-raise so the existing function behaves exactly as in prod
        except Exception as exc:
            captured["transport_error"] = repr(exc)
            raise

    urllib.request.urlopen = _spy
    try:
        result = send_invite_email(
            db,
            name="Test User",
            email=recipient,
            role="Team",
            temp_password="Dummy-Temp-1234",
        )
    finally:
        urllib.request.urlopen = _real_urlopen  # always restore

    # ---- (b) Real Resend path or outbox fallback? ----
    delivery = result.get("delivery")
    if not key:
        path = "OUTBOX FALLBACK (no key in this process — real send was skipped)"
    elif delivery == "sent":
        path = "REAL RESEND PATH — provider accepted (HTTP 2xx)"
    elif delivery == "failed":
        path = "REAL RESEND PATH — attempted but the provider rejected/errored"
    else:
        path = f"OUTBOX FALLBACK (delivery={delivery!r})"
    print(f"(b) Path executed                         : {path}")
    print(f"    delivery field returned               : {delivery!r}")
    print("-" * 70)

    # ---- (c) Full raw result from Resend ----
    print("(c) Raw result from Resend:")
    if "http_status" in captured:
        print(f"    HTTP status : {captured['http_status']}")
    if "raw_body" in captured:
        print(f"    Raw body    : {captured['raw_body']}")
    if "transport_error" in captured:
        print(f"    Transport error (never reached Resend): {captured['transport_error']}")
    if not captured:
        print("    <no HTTP call was made — outbox fallback path>")
    print("-" * 70)
    print(f"Outbox audit row written (in-memory): id={result.get('id')} "
          f"to={result.get('to_email')!r} subject={result.get('subject')!r}")
    print("=" * 70)

    # Exit non-zero if a real send was attempted and failed, so this is
    # usable in a pipeline.
    return 1 if (key and delivery == "failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
