"""Filter 1 — freshness. Reject anything posted more than 24 hours ago.

Duplicate suppression is the seen-jobs table's job, not this filter's; this one
only cares about the clock.
"""

from __future__ import annotations

from typing import Any

from ..models import FilterResult, Job, Verdict

RULE = "freshness"


def check(job: Job, config: dict[str, Any]) -> FilterResult:
    max_age = float(config.get("max_age_hours", 24))
    keep_if_missing = bool(config.get("keep_if_date_missing", True))

    age = job.age_hours

    if age is None:
        if keep_if_missing:
            return FilterResult(
                Verdict.ACCEPT,
                RULE,
                "no posting date available; kept (seen-jobs table prevents repeats)",
            )
        return FilterResult(Verdict.REJECT, RULE, "no posting date available")

    if age < 0:
        # A future timestamp is a provider clock skew, not a real posting date.
        return FilterResult(
            Verdict.ACCEPT, RULE, f"posting date is {abs(age):.1f}h in the future; kept"
        )

    if age > max_age:
        return FilterResult(
            Verdict.REJECT, RULE, f"posted {age:.1f}h ago, older than {max_age:.0f}h"
        )

    return FilterResult(Verdict.ACCEPT, RULE, f"posted {age:.1f}h ago")
