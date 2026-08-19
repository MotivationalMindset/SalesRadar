"""Title relevance, including the conditional Sales Engineer rule."""

from __future__ import annotations

import pytest

from salesradar.filters import title
from salesradar.models import Verdict

from .fixtures import postings as p


class TestAccepts:
    @pytest.mark.parametrize(
        "job_title",
        [
            "SDR - Outbound",
            "BDR, Enterprise",
            "Account Executive",
            "Senior Account Executive",
            "Inside Sales Representative",
            "Sales Development Representative",
            "Business Development Manager",
            "Account Manager",
            "Sales Representative",
            "Enterprise Sales Executive",
            "Territory Manager",
        ],
    )
    def test_target_titles(self, title_rules, job_title):
        job = p.make_job(title=job_title)
        assert title.check(job, title_rules).verdict is Verdict.ACCEPT

    def test_matching_is_case_insensitive(self, title_rules):
        job = p.make_job(title="ACCOUNT EXECUTIVE")
        assert title.check(job, title_rules).verdict is Verdict.ACCEPT


class TestRejects:
    def test_retail_floor_associate(self, title_rules):
        result = title.check(p.RETAIL_FLOOR, title_rules)
        assert result.verdict is Verdict.REJECT
        assert "retail sales associate" in result.reason.lower()

    def test_automotive_commission_floor(self, title_rules):
        assert title.check(p.AUTOMOTIVE, title_rules).verdict is Verdict.REJECT

    def test_unrelated_role(self, title_rules):
        result = title.check(p.IRRELEVANT, title_rules)
        assert result.verdict is Verdict.REJECT
        assert "matched no accepted" in result.reason

    def test_door_to_door(self, title_rules):
        job = p.make_job(title="Door to Door Sales Representative")
        assert title.check(job, title_rules).verdict is Verdict.REJECT

    def test_reject_list_beats_accept_list(self, title_rules):
        """'Automotive Sales Representative' matches the accepted 'sales
        representative'. Rejects run first, which is what keeps it out."""
        job = p.make_job(title="Automotive Sales Representative")
        assert title.check(job, title_rules).verdict is Verdict.REJECT


class TestSalesEngineerConditional:
    def test_rejected_when_p_eng_required(self, title_rules):
        result = title.check(p.SALES_ENGINEER_PENG, title_rules)
        assert result.verdict is Verdict.REJECT
        assert "p.eng" in result.reason.lower()

    def test_kept_when_no_engineering_licence_demanded(self, title_rules):
        """A SaaS sales engineer role is a legitimate target."""
        result = title.check(p.SALES_ENGINEER_NO_PENG, title_rules)
        assert result.verdict is not Verdict.REJECT

    def test_professional_engineer_wording_also_triggers(self, title_rules):
        job = p.make_job(
            title="Sales Engineer",
            description="Must be a licensed Professional Engineer in Ontario.",
        )
        assert title.check(job, title_rules).verdict is Verdict.REJECT


class TestConfigDriven:
    def test_new_reject_phrase_takes_effect_from_config_alone(self):
        rules = {"accept": ["account executive"], "reject": ["intern"]}
        job = p.make_job(title="Account Executive Intern")
        assert title.check(job, rules).verdict is Verdict.REJECT

    def test_empty_accept_list_rejects_everything(self):
        assert title.check(p.make_job(), {}).verdict is Verdict.REJECT
