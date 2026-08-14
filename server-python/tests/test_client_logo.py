"""The per-project client logo.

Stored as a data URI on `projects.client_logo`, shown on the project card and the
dashboard sidebar, and copied into a report's header block when the report is
generated so it reaches the PDF.

Two things carry real risk and are covered hardest:

  * these strings are interpolated into HTML that headless Chromium executes while
    rendering a report, so what counts as an image has to be narrow
  * the API and the renderer must agree on that definition — a format accepted on
    upload but discarded at render time looks like a successful upload and a
    mysteriously missing logo
"""

import base64

import pytest

from app.services.images import (
    DATA_IMAGE_RE,
    MAX_LOGO_CHARS,
    normalize_logo,
)
from app.services.report_industry import _safe_image_src
from app.services.report_service import _seed_header_logo


def uri(mime="image/png", payload=b"not really a png") -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode()}"


PNG = uri()


# ── what counts as a logo ─────────────────────────────────────────────

@pytest.mark.parametrize("mime", ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"])
def test_the_raster_formats_are_accepted(mime):
    assert normalize_logo(uri(mime)) == uri(mime)


def test_the_mime_type_is_case_insensitive():
    assert normalize_logo(uri("IMAGE/PNG")) is not None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_means_no_logo(value):
    # This is how the form's Remove button clears the field.
    assert normalize_logo(value) is None


def test_whitespace_inside_the_payload_is_stripped():
    # Legal base64 and browsers accept it, but it inflates the row and every
    # report blob carrying a copy.
    assert "\n" not in normalize_logo("data:image/png;base64,AAAA\nBBBB\n  CCCC")


# ── what doesn't ──────────────────────────────────────────────────────

def test_svg_is_refused_with_a_reason():
    """An SVG is a document — it can carry script, external refs and CSS.

    These strings end up inside HTML that Chromium executes to render the PDF.
    """
    with pytest.raises(ValueError) as exc:
        normalize_logo("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=")
    assert "SVG" in str(exc.value)
    assert "PNG" in str(exc.value)


def test_a_url_is_refused_with_the_reason_it_cannot_work():
    # Linking is the obvious thing to try, and why it's disallowed isn't
    # guessable: the renderer embeds rather than fetches.
    with pytest.raises(ValueError) as exc:
        normalize_logo("https://example.com/logo.png")
    assert "uploaded" in str(exc.value)


@pytest.mark.parametrize("value", [
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "data:application/pdf;base64,AAAA",
    "<img src=x onerror=alert(1)>",
    "data:image/png,notbase64",
    "AAAA",
])
def test_anything_else_is_refused(value):
    with pytest.raises(ValueError):
        normalize_logo(value)


def test_a_quote_cannot_be_smuggled_through_the_payload():
    # The payload class admits only base64 characters, so nothing can break out
    # of the attribute it lands in.
    with pytest.raises(ValueError):
        normalize_logo('data:image/png;base64,AAA" onload="alert(1)')


def test_an_oversized_image_is_refused_before_it_is_stored():
    huge = "data:image/png;base64," + "A" * (MAX_LOGO_CHARS + 1)
    with pytest.raises(ValueError) as exc:
        normalize_logo(huge)
    assert "too large" in str(exc.value)


def test_a_logo_at_the_limit_is_allowed():
    at_limit = "data:image/png;base64," + "A" * (MAX_LOGO_CHARS - len("data:image/png;base64,"))
    assert len(at_limit) == MAX_LOGO_CHARS
    assert normalize_logo(at_limit) is not None


# ── the API and the renderer agree ────────────────────────────────────

@pytest.mark.parametrize("value", [
    "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
    "https://example.com/logo.png",
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
])
def test_what_the_api_refuses_the_renderer_also_drops(value):
    """The failure this prevents is silent: upload succeeds, logo never appears."""
    with pytest.raises(ValueError):
        normalize_logo(value)
    assert _safe_image_src(value) == ""


def test_what_the_api_accepts_the_renderer_renders():
    stored = normalize_logo(PNG)
    assert _safe_image_src(stored) != ""


def test_both_sides_use_one_expression():
    # Not two copies that drift: report_industry imports this one.
    from app.services import report_industry
    assert report_industry._DATA_IMAGE_RE is DATA_IMAGE_RE


# ── copying it into a generated report ────────────────────────────────

class FakeDb:
    def __init__(self, logo):
        self.logo = logo

    def execute(self, sql, params=()):
        assert "client_logo" in sql
        row = {"client_logo": self.logo}
        return type("C", (), {"fetchone": lambda _self: row})()


def document(header_extra=None):
    header = {"id": "header", "type": "report_header", "projectName": "Sattva Connect"}
    header.update(header_extra or {})
    return {"type": "report_document", "blocks": [header, {"id": "x", "type": "rich_text"}]}


def header_of(doc):
    return next(b for b in doc["blocks"] if b.get("type") == "report_header")


def test_the_project_logo_lands_in_the_header():
    doc = document()
    _seed_header_logo(FakeDb(PNG), 1, doc)
    assert header_of(doc)["clientLogo"] == PNG


def test_a_project_without_a_logo_changes_nothing():
    doc = document()
    _seed_header_logo(FakeDb(None), 1, doc)
    assert "clientLogo" not in header_of(doc)


def test_an_existing_logo_is_not_overwritten():
    # A fork carries the author's choice; re-seeding would undo a deliberate
    # per-report override.
    chosen = uri(payload=b"the one the author picked")
    doc = document({"clientLogo": chosen})
    _seed_header_logo(FakeDb(PNG), 1, doc)
    assert header_of(doc)["clientLogo"] == chosen


def test_a_document_with_no_header_block_is_left_alone():
    doc = {"type": "report_document", "blocks": [{"id": "x", "type": "rich_text"}]}
    _seed_header_logo(FakeDb(PNG), 1, doc)
    assert doc["blocks"] == [{"id": "x", "type": "rich_text"}]


@pytest.mark.parametrize("doc", [{}, {"blocks": []}, {"blocks": None}])
def test_an_empty_document_does_not_raise(doc):
    # build_document returns a blocks-less shape when there's nothing to report.
    _seed_header_logo(FakeDb(PNG), 1, doc)


def test_non_dict_blocks_are_skipped():
    doc = {"blocks": ["a string", None, {"type": "report_header"}]}
    _seed_header_logo(FakeDb(PNG), 1, doc)
    assert doc["blocks"][2]["clientLogo"] == PNG
