"""Address handling for the report email, including Cc."""

import pytest

from app.services import email_service


# ── address normalisation ─────────────────────────────────────────────

def test_a_single_address_becomes_a_one_item_list():
    # Most senders here mail one person and pass a bare string; the report send
    # passes a list. Both have to work.
    assert email_service._as_addresses("a@b.com") == ["a@b.com"]


def test_a_list_is_kept_in_order():
    assert email_service._as_addresses(["a@b.com", "c@d.com"]) == ["a@b.com", "c@d.com"]


@pytest.mark.parametrize("value", [None, "", "   ", [], [""], ["  ", None]])
def test_empty_inputs_produce_no_addresses(value):
    assert email_service._as_addresses(value) == []


def test_surrounding_whitespace_is_stripped():
    assert email_service._as_addresses(["  a@b.com  "]) == ["a@b.com"]


# ── the To / Cc split in the send endpoint ────────────────────────────
# _clean_addresses shares one `seen` set between the two lists, which is what
# stops an address being named on both lines of the same message.

def _split(recipients, cc):
    from app.routers.reports import _clean_addresses

    seen = set()
    valid, invalid = _clean_addresses(recipients, seen)
    cc_valid, cc_invalid = _clean_addresses(cc, seen)
    return valid, cc_valid, invalid + cc_invalid


def test_recipients_and_cc_are_kept_apart():
    to, cc, bad = _split(["a@b.com"], ["c@d.com"])
    assert to == ["a@b.com"]
    assert cc == ["c@d.com"]
    assert bad == []


def test_an_address_on_both_lines_stays_only_on_the_to_line():
    to, cc, _ = _split(["a@b.com"], ["a@b.com"])
    assert to == ["a@b.com"]
    assert cc == []


def test_the_duplicate_check_ignores_case():
    to, cc, _ = _split(["Alice@B.com"], ["alice@b.com"])
    assert to == ["Alice@B.com"]
    assert cc == []


def test_repeats_within_the_cc_list_collapse():
    to, cc, _ = _split(["a@b.com"], ["c@d.com", "c@d.com"])
    assert cc == ["c@d.com"]


def test_a_malformed_cc_is_reported_not_sent():
    to, cc, bad = _split(["a@b.com"], ["not-an-email"])
    assert cc == []
    assert bad == ["not-an-email"]


def test_blank_cc_entries_are_ignored_silently():
    to, cc, bad = _split(["a@b.com"], ["", "   "])
    assert cc == []
    assert bad == []


def test_no_cc_at_all_is_fine():
    to, cc, bad = _split(["a@b.com"], [])
    assert (to, cc, bad) == (["a@b.com"], [], [])


# ── what the provider payloads look like ──────────────────────────────

def test_brevo_payload_carries_to_and_cc(monkeypatch):
    captured = {}

    class _FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = __import__("json").loads(req.data.decode())
        return _FakeResponse()

    monkeypatch.setattr(email_service, "EMAIL_FROM", "Reports <no-reply@example.com>")
    monkeypatch.setattr(email_service.urllib.request, "urlopen", fake_urlopen)

    result = email_service._send_via_brevo(
        email=["a@b.com", "b@b.com"], cc=["boss@b.com"],
        subject="s", body="t",
    )

    assert result == "sent"
    assert captured["payload"]["to"] == [{"email": "a@b.com"}, {"email": "b@b.com"}]
    assert captured["payload"]["cc"] == [{"email": "boss@b.com"}]
    assert captured["payload"]["sender"] == {"email": "no-reply@example.com", "name": "Reports"}


def test_brevo_payload_omits_cc_when_there_is_none(monkeypatch):
    captured = {}

    class _FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["payload"] = __import__("json").loads(req.data.decode())
        return _FakeResponse()

    monkeypatch.setattr(email_service.urllib.request, "urlopen", fake_urlopen)
    email_service._send_via_brevo(email="a@b.com", subject="s", body="t")

    # An empty cc array is not the same as no cc key; don't send one.
    assert "cc" not in captured["payload"]
