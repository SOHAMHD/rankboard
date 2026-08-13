import base64
import json
import smtplib
import time
import sqlite3
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import parseaddr

from . import redaction
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


def _as_addresses(value) -> list[str]:
    """Normalise a To/Cc argument to a list of non-empty addresses.

    `email=` accepts either a single address or a list: most senders here mail one
    person, while the report send mails a group with a visible Cc.
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [a.strip() for a in value if a and a.strip()]


#: Value of the X-Mailin-custom header we attach to every Brevo send.
#:
#: Brevo echoes this header back verbatim on every webhook event, so it is a
#: correlation key we control. message_id alone would nearly always be enough,
#: but it is assigned by Brevo *after* the send call returns — if that response
#: is lost to a timeout we have a row in `emails` and no way to match its
#: events. The row id travels with the message instead, so nothing is orphaned.
_TRACK_PREFIX = "email_log_id:"


def _tracking_header(email_id: int | None) -> dict[str, str]:
    return {"X-Mailin-custom": f"{_TRACK_PREFIX}{email_id}"} if email_id else {}


def _send_via_smtp(*, email, subject: str, body: str, html: str | None = None,
                   attachments=None, cc=None, email_id: int | None = None) -> dict:
    try:
        to_list = _as_addresses(email)
        cc_list = _as_addresses(cc)

        msg = EmailMessage()
        msg["From"] = EMAIL_FROM
        msg["To"] = ", ".join(to_list)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = subject
        for _hk, _hv in _tracking_header(email_id).items():
            msg[_hk] = _hv
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
            # send_message reads the recipients off the To/Cc/Bcc headers, so the
            # Cc above is delivered as well as displayed — no separate list needed.
            server.send_message(msg)
        # Plain SMTP has no event feedback loop, so a message sent this way stops
        # at "sent" and never advances to delivered/opened. Brevo's SMTP relay is
        # the exception: it fires the same webhooks as the API, and those events
        # match on the X-Mailin-custom header set above.
        return {"status": "sent", "message_id": msg.get("Message-ID") or "", "error": None}
    except Exception as exc:
        print("SMTP send failed:", exc)
        return {"status": "failed", "message_id": "", "error": str(exc)[:500]}


#: Retry only what is worth retrying: rate limiting, provider-side faults, and
#: transport failures. A 400 or 401 is our fault and will fail identically every
#: time, so retrying one just delays the error.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = (1.0, 3.0)


def _with_retries(post):
    """Call `post()` with backoff on transient provider failures.

    A report send is expensive — the PDF is already rendered and base64-encoded by
    this point — and a single transient 5xx used to mark the row `failed` with no
    recourse but pressing Send again, which re-rendered everything and created a
    second `emails` row. Two extra attempts a few seconds apart cost nothing and
    remove most of that.
    """
    last_exc = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            status, raw = post()
            if status in _RETRY_STATUSES and attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                continue
            return status, raw
        except urllib.error.HTTPError as exc:
            if exc.code in _RETRY_STATUSES and attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                last_exc = exc
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Connection reset, DNS blip, read timeout — all worth one more go.
            if attempt < _RETRY_ATTEMPTS - 1:
                time.sleep(_RETRY_BACKOFF[attempt])
                last_exc = exc
                continue
            raise
    raise last_exc if last_exc else RuntimeError("send failed with no exception")


def _send_via_brevo(*, email, subject: str, body: str, html: str | None = None,
                    attachments=None, cc=None, email_id: int | None = None,
                    category: str | None = None) -> dict:
    try:
        from_name, from_addr = parseaddr(EMAIL_FROM)
        sender = {"email": from_addr}
        if from_name:
            sender["name"] = from_name

        payload = {
            "sender": sender,
            "to": [{"email": a} for a in _as_addresses(email)],
            "subject": subject,
            "textContent": body,
        }
        cc_list = _as_addresses(cc)
        if cc_list:
            payload["cc"] = [{"email": a} for a in cc_list]
        if html:
            payload["htmlContent"] = html
        if attachments:
            payload["attachment"] = [
                {"name": a["filename"], "content": base64.b64encode(a["content"]).decode()}
                for a in attachments
            ]
        headers = _tracking_header(email_id)
        if headers:
            payload["headers"] = headers
        if category:
            # Shows up as `tag` on the webhook payload and in Brevo's own UI, so
            # the two views of the same send agree on what kind of mail it was.
            payload["tags"] = [category]
        def _post():
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
                return res.status, (res.read().decode() or "{}")

        status, raw = _with_retries(_post)
        if not 200 <= status < 300:
            return {"status": "failed", "message_id": "",
                    "error": f"Brevo returned HTTP {status}"}
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            data = {}
        # A single-recipient send answers with `messageId`; a batch answers with
        # `messageIds`. Both are stored the same way — one `emails` row is one
        # message, and the batch form only appears for Brevo's batch endpoint,
        # which this code does not use.
        message_id = data.get("messageId") or ""
        if not message_id and isinstance(data.get("messageIds"), list) and data["messageIds"]:
            message_id = data["messageIds"][0]
        return {"status": "sent", "message_id": str(message_id or ""), "error": None}
    except urllib.error.HTTPError as exc:
        # Brevo puts the actual reason in the body — "unrecognised sender", an
        # exhausted quota. Without reading it every failure looked identical.
        try:
            detail = exc.read().decode()[:300]
        except Exception:
            detail = ""
        print("Email provider rejected the message:", exc, detail)
        return {"status": "failed", "message_id": "",
                "error": f"HTTP {exc.code}: {detail or exc.reason}"[:500]}
    except Exception as exc:
        print("Could not reach the email provider:", exc)
        return {"status": "failed", "message_id": "", "error": str(exc)[:500]}


def _deliver(db: sqlite3.Connection, *, email, subject: str, body: str,
             html: str | None = None, attachments=None, cc=None,
             category: str = "other", project_id: int | None = None,
             sent_by: int | None = None) -> dict:
    """Send one message and record it, then keep recording what happens to it.

    The `emails` row is written *before* the provider call, not after. It has to
    be: the row id is stamped into an X-Mailin-custom header so Brevo's webhook
    events can be matched back to it, and a row created afterwards would have no
    id to stamp. It also means a send that hangs or crashes still leaves a
    'queued' row behind rather than vanishing — a message we can't account for
    is worse than one we know we lost.
    """
    to_list = _as_addresses(email)
    cc_list = _as_addresses(cc)
    to_logged = ", ".join(to_list)
    cc_logged = ", ".join(cc_list) or None

    # Redact before storing, not just before displaying. An invite body carries a
    # working temporary password and an OTP body carries a live code; keeping
    # either in the database serves nothing once the send has happened, and any
    # dump or replica carried them indefinitely. email_log still redacts on read,
    # for rows written before this.
    stored_body = redaction.redact(body, category)
    stored_html = redaction.redact(html, category)

    cur = db.execute(
        """INSERT INTO emails (to_email, cc_email, subject, body, html_body,
                               category, status, provider, attachment_count,
                               project_id, sent_by)
           VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)""",
        (to_logged, cc_logged, subject, stored_body, stored_html, category,
         "smtp" if SMTP_HOST else ("brevo" if BREVO_API_KEY else "outbox"),
         len(attachments or []), project_id, sent_by),
    )
    email_id = cur.lastrowid

    if SMTP_HOST:
        result = _send_via_smtp(email=to_list, subject=subject, body=body, html=html,
                                attachments=attachments, cc=cc_list, email_id=email_id)
    elif BREVO_API_KEY:
        result = _send_via_brevo(email=to_list, subject=subject, body=body, html=html,
                                 attachments=attachments, cc=cc_list, email_id=email_id,
                                 category=category)
    else:
        result = {"status": "outbox", "message_id": "", "error": None}

    delivery = result["status"]
    # message_id is written unconditionally, but status/error only while the row
    # is still 'queued'. The row id went out in a header before the provider call
    # returned, so Brevo can (and on a slow response does) deliver the message
    # and fire its `delivered` webhook while we are still blocked on urlopen.
    # Writing 'sent' over that afterwards would rewind the row, and would erase a
    # bounce reason the webhook had already recorded.
    db.execute(
        """UPDATE emails
              SET message_id    = ?,
                  status        = CASE WHEN status = 'queued' THEN ? ELSE status END,
                  error         = CASE WHEN status = 'queued' THEN ? ELSE error END,
                  last_event_at = GREATEST(COALESCE(last_event_at, datetime('now')),
                                           datetime('now'))
            WHERE id = ?""",
        (result.get("message_id") or None, delivery, result.get("error"), email_id),
    )

    row = db.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    if delivery == "outbox":
        note = " (+1 attachment)" if attachments else ""
        print("=" * 64)
        print(f"[email outbox — no provider configured] to: {to_logged}{note}")
        if cc_logged:
            print(f"cc: {cc_logged}")
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


def clean_recipient_set(primary: str, ccs) -> tuple[str, list[str]]:
    """Validate and dedupe a saved recipient set. Returns (primary, cc_list).

    Lives here rather than in a router because two of them need it — the project
    recipients endpoint and user onboarding — and because it has to agree with
    `_valid_email` above, which is what the send path uses. One validator means
    an address that saves is an address that sends.

    The primary wins over Cc on a collision, matching the shared `seen` set in
    the report send endpoint.

    Raises ValueError on an invalid address rather than dropping it. These are
    stored defaults: an address quietly discarded here would make every future
    report to that client miss someone, and nobody would find out for months.
    Callers turn this into whatever their framework wants (routers raise a 422).
    """
    primary = (primary or "").strip()
    if not _valid_email(primary):
        raise ValueError(f"Not a valid email: {primary or '(empty)'}")

    seen = {primary.lower()}
    clean: list[str] = []
    for raw in ccs or []:
        addr = (raw or "").strip()
        if not addr:
            continue
        if addr.lower() in seen:  # equals the primary, or a repeated Cc
            continue
        if not _valid_email(addr):
            raise ValueError(f"Not a valid email: {addr}")
        seen.add(addr.lower())
        clean.append(addr)
    return primary, clean


def upsert_project_recipients(db, *, project_id: int, primary: str, ccs: list[str]) -> None:
    """Write one project's recipient set, replacing whatever was there.

    json.dumps plus the ::jsonb cast because psycopg has no adapter for a bare
    Python list on a jsonb column. updated_at is set explicitly since the column
    default only fires on INSERT.
    """
    db.execute(
        """INSERT INTO project_recipients (project_id, primary_email, cc_emails)
           VALUES (?, ?, ?::jsonb)
           ON CONFLICT (project_id) DO UPDATE
               SET primary_email = EXCLUDED.primary_email,
                   cc_emails     = EXCLUDED.cc_emails,
                   updated_at    = to_char((now() AT TIME ZONE 'UTC'),
                                           'YYYY-MM-DD HH24:MI:SS')""",
        (project_id, primary, json.dumps(ccs)),
    )


def send_report_email(
    db: sqlite3.Connection,
    *,
    email,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    html: str | None = None,
    cc=None,
    project_id: int | None = None,
    sent_by: int | None = None,
) -> dict:
    """Send one report email. `email` may be a single address or a list.

    Recipients on a report send go out together in one message so the Cc is
    meaningful — a Cc header is only honest if the To it sits beside is the real
    one. That does mean recipients can see each other; see the note in
    routers/reports.py where the list is assembled.
    """
    return _deliver(
        db,
        email=email,
        subject=subject,
        body=body,
        html=html,
        cc=cc,
        attachments=[{"filename": pdf_filename, "content": pdf_bytes, "mime": "application/pdf"}],
        category="report",
        project_id=project_id,
        sent_by=sent_by,
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
    return _deliver(db, email=email, subject=subject, body=body, category="invite")


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
    return _deliver(db, email=email, subject=subject, body=body, category="password_code")


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
    return _deliver(db, email=email, subject=subject, body=body, category="login_code")
