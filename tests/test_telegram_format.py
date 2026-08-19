"""Alert formatting — the shape the brief specified, and HTML safety."""

from __future__ import annotations

from salesradar.models import Draft, ScreenedJob
from salesradar.telegram_out import format_alert, format_weekly_summary

from .fixtures import postings as p


def screened(job=None, draft=None, uncertain=False) -> ScreenedJob:
    return ScreenedJob(job=job or p.make_job(), draft=draft, uncertain=uncertain)


class TestLayout:
    def test_header_line(self):
        text = format_alert(screened())
        assert "🎯" in text
        assert "Account Executive" in text
        assert "Northbound Software Inc." in text

    def test_location_and_salary_line(self):
        text = format_alert(screened())
        assert "📍" in text
        assert "Toronto, ON" in text
        assert "💰" in text
        assert "$70,000" in text

    def test_posted_line(self):
        text = format_alert(screened(p.make_job(posted_at=p.hours_ago(3))))
        assert "⏱️" in text
        assert "3 hours ago" in text

    def test_apply_link(self):
        text = format_alert(screened())
        assert 'href="https://example.com/jobs/1"' in text

    def test_missing_salary_reads_not_listed(self):
        text = format_alert(screened(p.make_job(salary_min=None, salary_max=None)))
        assert "Not listed" in text

    def test_no_date_falls_back_gracefully(self):
        text = format_alert(screened(p.NO_DATE))
        assert "Posted recently" in text

    def test_sub_hour_posting(self):
        text = format_alert(screened(p.make_job(posted_at=p.hours_ago(0.3))))
        assert "less than an hour" in text


class TestDraftSection:
    def test_all_three_parts_render(self):
        draft = Draft(
            "I noticed Northbound is expanding its mid-market team.",
            ["Closed $1.2M in new ARR", "Ran full-cycle deals", "Built outbound motion"],
            ["What does the ramp look like?", "How is the territory split?"],
        )
        text = format_alert(screened(draft=draft))

        assert "Cover letter opener" in text
        assert "Northbound is expanding" in text
        assert "Resume tweaks" in text
        assert "Closed $1.2M in new ARR" in text
        assert "Ask them" in text
        assert "What does the ramp look like?" in text

    def test_missing_draft_says_so_and_still_sends(self):
        text = format_alert(screened(draft=None))
        assert "No draft generated" in text
        assert "Account Executive" in text

    def test_bullets_are_rendered_as_a_list(self):
        draft = Draft("Opener.", ["one", "two"], [])
        assert "• one" in format_alert(screened(draft=draft))

    def test_questions_are_numbered(self):
        draft = Draft("Opener.", [], ["first?", "second?"])
        text = format_alert(screened(draft=draft))
        assert "1. first?" in text
        assert "2. second?" in text


class TestUncertain:
    def test_warning_emoji_is_shown(self):
        job = p.make_job()
        job.uncertain_reasons.append("commission: conflicting signals")
        assert "⚠️" in format_alert(screened(job=job, uncertain=True))

    def test_the_reason_is_shown(self):
        job = p.make_job()
        job.uncertain_reasons.append("commission: 1099 mentioned alongside a base")
        text = format_alert(screened(job=job, uncertain=True))
        assert "1099" in text

    def test_confident_jobs_get_no_warning(self):
        assert "⚠️" not in format_alert(screened())


class TestEscaping:
    def test_angle_brackets_in_a_title_are_escaped(self):
        job = p.make_job(title="Account Executive <urgent>")
        text = format_alert(screened(job=job))
        assert "&lt;urgent&gt;" in text

    def test_ampersand_in_a_company_name(self):
        job = p.make_job(company="Smith & Jones Ltd.")
        assert "Smith &amp; Jones" in format_alert(screened(job=job))

    def test_draft_content_is_escaped(self):
        draft = Draft("I saw your <b>posting</b>", [], [])
        text = format_alert(screened(draft=draft))
        assert "&lt;b&gt;posting&lt;/b&gt;" in text


class TestLength:
    def test_a_huge_draft_is_truncated_under_the_telegram_cap(self):
        draft = Draft("x" * 6000, ["y" * 2000], ["z" * 2000])
        text = format_alert(screened(draft=draft))
        assert len(text) <= 4096
        assert "truncated" in text


class TestWeeklySummary:
    def test_counts_render(self):
        text = format_weekly_summary(
            {"alerted": 20, "applied": 6, "skipped": 12, "no_response": 2}
        )
        assert "20" in text
        assert "Applied" in text
        assert "6" in text

    def test_rate_is_computed(self):
        text = format_weekly_summary(
            {"alerted": 10, "applied": 3, "skipped": 7, "no_response": 0}
        )
        assert "30%" in text

    def test_no_division_by_zero_on_a_quiet_week(self):
        text = format_weekly_summary(
            {"alerted": 0, "applied": 0, "skipped": 0, "no_response": 0}
        )
        assert "0%" in text
