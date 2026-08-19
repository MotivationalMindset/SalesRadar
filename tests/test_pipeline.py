"""End-to-end filter pipeline: ordering, uncertainty propagation, dry-run."""

from __future__ import annotations

from salesradar.filters import pipeline
from salesradar.models import Verdict

from .fixtures import postings as p


class TestOrdering:
    def test_a_stale_job_stops_at_freshness(self, config):
        """Filters run in order and stop at the first rejection, so a two-day-
        old posting is never handed to the commission filter."""
        screening = pipeline.screen_job(p.STALE, config)
        assert screening.rejected_by is not None
        assert screening.rejected_by.rule == "freshness"
        assert len(screening.results) == 1

    def test_commission_runs_before_geo(self, config):
        screening = pipeline.screen_job(p.COMMISSION_ONLY, config)
        assert screening.rejected_by is not None
        assert screening.rejected_by.rule == "commission"

    def test_geo_runs_before_title(self, config):
        job = p.make_job(
            title="Warehouse Supervisor",
            location="Ottawa, ON",
            latitude=45.4215,
            longitude=-75.6972,
        )
        screening = pipeline.screen_job(job, config)
        assert screening.rejected_by is not None
        assert screening.rejected_by.rule == "geo"

    def test_a_good_job_runs_every_filter(self, config):
        screening = pipeline.screen_job(p.make_job(), config)
        assert screening.passed
        assert [r.rule for r in screening.results] == [
            "freshness",
            "commission",
            "geo",
            "title",
        ]


class TestOutcomes:
    def test_a_qualifying_posting_passes(self, config):
        assert pipeline.screen_job(p.BASE_PLUS_COMMISSION, config).passed

    def test_uncertainty_is_recorded_on_the_job(self, config):
        screening = pipeline.screen_job(p.CONFLICTING_SIGNALS, config)
        assert screening.passed
        assert screening.is_uncertain
        assert any("commission" in r for r in screening.job.uncertain_reasons)

    def test_uncertain_jobs_still_reach_the_alert_list(self, config):
        report = pipeline.screen_all([p.CONFLICTING_SIGNALS], config)
        assert len(report.passed) == 1

    def test_retail_is_filtered_at_the_title_step(self, config):
        screening = pipeline.screen_job(p.RETAIL_FLOOR, config)
        assert screening.rejected_by is not None
        assert screening.rejected_by.rule == "title"


class TestReport:
    def test_counts_split_correctly(self, config):
        jobs = [
            p.make_job(source_id="ok-1"),
            p.COMMISSION_ONLY,
            p.RETAIL_FLOOR,
            p.OTTAWA_JOB,
            p.STALE,
        ]
        report = pipeline.screen_all(jobs, config)

        assert len(report.screenings) == 5
        assert len(report.passed) == 1
        assert len(report.rejected) == 4

    def test_rejections_are_attributed_by_rule(self, config):
        report = pipeline.screen_all(
            [p.COMMISSION_ONLY, p.PRIMERICA, p.RETAIL_FLOOR, p.STALE], config
        )
        counts = report.rejection_counts()

        assert counts["commission"] == 2
        assert counts["title"] == 1
        assert counts["freshness"] == 1

    def test_empty_input(self, config):
        report = pipeline.screen_all([], config)
        assert report.passed == []
        assert report.rejected == []


class TestDryRunOutput:
    def test_shows_both_sides_with_reasons(self, config):
        report = pipeline.screen_all(
            [p.make_job(), p.COMMISSION_ONLY, p.CONFLICTING_SIGNALS], config
        )
        output = pipeline.format_dry_run(report)

        assert "DRY RUN" in output
        assert "nothing was sent" in output
        assert "WOULD ALERT" in output
        assert "WOULD FILTER OUT" in output
        # The rejection reason has to be visible, not just the verdict.
        assert "commission only" in output.lower()

    def test_marks_uncertain_jobs(self, config):
        report = pipeline.screen_all([p.CONFLICTING_SIGNALS], config)
        assert "[UNCERTAIN]" in pipeline.format_dry_run(report)

    def test_summary_counts_appear(self, config):
        report = pipeline.screen_all([p.make_job(), p.STALE], config)
        output = pipeline.format_dry_run(report)

        assert "screened : 2" in output
        assert "passed   : 1" in output
        assert "rejected : 1" in output


class TestIndeedJobsThroughTheFullPipeline:
    def test_the_fixture_email_filters_down_correctly(self, config, alert_html):
        """The saved alert has 4 cards: two good, one MLM, one retail."""
        from salesradar.providers.indeed_email import IndeedEmailProvider

        provider = IndeedEmailProvider(
            gmail_service=None,
            provider_config=config.provider_section("indeed_email"),
        )
        jobs = provider.parse_html(alert_html, received_at=p.hours_ago(1))
        report = pipeline.screen_all(jobs, config)

        passed_titles = [s.job.title for s in report.passed]
        assert "Account Executive - Mid Market" in passed_titles
        assert "Sales Development Representative" in passed_titles

        rejected_titles = [s.job.title for s in report.rejected]
        assert "Sales Representative - Entry Level" in rejected_titles
        assert "Retail Sales Associate" in rejected_titles
