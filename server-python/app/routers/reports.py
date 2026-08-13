import json
import os
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..config import (
    EMAIL_LOGO_URL,
    REPORT_ASSET_BASE_URL,
    REPORT_ASSET_DIR,
    UNSUBSCRIBE_URL,
)
from ..db import db_session, get_db
from ..permissions import AUTHOR_ROLES, DELETER_ROLES, SENDER_ROLES
from ..security import require_roles
from ..access import user_can_access_project
from ..services import report_service
from ..services import report_pdf
from ..services import email_service


_MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def _month_year_label(period_key, period_label: str = "") -> str:
    """Human month for the email subject: '2026-07' -> 'July 2026'.

    The stored label already spells the month out, so it wins whenever it
    contains letters. Only when it is missing (or is itself numeric) do we
    parse the key, accepting either order — '2026-07' and '07-2026' both work.
    """
    lbl = (period_label or "").strip()
    if any(c.isalpha() for c in lbl):
        return lbl
    parts = [p for p in re.split(r"[-/_. ]+", str(period_key or "").strip()) if p]
    if len(parts) >= 2:
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            a = b = None
        if a is not None:
            month, year = (b, a) if len(parts[0]) == 4 else (a, b)
            if 1 <= month <= 12 and year > 0:
                return f"{_MONTH_NAMES[month]} {year:04d}"
    return lbl or str(period_key or "")


router = APIRouter()

_EMAIL_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "assets" / "email" / "seo-report-email.html"
)


def _require_project_access(db: sqlite3.Connection, user: sqlite3.Row, project_id: int) -> int:
    if not user_can_access_project(user, project_id, db):
        raise HTTPException(403, "You don't have access to this project's reports.")
    return project_id


