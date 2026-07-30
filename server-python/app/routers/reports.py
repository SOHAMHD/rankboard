"""REPORT ROUTES — trigger and inspect frozen report versions.

This slice is the DATA FOUNDATION: generate a frozen version, fork one for
changes, list a project's versions, and fetch one version's frozen blob to
INSPECT it. There is NO rendering, sending, status-transition-to-sent, or public
link here — those are later slices.

Every endpoint is gated to report AUTHORS (require_roles(*AUTHOR_ROLES)) AND to
the caller's project access. IMPORTANT: "Team" is an author but is a project-
SCOPED role (not staff), so role-gating alone is NOT enough — each handler
resolves the target project and calls _require_project_access /
_require_version_access to prevent cross-project (cross-client) access (IDOR).
Sending to a client is further restricted to SENDER_ROLES.
"""
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
from ..db import get_db
from ..permissions import AUTHOR_ROLES, DELETER_ROLES, SENDER_ROLES
from ..security import require_roles
from ..access import user_can_access_project
from ..services import report_service
from ..services import report_pdf
from ..services import email_service

router = APIRouter()

# The monthly report email's HTML body (the design handoff template). Rendered
# with simple {{placeholder}} substitution in send_report() below — there are no
# loops or conditionals in the markup, so this avoids a Jinja2 dependency.
_EMAIL_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "assets" / "email" / "seo-report-email.html"
)


def _require_project_access(db: sqlite3.Connection, user: sqlite3.Row, project_id: int) -> int:
    """403 unless this user may access the project. Staff (Super Admin/Admin)
    always pass; Team/Client must be linked via user_projects. Closes the IDOR
    where a non-staff author role (Team) could reach reports for projects it
    isn't assigned to."""
    if not user_can_access_project(user, project_id, db):
        raise HTTPException(403, "You don't have access to this project's reports.")
    return project_id


