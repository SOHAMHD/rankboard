"""EMAIL SERVICE — same swappable transport as the Node version.

RESEND_API_KEY set      -> actually sent via Resend's HTTP API
RESEND_API_KEY not set  -> dev outbox only (the `emails` table)

Either way the email is logged to the outbox for an audit trail, and
callers only ever know "an invite was sent".
"""
import json
import sqlite3
import urllib.request

from ..config import APP_URL, EMAIL_FROM, RESEND_API_KEY


def send_invite_email(db: sqlite3.Connection, *, name: str, email: str, role: str, temp_password: str) -> dict:
    subject = "You've been added to RankBoard"
    body = "\n".join([
        f"Hi {name.split(' ')[0]},",
        "",
        f"You've been added to the RankBoard workspace as {role}.",
        "",
        f"Sign in here: {APP_URL}",
        f"Email: {email}",
        f"Temporary password: {temp_password}",
        "",
        "You'll be asked to set your own password the first time you sign in.",
        "",
        "If you weren't expecting this, you can ignore this email.",
    ])

    # ---- Real transport (active only when a key is configured) ----
    delivery = "outbox"
    if RESEND_API_KEY:
        try:
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps({"from": EMAIL_FROM, "to": [email], "subject": subject, "text": body}).encode(),
                headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                delivery = "sent" if 200 <= res.status < 300 else "failed"
        except Exception as exc:  # don't break onboarding if the provider is down
            delivery = "failed"
            print("Could not reach the email provider:", exc)

    cur = db.execute(
        "INSERT INTO emails (to_email, subject, body) VALUES (?, ?, ?)", (email, subject, body)
    )
    row = db.execute("SELECT * FROM emails WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {**dict(row), "delivery": delivery}
