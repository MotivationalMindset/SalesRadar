"""Wires the whole run together: fetch, dedupe, screen, draft, deliver.

Nothing here talks to a job board directly and nothing here submits anything.
The run surfaces postings and drafts material; a human decides what to do with
them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .drafting import Drafter
from .filters import pipeline
from .models import Job, ScreenedJob
from .providers.base import JobProvider, ProviderError
from .storage import Storage
from .telegram_out import TelegramNotifier, format_weekly_summary

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """What happened, for the log line at the end of the run."""

    fetched: int = 0
    after_dedupe: int = 0
    passed: int = 0
    uncertain: int = 0
    drafted: int = 0
    sent: int = 0
    decisions_recorded: int = 0
    provider_errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "after_dedupe": self.after_dedupe,
            "passed": self.passed,
            "uncertain": self.uncertain,
            "drafted": self.drafted,
            "sent": self.sent,
            "decisions_recorded": self.decisions_recorded,
            "provider_errors": self.provider_errors,
        }


def build_providers(config: Config, storage: Storage) -> list[JobProvider]:
    """Instantiate every enabled provider. A broken one is skipped, not fatal."""
    providers: list[JobProvider] = []

    if config.provider_enabled("adzuna"):
        from .providers.adzuna import AdzunaProvider

        try:
            providers.append(
                AdzunaProvider.from_env(config.search, config.provider_section("adzuna"))
            )
        except ProviderError as exc:
            log.error("adzuna provider unavailable", extra={"error": str(exc)})

    if config.provider_enabled("indeed_email"):
        from .providers.indeed_email import IndeedEmailProvider

        try:
            providers.append(
                IndeedEmailProvider.from_env(
                    config.provider_section("indeed_email"), storage
                )
            )
        except Exception as exc:
            log.error("indeed email provider unavailable", extra={"error": str(exc)})

    if config.provider_enabled("jsearch"):
        from .providers.jsearch import JSearchProvider

        try:
            providers.append(
                JSearchProvider.from_env(
                    config.search, config.provider_section("jsearch")
                )
            )
        except ProviderError as exc:
            log.error("jsearch provider unavailable", extra={"error": str(exc)})

    log.info("providers ready", extra={"providers": [p.name for p in providers]})
    return providers


def fetch_all(providers: list[JobProvider], summary: RunSummary) -> list[Job]:
    """Collect postings from every provider, surviving individual failures."""
    jobs: list[Job] = []
    for provider in providers:
        try:
            fetched = provider.fetch()
        except Exception as exc:
            message = f"{provider.name}: {exc}"
            summary.provider_errors.append(message)
            log.error(
                "provider fetch failed",
                extra={"provider": provider.name, "error": str(exc)},
            )
            continue
        log.info("provider fetched", extra={"provider": provider.name, "count": len(fetched)})
        jobs.extend(fetched)
    return jobs


async def run(
    config: Config,
    storage: Storage,
    dry_run: bool = False,
    weekly_summary: bool = False,
) -> RunSummary:
    """Execute one full cycle. Returns a summary of what happened."""
    summary = RunSummary()

    providers = build_providers(config, storage)
    if not providers:
        log.error("no providers are available — check the secrets in SETUP.md")
        return summary

    jobs = fetch_all(providers, summary)
    summary.fetched = len(jobs)

    # Dedupe across providers and against everything ever alerted. A job Adzuna
    # and Indeed both carry alerts once, and never twice.
    fresh = storage.filter_unseen(jobs)
    summary.after_dedupe = len(fresh)
    log.info(
        "deduplicated",
        extra={"fetched": len(jobs), "new": len(fresh), "already_seen": len(jobs) - len(fresh)},
    )

    report = pipeline.screen_all(fresh, config)
    summary.passed = len(report.passed)
    summary.uncertain = sum(1 for s in report.passed if s.is_uncertain)

    if dry_run:
        print(pipeline.format_dry_run(report))
        log.info("dry run complete — nothing sent, nothing recorded", extra=summary.as_dict())
        return summary

    screened = [
        ScreenedJob(job=s.job, uncertain=s.is_uncertain) for s in report.passed
    ]

    # Cap the send volume before drafting so a runaway provider doesn't also
    # run up an Anthropic bill.
    max_alerts = int(config.telegram.get("max_alerts_per_run", 15))
    if len(screened) > max_alerts:
        log.warning(
            "capping alerts for this run",
            extra={"passed": len(screened), "cap": max_alerts},
        )
        screened = screened[:max_alerts]

    if config.drafting.get("enabled", True) and screened:
        drafter = Drafter(config.drafting, config.resume_path, storage)
        drafts = drafter.draft_all([s.job for s in screened])
        for item in screened:
            item.draft = drafts.get(item.job.dedupe_hash)
        summary.drafted = sum(1 for s in screened if s.draft is not None)

    notifier = TelegramNotifier.from_env(config.telegram, storage)

    # Drain queued button presses first so the weekly summary counts them.
    summary.decisions_recorded = await notifier.drain_callbacks()

    for item in screened:
        delivered = await notifier.send_alert(item)
        if delivered:
            summary.sent += 1
        storage.record_seen(item.job, alerted=delivered)

    # Anything screened out is still recorded, so a rejected posting is never
    # re-screened on a later run. Jobs held back by the cap are deliberately
    # left unrecorded so they alert on the next run instead of vanishing.
    for screening in report.rejected:
        storage.record_seen(screening.job, alerted=False)

    if summary.provider_errors:
        await notifier.send_text(
            "⚠️ <b>SalesRadar</b>: some sources failed this run —\n"
            + "\n".join(f"• {e}" for e in summary.provider_errors[:5])
        )

    if weekly_summary:
        counts = storage.weekly_summary(days=7)
        await notifier.send_text(format_weekly_summary(counts))
        log.info("weekly summary sent", extra=counts)

    pruned = storage.prune_seen(older_than_days=120)
    if pruned:
        log.info("pruned old seen_jobs rows", extra={"rows": pruned})

    log.info("run complete", extra=summary.as_dict())
    return summary
