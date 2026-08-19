"""The Indeed alert-email parser, written against the saved fixture.

The loud-failure test is the important one here: if Indeed rewrites its HTML
and the selectors stop matching, the parser must shout rather than quietly
report zero jobs — a silent zero is indistinguishable from a quiet job market.
"""

from __future__ import annotations

import logging

import pytest

from salesradar.providers.indeed_email import (
    IndeedEmailParseError,
    IndeedEmailProvider,
    _looks_like_a_real_alert,
    _parse_salary_min,
    required_scopes,
)

from .fixtures import postings as p


@pytest.fixture
def provider(config):
    return IndeedEmailProvider(
        gmail_service=None, provider_config=config.provider_section("indeed_email")
    )


class TestParsing:
    def test_extracts_every_card(self, provider, alert_html):
        jobs = provider.parse_html(alert_html)
        assert len(jobs) == 4

    def test_titles(self, provider, alert_html):
        titles = [j.title for j in provider.parse_html(alert_html)]
        assert "Account Executive - Mid Market" in titles
        assert "Sales Development Representative" in titles
        assert "Retail Sales Associate" in titles

    def test_company_and_location(self, provider, alert_html):
        job = provider.parse_html(alert_html)[0]
        assert job.company == "Riverstone Technologies"
        assert job.location == "Toronto, ON"

    def test_salary_snippet_captured(self, provider, alert_html):
        job = provider.parse_html(alert_html)[0]
        assert job.salary_text == "$70,000 - $135,000 a year"
        assert job.salary_min == 70000.0

    def test_apply_url_captured(self, provider, alert_html):
        job = provider.parse_html(alert_html)[0]
        assert "ca.indeed.com/rc/clk" in job.url
        assert "jk=a1b2c3d4e5f6a7b8" in job.url

    def test_job_key_becomes_the_source_id(self, provider, alert_html):
        job = provider.parse_html(alert_html)[0]
        assert job.source_id == "a1b2c3d4e5f6a7b8"

    def test_source_is_tagged(self, provider, alert_html):
        assert all(j.source == "indeed_email" for j in provider.parse_html(alert_html))

    def test_card_missing_a_salary_still_parses(self, provider, alert_html):
        jobs = provider.parse_html(alert_html)
        commission_card = next(j for j in jobs if "Summit" in j.company)
        assert commission_card.salary_text is None
        assert commission_card.title == "Sales Representative - Entry Level"

    def test_received_time_becomes_posted_at(self, provider, alert_html):
        received = p.hours_ago(2)
        jobs = provider.parse_html(alert_html, received_at=received)
        assert all(j.posted_at == received for j in jobs)


class TestLoudFailure:
    def test_drifted_selectors_raise(self, config, alert_html):
        """A large email that yields nothing means the template moved."""
        broken = dict(config.provider_section("indeed_email"))
        broken["selectors"] = {"job_card": ["td.this-class-no-longer-exists"]}
        provider = IndeedEmailProvider(gmail_service=None, provider_config=broken)

        with pytest.raises(IndeedEmailParseError):
            provider.parse_html(alert_html, message_id="msg-123")

    def test_the_raw_html_is_logged_on_failure(self, config, alert_html, caplog):
        broken = dict(config.provider_section("indeed_email"))
        broken["selectors"] = {"job_card": ["td.gone"]}
        provider = IndeedEmailProvider(gmail_service=None, provider_config=broken)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(IndeedEmailParseError):
                provider.parse_html(alert_html, message_id="msg-123")

        record = next(r for r in caplog.records if hasattr(r, "raw_html"))
        assert "Riverstone" in record.raw_html
        assert record.message_id == "msg-123"

    def test_a_genuine_no_new_jobs_email_does_not_raise(self, provider):
        """Indeed does send empty alerts. Crying wolf on those is worse."""
        html = (
            "<html><body>"
            + "<p>There are no new jobs matching your alert today.</p>"
            + "<div>filler</div>" * 400
            + "</body></html>"
        )
        assert provider.parse_html(html) == []

    def test_an_empty_body_does_not_raise(self, provider):
        assert provider.parse_html("") == []

    def test_a_tiny_body_does_not_raise(self, provider):
        assert provider.parse_html("<html><body>hi</body></html>") == []


class TestSelectorFallback:
    def test_the_first_matching_selector_wins(self, config, alert_html):
        """Old selectors can stay in the list as fallbacks while new ones are
        added at the top — that's the whole point of the ordered list."""
        cfg = dict(config.provider_section("indeed_email"))
        cfg["selectors"] = dict(cfg["selectors"])
        cfg["selectors"]["job_card"] = ["div.brand-new-layout", "td.job_card"]
        provider = IndeedEmailProvider(gmail_service=None, provider_config=cfg)

        assert len(provider.parse_html(alert_html)) == 4


class TestSalaryParsing:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("$70,000 - $135,000 a year", 70000.0),
            ("$55,000 a year", 55000.0),
            ("$17.50 an hour", 36400.0),
            ("$4,000 a month", 48000.0),
            ("Competitive salary", None),
            (None, None),
            ("", None),
        ],
    )
    def test_annualizes_correctly(self, text, expected):
        assert _parse_salary_min(text) == expected


class TestScopes:
    def test_marking_read_requires_the_modify_scope(self):
        """Documented tension: read-only cannot mark a message read."""
        assert required_scopes(mark_read=True) == [
            "https://www.googleapis.com/auth/gmail.modify"
        ]

    def test_readonly_when_not_marking_read(self):
        assert required_scopes(mark_read=False) == [
            "https://www.googleapis.com/auth/gmail.readonly"
        ]


class TestEmptyAlertDetection:
    def test_short_html_is_not_a_real_alert(self):
        assert not _looks_like_a_real_alert("<html>short</html>")

    def test_large_html_is_a_real_alert(self):
        assert _looks_like_a_real_alert("<div>x</div>" * 500)

    def test_no_new_jobs_marker_wins_over_size(self):
        html = "<div>no new jobs</div>" + "<span>y</span>" * 500
        assert not _looks_like_a_real_alert(html)
