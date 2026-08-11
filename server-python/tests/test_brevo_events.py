"""Pulling events from Brevo's API and reshaping them for the ingest path.

The API and the webhook describe the same events with different field names, and
that translation is the only place this feed can silently go wrong: a payload
that keeps `messageId` instead of `message-id` still ingests happily, just with
an empty message id — so every event lands unmatched, no status ever advances,
and the Email Log looks exactly as broken as it did before. Hence the tests.
"""

import pytest

from app.services import brevo_events


# ── event-name translation ────────────────────────────────────────────
# The API says "hardBounces" where the webhook says "hard_bounce", and
# EVENT_STATUS is keyed on the webhook spelling. An untranslated name resolves
# to status None: the event stores, the row never advances, and nothing looks
# broken enough to investigate. Every name Brevo can return is pinned here.

@pytest.mark.parametrize("api_name,webhook_name", [
    ("requests", "request"),
    ("clicks", "click"),
    ("uniqueOpened", "unique_opened"),
    ("loadedByProxy", "proxy_open"),
    ("hardBounces", "hard_bounce"),
    ("softBounces", "soft_bounce"),
    ("bounces", "hard_bounce"),
    ("invalid", "invalid_email"),
    ("complaints", "complaint"),
])
def test_api_event_names_are_translated(api_name, webhook_name):
    out = brevo_events.to_webhook_payload({"event": api_name})
    assert out["event"] == webhook_name


@pytest.mark.parametrize("name", [
    "delivered", "opened", "spam", "deferred", "blocked", "error", "unsubscribed",
])
def test_names_that_already_agree_pass_through(name):
    assert brevo_events.to_webhook_payload({"event": name})["event"] == name


def test_translation_is_case_insensitive():
    assert brevo_events.to_webhook_payload({"event": "hardbounces"})["event"] == "hard_bounce"


def test_an_unrecognised_event_is_left_alone_not_dropped():
    # Better stored under its own name — visible in the raw column — than
    # silently discarded because we didn't recognise it.
    assert brevo_events.to_webhook_payload({"event": "somethingNew"})["event"] == "somethingNew"


def test_every_translated_name_resolves_to_a_real_status():
    # The point of the mapping: each output name must be a key EVENT_STATUS
    # actually knows, or the row's status stays put.
    from app.services.email_tracking import EVENT_STATUS

    for api_name in brevo_events._EVENT_NAMES:
        translated = brevo_events.to_webhook_payload({"event": api_name})["event"]
        assert translated in EVENT_STATUS, f"{api_name} -> {translated} is not in EVENT_STATUS"


def test_the_open_events_the_api_reports_all_count_as_reads():
    from app.services.email_tracking import _OPEN_EVENTS

    for api_name in ("opened", "uniqueOpened", "loadedByProxy"):
        translated = brevo_events.to_webhook_payload({"event": api_name})["event"]
        assert translated in _OPEN_EVENTS


# ── field translation ─────────────────────────────────────────────────

def test_messageid_is_renamed_to_the_webhook_spelling():
    # ingest_event reads "message-id" (or "message_id"). The API sends
    # "messageId". Without this rename the id is dropped and the event can never
    # be matched to its emails row.
    out = brevo_events.to_webhook_payload({
        "event": "delivered",
        "email": "a@b.com",
        "messageId": "<202608@smtp-relay.mailin.fr>",
    })
    assert out["message-id"] == "<202608@smtp-relay.mailin.fr>"


def test_an_already_correct_message_id_survives():
    out = brevo_events.to_webhook_payload({"message-id": "<x@y>"})
    assert out["message-id"] == "<x@y>"


def test_a_numeric_message_id_becomes_a_string():
    # ingest_event does str() on it anyway, but the dedupe key is text — an int
    # sneaking through would compare differently.
    out = brevo_events.to_webhook_payload({"messageId": 12345})
    assert out["message-id"] == "12345"


def test_the_date_field_is_left_alone():
    # _event_time already looks for "date" in its fallback order, and the API's
    # value carries a UTC offset that _to_utc_string converts correctly.
    # Renaming it to ts_event would strip that advantage for no gain.
    out = brevo_events.to_webhook_payload({"date": "2026-08-11T15:34:02.000+05:30"})
    assert out["date"] == "2026-08-11T15:34:02.000+05:30"
    assert "ts_event" not in out


def test_url_is_mapped_to_link_for_clicks():
    out = brevo_events.to_webhook_payload({"event": "click", "url": "https://example.com/a"})
    assert out["link"] == "https://example.com/a"


def test_an_existing_link_is_not_overwritten_by_url():
    out = brevo_events.to_webhook_payload({"link": "https://kept", "url": "https://ignored"})
    assert out["link"] == "https://kept"


def test_unknown_fields_pass_through_untouched():
    # They end up in the `raw` column, which is where anyone debugging looks.
    out = brevo_events.to_webhook_payload({"event": "spam", "tag": "report", "somethingNew": 1})
    assert out["tag"] == "report"
    assert out["somethingNew"] == 1


