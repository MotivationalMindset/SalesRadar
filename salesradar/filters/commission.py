"""Filter 2 — commission-only rejection. The highest-value rule in the pipeline.

Base proof is established first, because two kinds of red flag are graded
against it:

  BASE PROOF   salary_min at or above the configured floor, or a base-salary
               phrase in the description ("base + commission", "$65k base").

  HARD FLAGS   "commission only", "100% commission", 1099/contractor language,
               known MLM operators. These contradict a base rather than
               coexisting with it.
  SOFT FLAGS   "uncapped commission", "unlimited earning potential". The brief
               is precise that these only damn a posting when no base is
               mentioned — a real AE listing says "$70k base plus uncapped
               commission", and treating that as suspicious would reject the
               best jobs on the board. Soft flags are therefore ignored
               entirely once base proof exists.

  hard flags AND base proof  -> UNCERTAIN (genuinely contradictory; surfaced
                                with a warning rather than dropped)
  any flag, no base proof    -> REJECT
  base proof, no hard flags  -> ACCEPT
  nothing either way         -> ACCEPT (nothing incriminating found)

The UNCERTAIN case exists because a false reject is silent and permanent, while
a false accept costs ten seconds of reading. Indeed alert emails in particular
carry only a teaser, so ambiguity there is common and must not be fatal.
"""

from __future__ import annotations

import re
from typing import Any

from ..models import FilterResult, Job, Verdict

RULE = "commission"


def check(job: Job, config: dict[str, Any]) -> FilterResult:
    haystack = job.haystack

    base_proof = _find_base_proof(job, haystack, config)
    hard_flags = _find_hard_flags(job, haystack, config)
    soft_flags = _find_soft_flags(job, haystack, config) if not base_proof else []

    if hard_flags and base_proof:
        return FilterResult(
            Verdict.UNCERTAIN,
            RULE,
            f"conflicting signals — flags: {_join(hard_flags)}; "
            f"but base evidence: {_join(base_proof)}",
        )

    flags = hard_flags + soft_flags
    if flags:
        return FilterResult(
            Verdict.REJECT, RULE, f"commission-only indicators: {_join(flags)}"
        )

    if base_proof:
        return FilterResult(Verdict.ACCEPT, RULE, f"base pay evidence: {_join(base_proof)}")

    return FilterResult(Verdict.ACCEPT, RULE, "no commission-only indicators found")


# --- red flags --------------------------------------------------------------


def _find_hard_flags(job: Job, haystack: str, config: dict[str, Any]) -> list[str]:
    """Signals that contradict a base salary rather than sitting beside one."""
    flags: list[str] = []

    for phrase in config.get("commission_only_phrases", []):
        if phrase.lower() in haystack:
            flags.append(f'"{phrase}"')

    for phrase in config.get("contractor_phrases", []):
        if phrase.lower() in haystack:
            flags.append(f'"{phrase}"')

    for company in config.get("mlm_companies", []):
        if company.lower() in haystack:
            flags.append(f"known operator: {company}")

    for combo in config.get("mlm_phrase_combos", []):
        if combo and all(str(part).lower() in haystack for part in combo):
            flags.append("MLM pattern: " + " + ".join(f'"{p}"' for p in combo))

    return flags


def _find_soft_flags(job: Job, haystack: str, config: dict[str, Any]) -> list[str]:
    """Signals that only matter when nothing establishes a base.

    Only consulted when base proof is absent, so "uncapped commission" next to
    a $70k base never counts against the posting.
    """
    flags: list[str] = []

    for phrase in config.get("commission_phrases_needing_base", []):
        if phrase.lower() in haystack:
            flags.append(f'"{phrase}" with no base mentioned')

    # The brief is specific that hype language is judged against the API's
    # salary_min field, not against description phrasing.
    if job.salary_min is None:
        for phrase in config.get("hype_phrases_needing_salary", []):
            if phrase.lower() in haystack:
                flags.append(f'"{phrase}" with no salary_min')

    return flags


# --- base salary proof ------------------------------------------------------


def _find_base_proof(job: Job, haystack: str, config: dict[str, Any]) -> list[str]:
    proof: list[str] = []

    floor = float(config.get("min_base_salary_cad", 40000))
    if job.salary_min is not None and job.salary_min >= floor:
        proof.append(f"salary_min ${job.salary_min:,.0f} >= ${floor:,.0f}")

    for phrase in config.get("base_salary_phrases", []):
        if phrase.lower() in haystack:
            proof.append(f'"{phrase}"')

    for pattern in config.get("base_salary_regexes", []):
        try:
            match = re.search(pattern, haystack, re.IGNORECASE)
        except re.error:
            # A bad regex in config shouldn't take the run down; skip it.
            continue
        if match:
            proof.append(f'matched "{match.group(0).strip()}"')

    return proof


def _join(items: list[str], limit: int = 4) -> str:
    shown = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return ", ".join(shown) + suffix
