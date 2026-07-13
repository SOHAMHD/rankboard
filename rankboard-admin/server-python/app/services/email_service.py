"""EMAIL SERVICE — same swappable transport as the Node version.

RESEND_API_KEY set      -> actually sent via Resend's HTTP API
RESEND_API_KEY not set  -> dev outbox only (the `emails` table)

Either way the email is logged to the outbox for an audit trail, and
callers only ever know "an invite was sent" / "a code was sent".
"""
import json
import sqlite3
import urllib.request

from ..config import APP_URL, EMAIL_FROM, RESEND_API_KEY


def _deliver(db: sqlite3.Connection, *, email: str, subject: str, body: str) -> dict:
    """Send one email via Resend when configured, and ALWAYS log it to the
    `emails` outbox. Returns the stored row + a `delivery` status
    ("sent" | "failed" | "outbox"). Never raises — a provider outage must not
    break sign-in or onboarding."""
    delivery = "outbox"
    if RESEND_API_KEY:
        try:
            req = urllib.request.Request(
                "https://api.resend.com/emails",
                data=json.dumps({"from": EMAIL_FROM, "to": [email], "subject": subject, "text": body}).encode(),
                headers={
                    "Authorization": f"Bearer {RESEND_API_KEY}",
                    "Content-Type": "application/json",
                    # Cloudflare (in front of Resend's API) 403s urllib's default UA.
                    "User-Agent": "RankBoard/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                delivery = "sent" if 200 <= res.status < 300 else "failed"
        except Exception as exc:
            delivery = "failed"
            print("Could not reach the email provider:", exc)

    cur = db.execute(
        "INSERT INTO emails (to_email, subject, body) VALUES (?, ?, ?)", (email, subject, body)
    )
    row = db.execute("SELECT * FROM emails WHERE id = ?", (cur.lastrowid,)).fetchone()
    # DEV convenience: with no email provider configured, print the message to
    # the server console so local sign-in / password codes are readable without
    # a real inbox. In production RESEND_API_KEY is set, so delivery isn't
    # "outbox" and nothing is printed.
    if delivery == "outbox":
        print("=" * 64)
        print(f"[email outbox — no provider configured] to: {email}")
        print(f"subject: {subject}")
        print(body)
        print("=" * 64)
    return {**dict(row), "delivery": delivery}


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
    return _deliver(db, email=email, subject=subject, body=body)


def send_password_code_email(db: sqlite3.Connection, *, name: str, email: str, code: str) -> dict:
    """Code emailed when a signed-in user wants to change their password."""
    subject = "Your RankBoard password-change code"
    body = "\n".join([
        f"Hi {name.split(' ')[0]},",
        "",
        f"Your password-change verification code is: {code}",
        "",
        "It expires in 10 minutes. Enter it in RankBoard to set a new password.",
        "",
        "If you didn't request this, ignore this email — your password stays the same.",
    ])
    return _deliver(db, email=email, subject=subject, body=body)


def send_login_code_email(db: sqlite3.Connection, *, name: str, email: str, code: str) -> dict:
    """The Admin / Super Admin third-factor code, emailed at sign-in."""
    subject = "Your RankBoard sign-in code"
    body = "\n".join([
        f"Hi {name.split(' ')[0]},",
        "",
        f"Your sign-in verification code is: {code}",
        "",
        "It expires in 10 minutes. Enter it to finish signing in.",
        "",
        "If you didn't just try to sign in, change your password right away.",
    ])
    return _deliver(db, email=email, subject=subject, body=body)