def _require_version_access(db: sqlite3.Connection, user: sqlite3.Row, version_id: int) -> int:
    row = db.execute(
        "SELECT project_id FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    return _require_project_access(db, user, row["project_id"])


def _require_active_project(db: sqlite3.Connection, project_id: int) -> None:
    """Refuse work on an archived project.

    Applied to generating and sending only — not to reading an existing report or
    downloading its PDF. A report that was produced while the project was live is
    a record of work done, and should stay readable after the project is archived.
    What must not happen is a *new* report being produced, or one being emailed to
    a client you have stopped working for.
    """
    row = db.execute("SELECT active FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is not None and not row["active"]:
        raise HTTPException(
            409,
            "This project is inactive. Reactivate it before generating or sending reports.",
        )


class GenerateIn(BaseModel):
    projectId: int
    periodKey: str | None = None


@router.post("/generate", status_code=201)
def generate_report(
    body: GenerateIn,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_project_access(db, user, body.projectId)
    _require_active_project(db, body.projectId)
    version = report_service.generate(db, body.projectId, body.periodKey, user["id"])
    return {"version": version}


@router.post("/{version_id}/fork", status_code=201)
def fork_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    version = report_service.fork_for_changes(db, version_id, user["id"])
    return {"version": version}


@router.delete("/{version_id}")
def delete_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*DELETER_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    return report_service.delete_version(db, version_id)


@router.get("")
def list_reports(
    projectId: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_project_access(db, user, projectId)
    return {"versions": report_service.list_versions(db, projectId)}


@router.get("/{version_id}")
def get_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    version = report_service.get_version(db, version_id, include_data=True)
    return {"version": version}


class _SkipCover(Exception):
    """Raised to skip cover rendering when the template has no <img> for it."""


#: Cover filenames are secrets.token_urlsafe(16) + ".png". Anchored and
#: character-restricted so nothing resembling a path can get through — no "..",
#: no slashes, no absolute paths.
_COVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}\.png$")


@router.get("/covers/{name}")
def get_report_cover(name: str):
    """Serve a report cover PNG.

    Deliberately unauthenticated: the recipient's mail client fetches this with
    no cookies or headers from us. The 22-character random filename is the access
    control, which is the same protection the file had when Apache served it
    directly out of public_html.

    Serving through the API rather than as an Apache static file removes the
    dependency on document-root layout, .htaccess rules, hotlink protection and
    mod_security — any of which can silently 403 the image and leave a broken
    picture in a client's inbox.
    """
    if not _COVER_NAME_RE.match(name):
        raise HTTPException(404, "Not found.")

    path = Path(REPORT_ASSET_DIR) / name
    try:
        # resolve() then containment check: belt and braces against traversal.
        base = Path(REPORT_ASSET_DIR).resolve()
        resolved = path.resolve()
        if base not in resolved.parents:
            raise HTTPException(404, "Not found.")
        data = resolved.read_bytes()
    except (OSError, ValueError):
        raise HTTPException(404, "Not found.")

    return Response(
        content=data,
        media_type="image/png",
        headers={
            # Immutable: a cover is written once under a random name and never
            # rewritten, so both mail proxies and browsers can cache it hard.
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Length": str(len(data)),
        },
    )


@router.get("/{version_id}/pdf")
def download_report_pdf(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
):
    """Render one report to PDF.

    Deliberately does NOT take `Depends(get_db)`. FastAPI holds a dependency's
    connection until the response is finalised, so with the pool capped at 10 and
    a Chromium render taking seconds, ten concurrent downloads starved every other
    endpoint in the process of database connections. The reads happen inside
    `db_session()` and the connection goes back before rendering starts.
    """
    with db_session() as db:
        _require_version_access(db, user, version_id)
        version = report_service.get_version(db, version_id, include_data=True)
        blobs = report_service.available_blobs(db, version_id)

    # No database connection held from here on.
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class SendReportIn(BaseModel):
    recipients: list[str]
    cc: list[str] = []
    subject: str | None = None
    message: str | None = None


def _clean_addresses(raw, seen: set[str]) -> tuple[list[str], list[str]]:
    """Split addresses into (valid, invalid), skipping blanks and repeats.

    `seen` is shared across the To and Cc lists and mutated as it goes, so an
    address already on the To line is dropped from the Cc rather than named twice
    in the same message.
    """
    valid: list[str] = []
    invalid: list[str] = []
    for addr in raw or []:
        clean = (addr or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        (valid if email_service._valid_email(clean) else invalid).append(clean)
    return valid, invalid


@router.post("/{version_id}/send")
def send_report(
    version_id: int,
    body: SendReportIn,
    user: sqlite3.Row = Depends(require_roles(*SENDER_ROLES)),
):
    """Render the report and email it.

    No `Depends(get_db)` — see download_report_pdf. This handler is the worse of
    the two: it holds a connection across a Chromium render *and* a base64 PDF
    upload to the mail provider. All reads happen up front and the connection is
    returned before either.
    """
    # One `seen` set for both lists: To wins, so cc'ing someone already on the To
    # line is a no-op rather than a duplicate.
    seen: set[str] = set()
    valid, invalid = _clean_addresses(body.recipients, seen)
    cc_valid, cc_invalid = _clean_addresses(body.cc, seen)
    invalid = invalid + cc_invalid

    if not valid:
        raise HTTPException(422, "Add at least one valid email address.")

    with db_session() as db:
        _require_version_access(db, user, version_id)
        version = report_service.get_version(db, version_id, include_data=True)
        _require_active_project(db, version["projectId"])
        blobs = report_service.available_blobs(db, version_id)
        proj = db.execute(
            "SELECT name, client_name, domain FROM projects WHERE id = ?", (version["projectId"],)
        ).fetchone()

    # No connection held across the render or the upload below. The send itself
    # needs one to write the emails row, so it takes a fresh short-lived session.
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)
    # Two different names, used in two different places:
    #   project_name  - who the mail is addressed to. client_name is the contact
    #                   person ("Dr. Anuranjan"), so this drives the greeting.
    #   company_name  - the business the report is about ("MindBrainTMS"). This is
    #                   what belongs in the subject line and the body sentence; a
    #                   person's name there reads as though the report is about them.
    project_name = (proj["client_name"] or proj["name"]) if proj else "your project"
    company_name = (proj["name"] or proj["client_name"]) if proj else "your project"
    client_domain = (proj["domain"] if proj else "") or ""
    period = version.get("periodKey") or ""

    _content = version.get("content") or {}
    _hdr = next(
        (b for b in (_content.get("blocks") or []) if b.get("type") == "report_header"),
        {},
    )
    period_label = _hdr.get("periodLabel") or _content.get("period_label") or period
    period_range = report_pdf._period_range_label(period, period_label)
    if not client_domain:
        client_domain = _hdr.get("domain") or ""

    # Subject shows the month by name ("July 2026"), not the raw period key
    # ("2026-07"), so it reads the same way as the PDF header and body copy.
    subject_period = _month_year_label(period, period_label)
    subject = (body.subject or "").strip() or f"SEO report for {company_name} — {subject_period}".rstrip(" —")

    intro = (body.message or "").strip()
    if intro:
        email_body = intro
    else:
        email_body = "\n\n".join([
            f"Hi,\n\nPlease find attached the SEO report for {company_name}"
            + (f" ({period_label})" if period_label else "") + ".",
            "Best regards,\nThe SEO Dashboard team",
        ])

    cover_url = ""
    _cover_name = ""   # initialised here: the render below can raise before it's set

    # Only render the cover PNG if the template actually uses it. Rendering costs
    # a Chromium page load and writes a file to disk, and with no <img> in the
    # template nothing would ever fetch it. Driven by the template rather than a
    # setting so re-adding the <img> is the only step needed to switch it back on.
    try:
        _template_src = _EMAIL_TEMPLATE.read_text(encoding="utf-8")
    except OSError:
        _template_src = ""
    # HTML comments stripped first: the template's own documentation quotes both
    # placeholders as examples, which would otherwise read as "yes, wants a cover".
    _live_markup = re.sub(r"<!--.*?-->", "", _template_src, flags=re.S)
    _wants_cover = (
        "{{cover_image_url}}" in _live_markup or "{{cover_filename}}" in _live_markup
    )

    try:
        if not _wants_cover:
            raise _SkipCover()
        _png = report_pdf.render_cover_png(version, blobs)
        Path(REPORT_ASSET_DIR).mkdir(parents=True, exist_ok=True)
        _cover_name = f"{secrets.token_urlsafe(16)}.png"
        _cover_path = Path(REPORT_ASSET_DIR) / _cover_name
        _cover_path.write_bytes(_png)
        os.chmod(_cover_path, 0o644)
        cover_url = f"{REPORT_ASSET_BASE_URL}/{_cover_name}"
    except _SkipCover:
        pass
    except Exception as exc:
        print("report cover thumbnail failed:", exc)

    html_body = None
    try:
        html_body = _EMAIL_TEMPLATE.read_text(encoding="utf-8")
        # The cover filename is random per send, so it can never be hardcoded in
        # the template. Two placeholders are supported:
        #   {{cover_image_url}} — the whole URL, built from REPORT_ASSET_BASE_URL
        #   {{cover_filename}}  — just the file name, for templates that prefer to
        #                         hardcode their own base URL
        cover_filename = _cover_name if cover_url else ""
        if not cover_url:
            # Drop the <img> entirely when there's no cover, so the email shows no
            # broken picture. Matches whichever placeholder the template uses.
            html_body = re.sub(
                r"<img[^>]*\{\{cover_(?:image_url|filename)\}\}[^>]*>", "", html_body
            )
        for _key, _val in {
            "client_name": project_name,
            "client_domain": client_domain,
            "report_month": period_label,
            "period_range": period_range,
            "cover_image_url": cover_url,
            "cover_filename": cover_filename,
            "logo_url": EMAIL_LOGO_URL,
            "unsubscribe_url": UNSUBSCRIBE_URL,
            "year": str(datetime.now().year),
        }.items():
            html_body = html_body.replace("{{" + _key + "}}", _val or "")
    except Exception as exc:
        print("report email template failed, sending text only:", exc)
        html_body = None

    # ONE message to the whole group, rather than the previous separate send per
    # recipient. A Cc header is only honest sitting next to the real To line, so
    # supporting Cc means sending together — and that makes recipients visible to
    # each other, which the previous per-recipient loop did not. Deliberate, and
    # called out in the send dialog so nobody discovers it from a client.
    # A fresh short-lived session for the write. The send itself is the slow part
    # and it needs a connection to log the emails row, so this is scoped as
    # tightly as it can be rather than spanning the render above.
    with db_session() as db:
        outcome = email_service.send_report_email(
            db,
            email=valid,
            cc=cc_valid,
            subject=subject,
            body=email_body,
            html=html_body,
            pdf_bytes=pdf_bytes,
            pdf_filename=filename,
            # Attribution for the Email Log: which client this went out for, and who
            # pressed send. Only the report path has both — the invite and code
            # emails aren't tied to a project.
            project_id=version["projectId"],
            sent_by=user["id"],
        )
    delivery = outcome["delivery"]
    ok = delivery in ("sent", "outbox")

    # Per-address results are kept in the response even though delivery is now
    # all-or-nothing: the caller counts them, and reporting per address stays
    # useful if a Bcc or a retry-per-address path is added later.
    addressed = [{"email": a, "delivery": delivery, "kind": "to"} for a in valid]
    addressed += [{"email": a, "delivery": delivery, "kind": "cc"} for a in cc_valid]

    return {
        "sent": len(addressed) if ok else 0,
        "failed": 0 if ok else len(addressed),
        "skipped": invalid,
        "cc": cc_valid,
        "results": addressed,
    }


@router.get("/{version_id}/blobs")
def get_report_blobs(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    return {"blobs": report_service.available_blobs(db, version_id)}


@router.get("/{version_id}/template-blocks")
def get_template_blocks(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    return {"blocks": report_service.template_blocks(db, version_id)}


class SaveContentIn(BaseModel):
    content: dict


@router.patch("/{version_id}/content")
def save_report_content(
    version_id: int,
    body: SaveContentIn,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    if len(json.dumps(body.content)) > 500_000:
        raise HTTPException(413, "Report document is too large.")
    version = report_service.save_content(db, version_id, body.content, user["id"])
    return {"version": version}
