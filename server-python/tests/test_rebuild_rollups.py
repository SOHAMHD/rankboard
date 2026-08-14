"""Rebuilding email rollups from the event log.

The rebuild has to agree with what `_apply_rollup` would have produced live —
otherwise repairing a row makes it differently wrong. These tests pin the cases
that actually caused trouble: a click that never advanced the status because its
event row was already stored, and events written under Brevo's API spellings
before the name translation existed.
"""

import pytest

from scripts.rebuild_email_rollups import canonical, rollup_for


def ev(event, at, reason=None):
    return {"event": event, "occurred_at": at, "reason": reason}


# ── legacy name repair ────────────────────────────────────────────────

@pytest.mark.parametrize("stored,expected", [
    ("clicks", "click"),
    ("hardBounces", "hard_bounce"),
    ("uniqueOpened", "unique_opened"),
    ("loadedByProxy", "proxy_open"),
    ("requests", "request"),
    ("click", "click"),          # already canonical
    ("opened", "opened"),
    ("somethingNew", "somethingNew"),
])
def test_legacy_api_spellings_are_recognised(stored, expected):
    assert canonical(stored) == expected


# ── status ────────────────────────────────────────────────────────────

def test_a_click_produces_the_clicked_status():
    # The whole point: a message with a click event must read "Clicked", not
    # "Opened". Live, this was missed whenever the event row already existed.
    r = rollup_for([
        ev("request", "2026-08-11 10:00:00"),
        ev("delivered", "2026-08-11 10:00:05"),
        ev("opened", "2026-08-11 10:05:00"),
        ev("click", "2026-08-11 10:06:00"),
    ])
    assert r["status"] == "clicked"


def test_a_click_stored_under_the_api_spelling_also_produces_clicked():
    r = rollup_for([ev("opened", "2026-08-11 10:05:00"),
                    ev("clicks", "2026-08-11 10:06:00")])
    assert r["status"] == "clicked"
    assert r["click_count"] == 1
    assert r["first_clicked_at"] == "2026-08-11 10:06:00"


def test_status_only_moves_forward_regardless_of_event_order():
    # Events arrive out of order; a delivered landing after an opened must not
    # pull the status back down.
    forward = rollup_for([ev("delivered", "2026-08-11 10:00:00"),
                          ev("opened", "2026-08-11 10:05:00")])
    backward = rollup_for([ev("opened", "2026-08-11 10:05:00"),
                           ev("delivered", "2026-08-11 10:00:00")])
    assert forward["status"] == backward["status"] == "opened"


def test_a_complaint_outranks_a_click():
    # A spam report is the fact someone needs to act on; burying it under
    # "clicked" is how a deliverability problem goes unnoticed.
    r = rollup_for([ev("click", "2026-08-11 10:06:00"),
                    ev("spam", "2026-08-11 11:00:00")])
    assert r["status"] == "complaint"


def test_a_bounce_reason_is_carried_onto_the_row():
    r = rollup_for([ev("hard_bounce", "2026-08-11 10:00:00", reason="mailbox unavailable")])
    assert r["status"] == "bounced"
    assert r["error"] == "mailbox unavailable"


def test_a_reason_on_a_success_event_is_ignored():
    r = rollup_for([ev("opened", "2026-08-11 10:00:00", reason="noise")])
    assert r["error"] is None


# ── counts and timestamps ─────────────────────────────────────────────

def test_unique_opened_moves_timestamps_without_counting():
    # Brevo emits unique_opened alongside opened for a first open, so counting it
    # too would report every first read as two.
    r = rollup_for([ev("opened", "2026-08-11 10:05:00"),
                    ev("unique_opened", "2026-08-11 10:05:00")])
    assert r["open_count"] == 1
    assert r["first_opened_at"] == "2026-08-11 10:05:00"


def test_a_proxy_open_counts_as_a_read():
    # Apple Mail Privacy Protection prefetching the pixel. Excluded, an entire
    # class of recipient shows as never having opened anything.
    assert rollup_for([ev("proxy_open", "2026-08-11 10:05:00")])["open_count"] == 1


def test_first_and_last_open_bracket_every_read():
    r = rollup_for([ev("opened", "2026-08-11 12:00:00"),
                    ev("opened", "2026-08-11 10:00:00"),
                    ev("opened", "2026-08-11 11:00:00")])
    assert r["open_count"] == 3
    assert r["first_opened_at"] == "2026-08-11 10:00:00"
    assert r["last_opened_at"] == "2026-08-11 12:00:00"


def test_the_earliest_click_wins_even_when_it_arrives_last():
    r = rollup_for([ev("click", "2026-08-11 12:00:00"),
                    ev("click", "2026-08-11 10:00:00")])
    assert r["first_clicked_at"] == "2026-08-11 10:00:00"
    assert r["click_count"] == 2


def test_delivered_at_takes_the_earliest():
    r = rollup_for([ev("delivered", "2026-08-11 10:00:09"),
                    ev("delivered", "2026-08-11 10:00:05")])
    assert r["delivered_at"] == "2026-08-11 10:00:05"


def test_last_event_at_is_the_latest_of_anything():
    r = rollup_for([ev("delivered", "2026-08-11 10:00:00"),
                    ev("opened", "2026-08-11 10:05:00"),
                    ev("click", "2026-08-11 10:06:00")])
    assert r["last_event_at"] == "2026-08-11 10:06:00"


def test_an_empty_event_list_produces_no_status():
    # The caller keeps the row's existing status in this case rather than nulling
    # it — a 'sent' or 'failed' set by the send call has no event behind it.
    r = rollup_for([])
    assert r["status"] is None
    assert r["open_count"] == 0 and r["click_count"] == 0


def test_an_unrecognised_event_does_not_break_the_rebuild():
    r = rollup_for([ev("somethingNew", "2026-08-11 10:00:00"),
                    ev("opened", "2026-08-11 10:05:00")])
    assert r["status"] == "opened"
    assert r["last_event_at"] == "2026-08-11 10:05:00"


# ── agreement with the live path ──────────────────────────────────────

def test_the_rebuild_matches_what_apply_rollup_would_have_written():
    """Same events through both paths must give the same answer."""
    from app.services import email_tracking as et

    events = [
        ev("request", "2026-08-11 10:00:00"),
        ev("delivered", "2026-08-11 10:00:05"),
        ev("opened", "2026-08-11 10:05:00"),
        ev("unique_opened", "2026-08-11 10:05:00"),
        ev("opened", "2026-08-11 11:30:00"),
        ev("click", "2026-08-11 10:06:00"),
    ]
    rebuilt = rollup_for(events)

    # Replay the live rules independently.
    status, opens, clicks = None, 0, 0
    for e in events:
        s = et.EVENT_STATUS.get(e["event"])
        if s and et.status_rank(s) > et.status_rank(status):
            status = s
        if e["event"] in et._OPEN_EVENTS and e["event"] in ("opened", "proxy_open"):
            opens += 1
        if e["event"] == "click":
            clicks += 1

    assert rebuilt["status"] == status == "clicked"
    assert rebuilt["open_count"] == opens == 2
    assert rebuilt["click_count"] == clicks == 1
