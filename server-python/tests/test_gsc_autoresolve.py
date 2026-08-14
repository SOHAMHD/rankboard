"""Resolving a project's Search Console property from its domain.

The form used to ask for the same site twice — a bare domain for Moz/backlinks,
and Google's own notation for Search Console — and the second field is where both
of this install's misconfigurations came from. It's now derived from the first.

The rule that matters most here is that an inconclusive lookup must never clear a
working property: the form no longer has a field to restore it with, so a
momentary Google outage would otherwise silently disconnect a project.
"""

import pytest

from app.routers.projects import (
    _property_core,
    match_gsc_properties,
    resolve_gsc_site_url,
)

SITES = [
    "https://sattvaconnect.com/",
    "https://www.perthlocalplumbing.com.au/",
    "sc-domain:symbient.com.au",
    "https://example.com/",
    "https://www.example.com/",   # same host, separate property — ambiguous
]


@pytest.fixture
def sites(monkeypatch):
    monkeypatch.setattr("app.routers.projects.list_sites", lambda: (list(SITES), None))


@pytest.fixture
def google_down(monkeypatch):
    monkeypatch.setattr("app.routers.projects.list_sites", lambda: ([], "connection reset"))


# ── reducing a property to its host ───────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("https://example.com/", "example.com"),
    ("https://www.example.com/", "example.com"),
    ("http://example.com", "example.com"),
    ("sc-domain:example.com", "example.com"),
    ("sc-domain:EXAMPLE.com", "example.com"),
    ("example.com", "example.com"),
    ("www.example.com", "example.com"),
    ("https://example.com/shop/", "example.com"),
])
def test_every_notation_reduces_to_the_same_host(value, expected):
    assert _property_core(value) == expected


def test_different_hosts_do_not_collide():
    assert _property_core("https://example.com/") != _property_core("https://example.org/")


# ── matching ──────────────────────────────────────────────────────────

def test_a_bare_domain_finds_its_url_prefix_property(sites):
    assert match_gsc_properties("sattvaconnect.com") == ["https://sattvaconnect.com/"]


def test_a_bare_domain_finds_a_www_property(sites):
    # The user types the domain; the property happens to be the www one.
    assert match_gsc_properties("perthlocalplumbing.com.au") == [
        "https://www.perthlocalplumbing.com.au/"
    ]


def test_a_bare_domain_finds_a_domain_property(sites):
    assert match_gsc_properties("symbient.com.au") == ["sc-domain:symbient.com.au"]


def test_a_domain_with_two_properties_returns_both(sites):
    assert len(match_gsc_properties("example.com")) == 2


def test_an_unknown_domain_matches_nothing(sites):
    assert match_gsc_properties("somebodyelse.com") == []


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_blank_domain_matches_nothing(sites, value):
    assert match_gsc_properties(value) == []


def test_matching_is_empty_when_google_is_unreachable(google_down):
    # Never "no property" — callers must read this as "couldn't decide".
    assert match_gsc_properties("sattvaconnect.com") == []


# ── resolving ─────────────────────────────────────────────────────────

def test_a_single_match_is_used(sites):
    assert resolve_gsc_site_url("sattvaconnect.com", None) == "https://sattvaconnect.com/"


def test_an_explicit_value_wins_over_the_domain(sites):
    # A property need not be the domain in the Moz field — a subdirectory
    # property, for instance.
    assert resolve_gsc_site_url(
        "sattvaconnect.com", "https://example.com/shop/"
    ) == "https://example.com/shop/"


def test_an_explicit_value_is_still_normalised(sites):
    assert resolve_gsc_site_url(None, "https://example.com") == "https://example.com/"


def test_an_unknown_domain_resolves_to_nothing(sites):
    assert resolve_gsc_site_url("somebodyelse.com", None) is None


def test_ambiguity_is_not_guessed(sites):
    # Picking one of a bare/www pair would report a different site's numbers.
    assert resolve_gsc_site_url("example.com", None) is None


def test_ambiguity_keeps_a_current_value_that_is_one_of_the_candidates(sites):
    assert resolve_gsc_site_url(
        "example.com", None, current="https://www.example.com/"
    ) == "https://www.example.com/"


# ── the rule that prevents a silent disconnection ─────────────────────

def test_an_unreachable_google_keeps_the_current_property(google_down):
    assert resolve_gsc_site_url(
        "sattvaconnect.com", None, current="https://sattvaconnect.com/"
    ) == "https://sattvaconnect.com/"


def test_clearing_the_domain_keeps_the_current_property(sites):
    # Emptying the domain field is not a request to disconnect Search Console.
    assert resolve_gsc_site_url(
        "", None, current="https://sattvaconnect.com/"
    ) == "https://sattvaconnect.com/"


def test_changing_the_domain_moves_the_property(sites):
    # The counterpart: a real domain change must not leave the old site attached.
    assert resolve_gsc_site_url(
        "symbient.com.au", None, current="https://sattvaconnect.com/"
    ) == "sc-domain:symbient.com.au"


def test_a_domain_with_no_property_clears_a_stale_one(sites):
    # Deliberately not preserved: keeping it would report the previous client's
    # numbers under the new domain.
    assert resolve_gsc_site_url(
        "somebodyelse.com", None, current="https://sattvaconnect.com/"
    ) is None