def _require_version_access(db: sqlite3.Connection, user: sqlite3.Row, version_id: int) -> int:
    """Resolve version_id → project_id (404 if the version is missing), then
    enforce project access. Returns the project_id."""
    row = db.execute(
        "SELECT project_id FROM report_version WHERE id = ?", (version_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Report version not found.")
    return _require_project_access(db, user, row["project_id"])


class GenerateIn(BaseModel):
    projectId: int
    periodKey: str | None = None  # defaults to the current month server-side


@router.post("/generate", status_code=201)
def generate_report(
    body: GenerateIn,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Generate a fresh frozen report version for a project+period.

    gather → validate → freeze. Fails loudly (writes nothing) when no usable
    rank snapshot or Moz row exists for the period (422), or when an unsent
    version already exists for that project+period (409 — fork it instead).
    Returns the new version including its frozen data blob."""
    _require_project_access(db, user, body.projectId)
    version = report_service.generate(db, body.projectId, body.periodKey, user["id"])
    return {"version": version}


@router.post("/{version_id}/fork", status_code=201)
def fork_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Fork a version for "changes": a new draft that copies the source's frozen
    data and editable content verbatim (never re-gathers), with
    parentVersionId set to the source. 404 if the source doesn't exist."""
    _require_version_access(db, user, version_id)
    version = report_service.fork_for_changes(db, version_id, user["id"])
    return {"version": version}


@router.delete("/{version_id}")
def delete_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*DELETER_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """HARD-delete a report version (irreversible row removal). Gated SERVER-SIDE
    to DELETER_ROLES (Super Admin / Admin) — Team/Client get 403 here regardless
    of what the UI shows. Allowed for ANY status incl. 'sent' (the destructive
    case the UI double-confirms). 404 if the version doesn't exist. Deleting a fork
    parent is safe: children's parent_version_id is set NULL by the FK."""
    _require_version_access(db, user, version_id)
    return report_service.delete_version(db, version_id)


@router.get("")
def list_reports(
    projectId: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """List a project's report versions, newest first (metadata only: id,
    period, status, parent, created_at — no blob)."""
    _require_project_access(db, user, projectId)
    return {"versions": report_service.list_versions(db, projectId)}


@router.get("/{version_id}")
def get_report(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Fetch one version's frozen data_json + editable content_json so the editor
    can rehydrate (prose + chips with their saved formats). 404 if missing."""
    _require_version_access(db, user, version_id)
    version = report_service.get_version(db, version_id, include_data=True)
    return {"version": version}


@router.get("/{version_id}/pdf")
def download_report_pdf(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Render this version to a downloadable PDF (headless Chromium) and stream it
    back. Author-gated like the rest; reads the EXISTING frozen content_json +
    data_json, generates ON DEMAND, stores nothing. 404 if the version is missing.

    PROOF SLICE: only the cover + one section are rendered (see report_pdf). This is
    a SYNC handler on purpose — FastAPI runs it in a worker thread, so the
    Playwright sync API has no running asyncio loop to clash with."""
    _require_version_access(db, user, version_id)
    version = report_service.get_version(db, version_id, include_data=True)
    # Pass the resolved scalar blobs so inserted-data chips in edited narrative
    # text render their frozen values in the PDF (not just the on-screen view).
    blobs = report_service.available_blobs(db, version_id)
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class SendReportIn(BaseModel):
    recipients: list[str]        # one or more email addresses
    subject: str | None = None   # optional custom subject; a sensible default is built
    message: str | None = None   # optional note prepended to the email body


@router.post("/{version_id}/send")
def send_report(
    version_id: int,
    body: SendReportIn,
    user: sqlite3.Row = Depends(require_roles(*SENDER_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Email this report's PDF to one OR MANY recipients.

    Renders the PDF ONCE (same on-demand path as the download endpoint — reads the
    frozen content_json + data_json, stores nothing), then sends a copy to each
    recipient via the configured transport (SMTP > Brevo > dev outbox). Returns a
    per-recipient delivery result so the UI can show partial success.

    GATING: restricted to SENDER_ROLES (Super Admin / Admin) — Team may author a
    report but must NOT send it to clients. Also project-scoped like the rest.

    422 if no valid recipient is supplied. A single recipient failing to send does
    NOT fail the whole request — its status comes back as "failed" in `results`."""
    _require_version_access(db, user, version_id)
    # ── Validate + de-duplicate recipients up front ──────────────────────────
    raw = body.recipients or []
    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[str] = []
    for addr in raw:
        clean = (addr or "").strip()
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        (valid if email_service._valid_email(clean) else invalid).append(clean)

    if not valid:
        raise HTTPException(422, "Add at least one valid email address.")

    # ── Render the PDF once (shared across every recipient) ───────────────────
    version = report_service.get_version(db, version_id, include_data=True)
    blobs = report_service.available_blobs(db, version_id)
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)

    # A friendly, project-aware subject + body when the caller doesn't supply one.
    proj = db.execute(
        "SELECT name, domain FROM projects WHERE id = ?", (version["projectId"],)
    ).fetchone()
    project_name = proj["name"] if proj else "your project"
    client_domain = (proj["domain"] if proj else "") or ""
    period = version.get("periodKey") or ""

    # periodKey is "2026-06", but the email template wants "June 2026" in the
    # heading and a full date range in the eyebrow. Both come off the frozen
    # report_header block, with report_pdf's own helper for the range.
    _content = version.get("content") or {}
    _hdr = next(
        (b for b in (_content.get("blocks") or []) if b.get("type") == "report_header"),
        {},
    )
    period_label = _hdr.get("periodLabel") or _content.get("period_label") or period
    period_range = report_pdf._period_range_label(period, period_label)
    if not client_domain:
        client_domain = _hdr.get("domain") or ""

    subject = (body.subject or "").strip() or f"SEO report for {project_name} — {period}".rstrip(" —")

    # PLAIN-TEXT body. The caller's note now REPLACES the boilerplate instead of
    # being prepended to it (previously both appeared). This stays as the
    # text/plain alternative alongside the HTML template below — clients that
    # block HTML fall back to it, and sending both improves deliverability.
    intro = (body.message or "").strip()
    if intro:
        email_body = intro
    else:
        email_body = "\n\n".join([
            f"Hi,\n\nPlease find attached the SEO report for {project_name}"
            + (f" ({period_label})" if period_label else "") + ".",
            "Best regards,\nThe SEO Dashboard team",
        ])

    # ── Cover thumbnail ───────────────────────────────────────────────────────
    # Page 1 of the report, rendered to PNG and written into the PUBLIC asset
    # dir so the email can reference it by absolute url (mail clients fetch
    # images with no cookies or auth, so it cannot be access-controlled — the
    # random filename is what keeps the url unguessable).
    #
    # Best-effort by design: a thumbnail failure must NOT fail the send. The PDF
    # attachment is the actual deliverable.
    cover_url = ""
    try:
        _png = report_pdf.render_cover_png(version, blobs)
        Path(REPORT_ASSET_DIR).mkdir(parents=True, exist_ok=True)
        _cover_name = f"{secrets.token_urlsafe(16)}.png"
        _cover_path = Path(REPORT_ASSET_DIR) / _cover_name
        _cover_path.write_bytes(_png)
        # Force world-READABLE (0644). The PNG inherits the service's umask,
        # which on a hardened/cPanel host is often 0077 -> the file lands as
        # 0600. Apache serves static files as a DIFFERENT user, so it gets a 403
        # and the recipient sees a broken image — with nothing in the app log,
        # because the write itself succeeded. Setting the mode explicitly makes
        # the send independent of whatever umask the unit happens to run with.
        os.chmod(_cover_path, 0o644)
        cover_url = f"{REPORT_ASSET_BASE_URL}/{_cover_name}"
    except Exception as exc:
        print("report cover thumbnail failed:", exc)

    # ── HTML body ─────────────────────────────────────────────────────────────
    html_body = None
    try:
        html_body = _EMAIL_TEMPLATE.read_text(encoding="utf-8")
        if not cover_url:
            # Drop the <img> rather than emitting src="" — an empty src renders
            # a broken-image icon in several clients.
            html_body = re.sub(
                r"<img[^>]*\{\{cover_image_url\}\}[^>]*>", "", html_body
            )
        for _key, _val in {
            "client_name": project_name,
            "client_domain": client_domain,
            "report_month": period_label,
            "period_range": period_range,
            "cover_image_url": cover_url,
            "logo_url": EMAIL_LOGO_URL,
            "unsubscribe_url": UNSUBSCRIBE_URL,
            "year": str(datetime.now().year),
        }.items():
            html_body = html_body.replace("{{" + _key + "}}", _val or "")
    except Exception as exc:
        # Template missing or unreadable → send the plain-text version only.
        print("report email template failed, sending text only:", exc)
        html_body = None

    # ── Deliver one copy per recipient; collect per-address results ───────────
    results = []
    for addr in valid:
        outcome = email_service.send_report_email(
            db,
            email=addr,
            subject=subject,
            body=email_body,
            html=html_body,
            pdf_bytes=pdf_bytes,
            pdf_filename=filename,
        )
        results.append({"email": addr, "delivery": outcome["delivery"]})

    return {
        "sent": sum(1 for r in results if r["delivery"] in ("sent", "outbox")),
        "failed": sum(1 for r in results if r["delivery"] == "failed"),
        "skipped": invalid,   # addresses rejected as malformed (never attempted)
        "results": results,
    }


@router.get("/{version_id}/blobs")
def get_report_blobs(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """The SCALAR blobs available to insert, resolved from this version's FROZEN
    data — { name, label, type, source, group, currentValue, deltaValue }. The
    single source the palette AND the live preview consume. 404 if missing."""
    _require_version_access(db, user, version_id)
    return {"blobs": report_service.available_blobs(db, version_id)}


@router.get("/{version_id}/template-blocks")
def get_template_blocks(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """The canonical TEMPLATE blocks rebuilt from this version's FROZEN data_json,
    so the editable document can RE-ADD a section the author removed (the data is
    still in data_json). Read-only; no live fetch; data_json untouched. 404 if
    missing."""
    _require_version_access(db, user, version_id)
    return {"blocks": report_service.template_blocks(db, version_id)}


class SaveContentIn(BaseModel):
    content: dict  # the editor document (TipTap/ProseMirror JSON), NOT rendered HTML


@router.patch("/{version_id}/content")
def save_report_content(
    version_id: int,
    body: SaveContentIn,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    """Save the editor's document into content_json. DRAFT-ONLY: 409 if the version
    is in_review/sent (locked). 404 if missing. Returns the updated version.

    SECURITY: this document is later rendered by a server-side headless browser,
    so it is UNTRUSTED input. Project access is enforced here, a size cap rejects
    absurd payloads, and — critically — the renderer escapes/allowlists every
    value it emits (see report_pdf / report_industry), so stored content can
    never inject markup or a URL into the render browser."""
    _require_version_access(db, user, version_id)
    # Cheap DoS guard: reject a wildly oversized document before storing it.
    if len(json.dumps(body.content)) > 500_000:
        raise HTTPException(413, "Report document is too large.")
    version = report_service.save_content(db, version_id, body.content, user["id"])
    return {"version": version}