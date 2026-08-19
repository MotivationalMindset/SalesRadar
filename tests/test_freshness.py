"""Freshness — the 24-hour cutoff."""

from __future__ import annotations

from salesradar.filters import freshness
from salesradar.models import Verdict

from .fixtures import postings as p


def test_recent_posting_accepted(freshness_rules):
    result = freshness.check(p.FRESH, freshness_rules)
    assert result.verdict is Verdict.ACCEPT
    assert "2.0h ago" in result.reason


def test_two_day_old_posting_rejected(freshness_rules):
    result = freshness.check(p.STALE, freshness_rules)
    assert result.verdict is Verdict.REJECT
    assert "older than 24h" in result.reason


def test_just_inside_the_window_accepted(freshness_rules):
    assert freshness.check(p.BORDERLINE, freshness_rules).verdict is Verdict.ACCEPT


def test_just_outside_the_window_rejected(freshness_rules):
    job = p.make_job(posted_at=p.hours_ago(24.5))
    assert freshness.check(job, freshness_rules).verdict is Verdict.REJECT


def test_missing_date_is_kept_by_default(freshness_rules):
    """The seen-jobs table stops repeats, so keeping is the safer default."""
    result = freshness.check(p.NO_DATE, freshness_rules)
    assert result.verdict is Verdict.ACCEPT
    assert "no posting date" in result.reason


def test_missing_date_can_be_configured_to_reject():
    rules = {"max_age_hours": 24, "keep_if_date_missing": False}
    assert freshness.check(p.NO_DATE, rules).verdict is Verdict.REJECT


def test_future_timestamp_treated_as_clock_skew(freshness_rules):
    job = p.make_job(posted_at=p.hours_ago(-3))
    assert freshness.check(job, freshness_rules).verdict is Verdict.ACCEPT


def test_window_is_configurable():
    rules = {"max_age_hours": 1, "keep_if_date_missing": True}
    assert freshness.check(p.FRESH, rules).verdict is Verdict.REJECT
