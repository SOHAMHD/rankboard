"""Date ranges can't ask for days that haven't happened.

The pickers used to have relative bounds only — the From date capped at the To
date, the To date floored at From — so nothing stopped a range running into next
month. GA4 and Search Console have no data for those days, so the answer came
back empty and read as a broken integration rather than an impossible question.

Clamped rather than rejected: on the 13th, the useful part of "1st to the 31st"
is the first thirteen days, and refusing the whole range would throw that away.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.routers.projects import _clamp_to_today, _ga_range


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def days_from_now(n: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")


# ── the clamp itself ──────────────────────────────────────────────────

def test_a_future_date_is_trimmed_to_today():
    assert _clamp_to_today(days_from_now(30)) == today()


def test_tomorrow_is_trimmed():
    # The off-by-one case: tomorrow is the most likely mistake and the easiest to
    # get wrong with a >= instead of a >.
    assert _clamp_to_today(days_from_now(1)) == today()


def test_today_itself_is_allowed():
    assert _clamp_to_today(today()) == today()


def test_a_past_date_is_untouched():
    assert _clamp_to_today("2020-01-15") == "2020-01-15"


def test_yesterday_is_untouched():
    assert _clamp_to_today(days_from_now(-1)) == days_from_now(-1)


@pytest.mark.parametrize("value", [None, ""])
def test_blank_values_pass_through(value):
    assert _clamp_to_today(value) == value


@pytest.mark.parametrize("token", ["yesterday", "28daysAgo", "today", "not-a-date"])
def test_non_dates_pass_through_untouched(token):
    # GA4 accepts relative tokens. Mangling one into a calendar date would change
    # which timezone resolves the window — the whole reason presets use tokens.
    assert _clamp_to_today(token) == token


# ── the GA4 range builder ─────────────────────────────────────────────

class Body:
    def __init__(self, start=None, end=None, preset=None):
        self.start, self.end, self.preset = start, end, preset


def test_a_custom_range_is_clamped_at_both_ends():
    start, end = _ga_range(Body(start=days_from_now(5), end=days_from_now(40)))
    assert start == end == today()


def test_a_custom_range_keeps_its_valid_start():
    # The point of clamping rather than rejecting: the past half of the range is
    # still a real question.
    start, end = _ga_range(Body(start="2026-08-01", end=days_from_now(18)))
    assert start == "2026-08-01"
    assert end == today()


def test_a_wholly_past_range_is_untouched():
    assert _ga_range(Body(start="2026-06-01", end="2026-06-30")) == ("2026-06-01", "2026-06-30")


def test_a_preset_still_uses_relative_tokens():
    # Presets must NOT be turned into calendar dates: GA4 resolves the tokens in
    # the property's own reporting timezone, which is the only one that decides
    # which day a session belongs to.
    assert _ga_range(Body(preset=28)) == ("28daysAgo", "yesterday")


def test_an_absurd_preset_falls_back_to_the_dates():
    # Out of range, so it isn't treated as a preset — and the dates it falls back
    # to are still clamped.
    start, end = _ga_range(Body(start="2026-01-01", end=days_from_now(60), preset=99999))
    assert start == "2026-01-01"
    assert end == today()
