import base64
import json
import smtplib
import sqlite3
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr

from ..config import (
    APP_URL,
    BREVO_API_KEY,
    EMAIL_FROM,
    SMTP_HOST,
    SMTP_PASS,
    SMTP_PORT,
    SMTP_SECURE,
    SMTP_USER,
)


def _send_via_smtp(*, email: str, subject: str, body: str, html: str | None = None,
                   attachments=None) -> str:
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_FROM
        msg["To"] = email
        msg["Subject"] = subject
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")
        for att in attachments or []:
            maintype, _, subtype = (att.get("mime") or "application/octet-stream").partition("/")
            msg.add_attachment(
                att["content"],
                maintype=maintype,
                subtype=subtype or "octet-stream",
                filename=att["filename"],
            )

        if SMTP_SECURE == "ssl":
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
        with server:
            if SMTP_SECURE in ("starttls", "tls"):
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return "sent"
    except Exception as exc:
        print("SMTP send failed:", exc)
        return "failed"


def _send_via_brevo(*, email: str, subject: str, body: str, html: str | None = None, attachments=None) -> str:
    try:
        from_name, from_addr = parseaddr(EMAIL_FROM)
        sender = {"email": from_addr}
        if from_name:
            sender["name"] = from_name

        payload = {
            "sender": sender,
            "to": [{"email": email}],
            "subject": subject,
            "textContent": body,
        }
        if html:
            payload["htmlContent"] = html
        if attachments:
            payload["attachment"] = [
                {"name": a["filename"], "content": base64.b64encode(a["content"]).decode()}
                for a in attachments
            ]
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode(),
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "SEODashboard/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            return "sent" if 200 <= res.status < 300 else "failed"
    except Exception as exc:
        print("Could not reach the email provider:", exc)
        return "failed"


def _deliver(db: sqlite3.Connection, *, email: str, subject: str, body: str,
             html: str | None = None, attachments=None) -> dict:
    if SMTP_HOST:
        delivery = _send_via_smtp(email=email, subject=subject, body=body, html=html,
                                  attachments=attachments)
    elif BREVO_API_KEY:
        delivery = _send_via_brevo(email=email, subject=subject, body=body, html=html,
                                   attachments=attachments)
    else:
        delivery = "outbox"

    cur = db.execute(
        "INSERT INTO emails (to_email, subject, body) VALUES (?, ?, ?)", (email, subject, body)
    )
    row = db.execute("SELECT * FROM emails WHERE id = ?", (cur.lastrowid,)).fetchone()
    if delivery == "outbox":
        note = " (+1 attachment)" if attachments else ""
        print("=" * 64)
        print(f"[email outbox — no provider configured] to: {email}{note}")
        print(f"subject: {subject}")
        print(body)
        print("=" * 64)
    return {**dict(row), "delivery": delivery}


def _valid_email(addr: str) -> bool:
    name, email = parseaddr(addr or "")
    if not email or email.count("@") != 1:
        return False
    local, _, domain = email.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def send_report_email(
    db: sqlite3.Connection,
    *,
    email: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    html: str | None = None,
) -> dict:
    return _deliver(
        db,
        email=email,
        subject=subject,
        body=body,
        html=html,
        attachments=[{"filename": pdf_filename, "content": pdf_bytes, "mime": "application/pdf"}],
    )


def send_invite_email(db: sqlite3.Connection, *, name: str, email: str, role: str, temp_password: str) -> dict:
    subject = "You've been added to SEO Dashboard"
    body = "\n".join([
        f"Hi {name.split(' ')[0]},",
        "",
        f"You've been added to the SEO Dashboard workspace as {role}.",
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
    subject = "Your SEO Dashboard password-change code"
    body = "\n".join([
        f"Hi {name.split(' ')[0]},",
        "",
        f"Your password-change verification code is: {code}",
        "",
        "It expires in 10 minutes. Enter it in SEO Dashboard to set a new password.",
        "",
        "If you didn't request this, ignore this email — your password stays the same.",
    ])
    return _deliver(db, email=email, subject=subject, body=body)


def send_login_code_email(db: sqlite3.Connection, *, name: str, email: str, code: str) -> dict:
    subject = "Your SEO Dashboard sign-in code"
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
