"""The commission filter — the highest-value rule, so the densest tests."""

from __future__ import annotations

import pytest

from salesradar.filters import commission
from salesradar.models import Verdict

from .fixtures import postings as p


class TestRejects:
    def test_explicit_commission_only(self, commission_rules):
        result = commission.check(p.COMMISSION_ONLY, commission_rules)
        assert result.verdict is Verdict.REJECT
        assert "commission only" in result.reason.lower()

    def test_1099_contractor_language(self, commission_rules):
        job = p.make_job(
            description="Independent contractor role, 1099. Sell our product.",
            salary_min=None,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT

    def test_own_your_own_business(self, commission_rules):
        job = p.make_job(
            description="Own your own business and set your own hours.",
            salary_min=None,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT

    def test_named_mlm_primerica(self, commission_rules):
        result = commission.check(p.PRIMERICA, commission_rules)
        assert result.verdict is Verdict.REJECT
        assert "primerica" in result.reason.lower()

    def test_named_mlm_in_company_field_only(self, commission_rules):
        job = p.make_job(
            company="World Financial Group",
            description="Financial services sales role in Toronto.",
            salary_min=None,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT

    def test_vector_marketing(self, commission_rules):
        job = p.make_job(
            company="Vector Marketing",
            description="Student summer work, flexible schedule.",
            salary_min=None,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT

    def test_mlm_phrase_combination(self, commission_rules):
        result = commission.check(p.CYDCOR_STYLE, commission_rules)
        assert result.verdict is Verdict.REJECT

    def test_hype_without_salary_min(self, commission_rules):
        result = commission.check(p.HYPE_NO_SALARY, commission_rules)
        assert result.verdict is Verdict.REJECT
        assert "unlimited earning potential" in result.reason.lower()

    def test_matching_is_case_insensitive(self, commission_rules):
        job = p.make_job(
            description="COMMISSION ONLY position. INDEPENDENT CONTRACTOR.",
            salary_min=None,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT


class TestAccepts:
    def test_base_plus_commission_phrase(self, commission_rules):
        result = commission.check(p.BASE_PLUS_COMMISSION, commission_rules)
        assert result.verdict is Verdict.ACCEPT

    def test_salary_min_above_floor_with_no_phrase(self, commission_rules):
        result = commission.check(p.SALARY_ONLY_NO_PHRASE, commission_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "58,000" in result.reason

    def test_nothing_incriminating_found(self, commission_rules):
        job = p.make_job(
            description="Sell our product to Ontario businesses. Great team.",
            salary_min=None,
        )
        result = commission.check(job, commission_rules)
        assert result.verdict is Verdict.ACCEPT

    def test_dollar_base_regex(self, commission_rules):
        job = p.make_job(
            description="Compensation is $65,000 base with commission on top.",
            salary_min=None,
        )
        result = commission.check(job, commission_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "base" in result.reason.lower()

    def test_uncapped_commission_alone_is_not_a_reject_when_base_exists(
        self, commission_rules
    ):
        """The brief is explicit: 'uncapped commission' only damns a posting
        when no base is mentioned. A real AE job says both."""
        job = p.make_job(
            description="Base salary $75,000 with uncapped commission.",
            salary_min=75000.0,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.ACCEPT

    def test_hype_with_salary_min_is_fine(self, commission_rules):
        job = p.make_job(
            description="Unlimited earning potential on top of your base.",
            salary_min=68000.0,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.ACCEPT


class TestUncertain:
    def test_conflicting_signals_are_flagged_not_dropped(self, commission_rules):
        result = commission.check(p.CONFLICTING_SIGNALS, commission_rules)
        assert result.verdict is Verdict.UNCERTAIN
        assert not result.rejected
        assert "1099" in result.reason

    def test_uncertain_reason_names_both_sides(self, commission_rules):
        result = commission.check(p.CONFLICTING_SIGNALS, commission_rules)
        assert "flags" in result.reason.lower()
        assert "base" in result.reason.lower()


class TestSalaryFloor:
    def test_below_floor_is_not_treated_as_base_proof(self, commission_rules):
        """$32k is below the $40k floor, so it isn't evidence of a real base —
        but with no red flags either, the posting still survives."""
        result = commission.check(p.LOW_SALARY_NO_FLAGS, commission_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "salary_min" not in result.reason

    def test_below_floor_plus_red_flag_rejects(self, commission_rules):
        job = p.make_job(
            description="Commission only role. Draw against commission available.",
            salary_min=20000.0,
        )
        assert commission.check(job, commission_rules).verdict is Verdict.REJECT

    @pytest.mark.parametrize("salary", [40000.0, 40001.0, 95000.0])
    def test_at_or_above_floor_counts(self, commission_rules, salary):
        job = p.make_job(description="Sales role.", salary_min=salary)
        result = commission.check(job, commission_rules)
        assert result.verdict is Verdict.ACCEPT
        assert "salary_min" in result.reason

    def test_just_below_floor_does_not_count(self, commission_rules):
        job = p.make_job(description="Sales role.", salary_min=39999.0)
        result = commission.check(job, commission_rules)
        assert "salary_min" not in result.reason


class TestConfigDriven:
    def test_adding_a_company_to_config_changes_behaviour(self):
        """Every rule is data. A new MLM only needs a config edit."""
        rules = {
            "min_base_salary_cad": 40000,
            "mlm_companies": ["fictional pyramid co"],
        }
        job = p.make_job(company="Fictional Pyramid Co", salary_min=None)
        assert commission.check(job, rules).verdict is Verdict.REJECT

    def test_empty_config_accepts_everything(self):
        assert commission.check(p.COMMISSION_ONLY, {}).verdict is Verdict.ACCEPT

    def test_a_broken_regex_in_config_does_not_crash_the_run(self):
        rules = {"min_base_salary_cad": 40000, "base_salary_regexes": ["([unclosed"]}
        result = commission.check(p.make_job(salary_min=None), rules)
        assert result.verdict is Verdict.ACCEPT
