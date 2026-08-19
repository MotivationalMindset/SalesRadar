"""Filter 4 — title relevance.

Reject list wins over accept list: "Retail Sales Associate" contains
"sales associate manager"-adjacent text and would otherwise sneak through, and
"Automotive Sales Representative" matches "sales representative" outright.
Checking rejects first is what keeps the floor-sales roles out.

Sales Engineer is the one conditional case: it's a real target role unless the
posting demands a P.Eng, so it's rejected only when the description says so.
"""

from __future__ import annotations

from typing import Any

from ..models import FilterResult, Job, Verdict

RULE = "title"


def check(job: Job, config: dict[str, Any]) -> FilterResult:
    title = job.title.lower()
    description = job.description.lower()

    for phrase in config.get("reject", []):
        if phrase.lower() in title:
            return FilterResult(
                Verdict.REJECT, RULE, f'title contains "{phrase}" (excluded role type)'
            )

    for rule in config.get("conditional_reject", []):
        trigger = str(rule.get("title_contains", "")).lower()
        if not trigger or trigger not in title:
            continue
        for marker in rule.get("description_contains", []):
            if str(marker).lower() in description:
                return FilterResult(
                    Verdict.REJECT,
                    RULE,
                    f'"{trigger}" role requiring "{marker}"',
                )

    for phrase in config.get("accept", []):
        if phrase.lower() in title:
            return FilterResult(Verdict.ACCEPT, RULE, f'title matched "{phrase}"')

    return FilterResult(
        Verdict.REJECT,
        RULE,
        f'"{job.title}" matched no accepted title pattern',
    )
