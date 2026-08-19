"""Runs every filter in order and records why each posting lived or died.

Order matters and is fixed: freshness, commission, geo, title. The cheapest and
most decisive checks run first, and --dry-run prints the first rule that
rejected a job rather than every rule it would have failed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from ..config import Config
from ..models import FilterResult, Job, Verdict
from . import commission, freshness, geo, title

log = logging.getLogger(__name__)

FilterFn = Callable[[Job, dict[str, Any]], FilterResult]

# (config key, callable). The order is the pipeline order.
FILTERS: list[tuple[str, FilterFn]] = [
    ("freshness", freshness.check),
    ("commission", commission.check),
    ("geo", geo.check),
    ("title", title.check),
]


@dataclass
class Screening:
    """Every verdict a single job collected on its way through."""

    job: Job
    results: list[FilterResult] = field(default_factory=list)

    @property
    def rejected_by(self) -> FilterResult | None:
        return next((r for r in self.results if r.rejected), None)

    @property
    def passed(self) -> bool:
        return self.rejected_by is None

    @property
    def uncertain_results(self) -> list[FilterResult]:
        return [r for r in self.results if r.uncertain]

    @property
    def is_uncertain(self) -> bool:
        return bool(self.uncertain_results)


@dataclass
class PipelineReport:
    """Everything a run screened, for --dry-run and for the run summary."""

    screenings: list[Screening] = field(default_factory=list)

    @property
    def passed(self) -> list[Screening]:
        return [s for s in self.screenings if s.passed]

    @property
    def rejected(self) -> list[Screening]:
        return [s for s in self.screenings if not s.passed]

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for screening in self.rejected:
            rejected_by = screening.rejected_by
            if rejected_by is not None:
                counts[rejected_by.rule] = counts.get(rejected_by.rule, 0) + 1
        return counts


def screen_job(job: Job, config: Config) -> Screening:
    """Run one job through every filter, stopping at the first rejection."""
    screening = Screening(job=job)

    for name, check in FILTERS:
        result = check(job, config.filter_section(name))
        screening.results.append(result)
        if result.rejected:
            break
        if result.uncertain:
            job.uncertain_reasons.append(f"{result.rule}: {result.reason}")

    return screening


def screen_all(jobs: list[Job], config: Config) -> PipelineReport:
    """Screen every job and log a one-line summary of the outcome."""
    report = PipelineReport(screenings=[screen_job(job, config) for job in jobs])

    log.info(
        "screening complete",
        extra={
            "screened": len(report.screenings),
            "passed": len(report.passed),
            "rejected": len(report.rejected),
            "uncertain": sum(1 for s in report.passed if s.is_uncertain),
            "rejections_by_rule": report.rejection_counts(),
        },
    )
    return report


def format_dry_run(report: PipelineReport) -> str:
    """Human-readable rundown of what would have happened, and why."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("DRY RUN — nothing was sent to Telegram and nothing was recorded")
    lines.append("=" * 72)
    lines.append("")

    passed = report.passed
    rejected = report.rejected

    lines.append(f"WOULD ALERT ({len(passed)})")
    lines.append("-" * 72)
    if not passed:
        lines.append("  (nothing)")
    for screening in passed:
        job = screening.job
        marker = "  [UNCERTAIN] " if screening.is_uncertain else "  [PASS]      "
        lines.append(f"{marker}{job.title} @ {job.company}")
        lines.append(f"               {job.location} · {job.salary_display} · {job.source}")
        for result in screening.results:
            symbol = "?" if result.uncertain else "+"
            lines.append(f"               {symbol} {result.rule}: {result.reason}")
        lines.append("")

    lines.append(f"WOULD FILTER OUT ({len(rejected)})")
    lines.append("-" * 72)
    if not rejected:
        lines.append("  (nothing)")
    for screening in rejected:
        job = screening.job
        rejected_by = screening.rejected_by
        assert rejected_by is not None
        lines.append(f"  [REJECT]    {job.title} @ {job.company}")
        lines.append(f"               {job.location} · {job.source}")
        lines.append(f"               - {rejected_by.rule}: {rejected_by.reason}")
        lines.append("")

    counts = report.rejection_counts()
    lines.append("SUMMARY")
    lines.append("-" * 72)
    lines.append(f"  screened : {len(report.screenings)}")
    lines.append(f"  passed   : {len(passed)}")
    lines.append(f"  uncertain: {sum(1 for s in passed if s.is_uncertain)}")
    lines.append(f"  rejected : {len(rejected)}")
    for rule, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"      by {rule}: {count}")
    lines.append("")

    return "\n".join(lines)
