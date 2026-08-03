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


@router.get("/{version_id}/pdf")
def download_report_pdf(
    version_id: int,
    user: sqlite3.Row = Depends(require_roles(*AUTHOR_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
    version = report_service.get_version(db, version_id, include_data=True)
    blobs = report_service.available_blobs(db, version_id)
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class SendReportIn(BaseModel):
    recipients: list[str]
    subject: str | None = None
    message: str | None = None


@router.post("/{version_id}/send")
def send_report(
    version_id: int,
    body: SendReportIn,
    user: sqlite3.Row = Depends(require_roles(*SENDER_ROLES)),
    db: sqlite3.Connection = Depends(get_db),
):
    _require_version_access(db, user, version_id)
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

    version = report_service.get_version(db, version_id, include_data=True)
    blobs = report_service.available_blobs(db, version_id)
    pdf_bytes = report_pdf.render_pdf(version, blobs)
    filename = report_pdf.pdf_filename(version)

    proj = db.execute(
        "SELECT name, domain FROM projects WHERE id = ?", (version["projectId"],)
    ).fetchone()
    project_name = proj["name"] if proj else "your project"
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

    subject = (body.subject or "").strip() or f"SEO report for {project_name} — {period}".rstrip(" —")

    intro = (body.message or "").strip()
    if intro:
        email_body = intro
    else:
        email_body = "\n\n".join([
            f"Hi,\n\nPlease find attached the SEO report for {project_name}"
            + (f" ({period_label})" if period_label else "") + ".",
            "Best regards,\nThe SEO Dashboard team",
        ])

    cover_url = ""
    try:
        _png = report_pdf.render_cover_png(version, blobs)
        Path(REPORT_ASSET_DIR).mkdir(parents=True, exist_ok=True)
        _cover_name = f"{secrets.token_urlsafe(16)}.png"
        _cover_path = Path(REPORT_ASSET_DIR) / _cover_name
        _cover_path.write_bytes(_png)
        os.chmod(_cover_path, 0o644)
        cover_url = f"{REPORT_ASSET_BASE_URL}/{_cover_name}"
    except Exception as exc:
        print("report cover thumbnail failed:", exc)

    html_body = None
    try:
        html_body = _EMAIL_TEMPLATE.read_text(encoding="utf-8")
        if not cover_url:
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
        print("report email template failed, sending text only:", exc)
        html_body = None

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
        "skipped": invalid,
        "results": results,
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
