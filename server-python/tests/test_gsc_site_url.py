"""Search Console property strings, which Google matches exactly.

Two of this install's projects were mistyped for months and neither showed a
useful symptom: one carried a spurious `www.`, one was missing its trailing
slash. Both looked configured, and every request failed later with a raw Google
403/400 that reads like broken credentials rather than a typo.
"""

import pytest
from fastapi import HTTPException

from app.routers.projects import normalize_gsc_site_url, verify_gsc_site_url

SITES = [
    "https://sattvaconnect.com/",
    "https://dishaimpex.com/",
    "https://www.perthlocalplumbing.com.au/",
    "sc-domain:symbient.com.au",
]


@pytest.fixture
def sites(monkeypatch):
    """Pretend the service account can read SITES."""
    monkeypatch.setattr("app.routers.projects.list_sites", lambda: (list(SITES), None))


# ── normalising ───────────────────────────────────────────────────────

def test_a_missing_trailing_slash_is_added():
    # A URL-prefix property always ends in "/" and Google rejects it without.
    # Deterministic, so it's safe to fix silently. This was project #25.
    assert normalize_gsc_site_url("https://dishaimpex.com") == "https://dishaimpex.com/"


def test_an_existing_trailing_slash_is_left_alone():
    assert normalize_gsc_site_url("https://dishaimpex.com/") == "https://dishaimpex.com/"


def test_a_path_is_not_given_a_slash():
    # A property can be a subdirectory; don't invent a trailing slash mid-path.
    assert normalize_gsc_site_url("https://example.com/shop") == "https://example.com/shop"


def test_www_is_never_stripped():
    # www and bare are separate properties. "Correcting" one to the other would
    # silently point a project at a different site's data.
    assert normalize_gsc_site_url("https://www.sattvaconnect.com/") == "https://www.sattvaconnect.com/"


@pytest.mark.parametrize("raw,expected", [
    ("sc-domain:Example.COM", "sc-domain:example.com"),
    ("sc-domain:example.com/", "sc-domain:example.com"),
    ("  sc-domain: example.com ", "sc-domain:example.com"),
])
def test_domain_properties_are_lowercased_and_unslashed(raw, expected):
    assert normalize_gsc_site_url(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_clears_the_field(raw):
    assert normalize_gsc_site_url(raw) is None


def test_whitespace_is_trimmed():
    assert normalize_gsc_site_url("  https://sattvaconnect.com/  ") == "https://sattvaconnect.com/"


# ── verifying against the real property list ──────────────────────────

def test_a_real_property_is_accepted(sites):
    verify_gsc_site_url("https://sattvaconnect.com/")  # no raise


def test_a_domain_property_is_accepted(sites):
    verify_gsc_site_url("sc-domain:symbient.com.au")


def test_a_stray_www_is_rejected_with_the_right_suggestion(sites):
    # Project #1's actual bug.
    with pytest.raises(HTTPException) as exc:
        verify_gsc_site_url("https://www.sattvaconnect.com/")
    assert exc.value.status_code == 400
    assert "https://sattvaconnect.com/" in exc.value.detail


def test_a_missing_www_is_rejected_with_the_right_suggestion(sites):
    # The mirror image: the real property is the www one.
    with pytest.raises(HTTPException) as exc:
        verify_gsc_site_url("https://perthlocalplumbing.com.au/")
    assert "https://www.perthlocalplumbing.com.au/" in exc.value.detail


def test_an_unknown_domain_is_rejected_without_a_guess(sites):
    with pytest.raises(HTTPException) as exc:
        verify_gsc_site_url("https://somebodyelse.com/")
    assert "Did you mean" not in exc.value.detail


def test_blank_is_not_verified(sites):
    verify_gsc_site_url(None)
    verify_gsc_site_url("")


# ── the checks must not become a hard dependency on Google ────────────

def test_an_unreachable_google_does_not_block_saving(monkeypatch):
    """Editing a project can't depend on a third party being up."""
    monkeypatch.setattr(
        "app.routers.projects.list_sites",
        lambda: ([], "Could not list Search Console properties: connection reset"),
    )
    verify_gsc_site_url("https://anything-at-all.com/")


def test_no_service_account_key_does_not_block_saving(monkeypatch):
    # An install with no key still needs to be able to record the URL.
    monkeypatch.setattr(
        "app.routers.projects.list_sites",
        lambda: ([], "Search Console is not configured on the server (no service-account key set)."),
    )
    verify_gsc_site_url("https://anything-at-all.com/")


def test_an_empty_property_list_does_not_block_saving(monkeypatch):
    # Distinguishing "account sees nothing" from "call failed" isn't worth
    # refusing every save over.
    monkeypatch.setattr("app.routers.projects.list_sites", lambda: ([], None))
    verify_gsc_site_url("https://anything-at-all.com/")


# ── the repair script's matcher ───────────────────────────────────────

def test_the_repair_script_pairs_both_real_mistakes():
    from scripts.fix_gsc_site_urls import core

    assert core("https://www.sattvaconnect.com/") == core("https://sattvaconnect.com/")
    assert core("https://dishaimpex.com") == core("https://dishaimpex.com/")
    assert core("sc-domain:symbient.com.au") == core("https://www.symbient.com.au/")
    assert core("https://sattvaconnect.com/") != core("https://dishaimpex.com/")