def test_translation_does_not_mutate_the_input():
    original = {"messageId": "<x@y>"}
    brevo_events.to_webhook_payload(original)
    assert original == {"messageId": "<x@y>"}


# ── fetching and pagination ───────────────────────────────────────────

def _fake_pages(monkeypatch, pages):
    """Serve canned responses, recording the params each call was made with."""
    calls = []

    def fake_request(params):
        calls.append(params)
        return pages[len(calls) - 1] if len(calls) <= len(pages) else {"events": []}

    monkeypatch.setattr(brevo_events, "BREVO_API_KEY", "test-key")
    monkeypatch.setattr(brevo_events, "_request", fake_request)
    return calls


def test_a_single_short_page_stops_immediately(monkeypatch):
    calls = _fake_pages(monkeypatch, [{"events": [{"event": "delivered"}]}])
    events = brevo_events.fetch_events(page_size=100)
    assert len(events) == 1
    assert len(calls) == 1          # no pointless second request


def test_a_full_page_triggers_another_request(monkeypatch):
    calls = _fake_pages(monkeypatch, [
        {"events": [{"event": "delivered"}, {"event": "opened"}]},   # full
        {"events": [{"event": "click"}]},                            # short
    ])
    events = brevo_events.fetch_events(page_size=2)
    assert [e["event"] for e in events] == ["delivered", "opened", "click"]
    assert [c["offset"] for c in calls] == [0, 2]


def test_events_are_requested_oldest_first(monkeypatch):
    # A run that hits the page cap should leave the NEWEST events unread, so the
    # next run picks them up. Descending order would strand the oldest forever.
    calls = _fake_pages(monkeypatch, [{"events": []}])
    brevo_events.fetch_events()
    assert calls[0]["sort"] == "asc"


def test_the_day_window_is_passed_through(monkeypatch):
    calls = _fake_pages(monkeypatch, [{"events": []}])
    brevo_events.fetch_events(days=7)
    assert calls[0]["days"] == 7


def test_page_size_is_capped_at_brevos_limit(monkeypatch):
    calls = _fake_pages(monkeypatch, [{"events": []}])
    brevo_events.fetch_events(page_size=999999)
    assert calls[0]["limit"] == brevo_events.MAX_PAGE


def test_runaway_pagination_raises_rather_than_looping(monkeypatch):
    # Every page comes back full, so the loop would never end on its own.
    monkeypatch.setattr(brevo_events, "BREVO_API_KEY", "test-key")
    monkeypatch.setattr(brevo_events, "_request",
                        lambda params: {"events": [{"event": "delivered"}] * params["limit"]})
    with pytest.raises(brevo_events.BrevoEventsError) as exc:
        brevo_events.fetch_events(page_size=10, max_pages=3)
    assert "max-pages" in str(exc.value)


def test_a_missing_api_key_is_reported_before_any_request(monkeypatch):
    monkeypatch.setattr(brevo_events, "BREVO_API_KEY", "")
    with pytest.raises(brevo_events.BrevoEventsError) as exc:
        brevo_events.fetch_events()
    assert "BREVO_API_KEY" in str(exc.value)


def test_a_missing_events_key_is_treated_as_empty(monkeypatch):
    _fake_pages(monkeypatch, [{}])
    assert brevo_events.fetch_events() == []


# ── ingesting ─────────────────────────────────────────────────────────

def test_the_tally_counts_each_outcome(monkeypatch):
    outcomes = iter(["stored", "duplicate", "ignored"])
    monkeypatch.setattr(brevo_events, "to_webhook_payload", lambda item: item)
    from app.services import email_tracking
    monkeypatch.setattr(email_tracking, "ingest_event", lambda db, payload: next(outcomes))

    tally = brevo_events.ingest_all(None, [{"event": "a"}, {"event": "b"}, {"event": "c"}])
    assert tally == {"received": 3, "stored": 1, "duplicates": 1, "ignored": 1, "errors": 0}


def test_one_failing_event_does_not_abandon_the_rest(monkeypatch):
    # A cron run that aborts on the first bad event leaves the remaining ones
    # unrecorded until someone notices, which may be never.
    def flaky(db, payload):
        if payload["event"] == "boom":
            raise ValueError("nope")
        return "stored"

    from app.services import email_tracking
    monkeypatch.setattr(email_tracking, "ingest_event", flaky)

    tally = brevo_events.ingest_all(
        None, [{"event": "delivered"}, {"event": "boom"}, {"event": "opened"}]
    )
    assert tally["stored"] == 2
    assert tally["errors"] == 1


def test_non_dict_entries_are_ignored_not_fatal(monkeypatch):
    from app.services import email_tracking
    monkeypatch.setattr(email_tracking, "ingest_event", lambda db, payload: "stored")
    tally = brevo_events.ingest_all(None, ["not a dict", {"event": "delivered"}])
    assert tally["ignored"] == 1
    assert tally["stored"] == 1
