"""Core data types shared across providers, filters, drafting, and delivery."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# Corporate suffixes that vary between sources for the same employer.
_COMPANY_NOISE = re.compile(
    r"\b(inc|inc\.|llc|ltd|ltd\.|limited|corp|corporation|co|company|"
    r"canada|group|the)\b"
)
# Seniority and bracketed decoration that differ between sources.
_TITLE_NOISE = re.compile(
    r"\b(senior|sr|junior|jr|entry level|entry-level|i|ii|iii|"
    r"full time|full-time|permanent|hiring|urgent|urgently)\b"
)


def _slugify(value: str) -> str:
    return _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")


class Verdict(str, Enum):
    """Outcome of running a posting through one filter."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


@dataclass(frozen=True)
class FilterResult:
    """Why a filter reached its verdict. The reason is shown in --dry-run."""

    verdict: Verdict
    rule: str
    reason: str

    @property
    def rejected(self) -> bool:
        return self.verdict is Verdict.REJECT

    @property
    def uncertain(self) -> bool:
        return self.verdict is Verdict.UNCERTAIN


@dataclass
class Job:
    """A single posting, normalized across every provider."""

    source: str
    source_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_text: str | None = None
    posted_at: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    # Populated by the pipeline.
    uncertain_reasons: list[str] = field(default_factory=list)

    @property
    def dedupe_slug(self) -> str:
        """Normalized company+title+location, stable across providers.

        Adzuna and Indeed spell the same employer differently often enough that
        a raw string match misses duplicates, so both sides get their noise
        words stripped before hashing.
        """
        company = _COMPANY_NOISE.sub(" ", self.company.lower())
        title = _TITLE_NOISE.sub(" ", self.title.lower())
        # Only the first location segment: "Toronto, ON" and "Toronto" are one
        # place, and providers disagree about how much of the tail they include.
        location = self.location.split(",")[0]
        return "|".join(_slugify(p) for p in (company, title, location))

    @property
    def dedupe_hash(self) -> str:
        return hashlib.sha256(self.dedupe_slug.encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        """Hash of the fields a draft depends on, for the drafting cache."""
        payload = "|".join(
            [self.title, self.company, self.location, self.description[:4000]]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @property
    def age_hours(self) -> float | None:
        if self.posted_at is None:
            return None
        posted = self.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - posted
        return delta.total_seconds() / 3600.0

    @property
    def haystack(self) -> str:
        """Everything a text filter should search, lowercased."""
        parts = [self.title, self.company, self.description, self.salary_text or ""]
        return " ".join(parts).lower()

    @property
    def salary_display(self) -> str:
        if self.salary_min and self.salary_max:
            return f"${self.salary_min:,.0f}–${self.salary_max:,.0f}"
        if self.salary_min:
            return f"From ${self.salary_min:,.0f}"
        if self.salary_text:
            return self.salary_text
        return "Not listed"


@dataclass
class Draft:
    """Application material generated for one posting."""

    cover_letter_opener: str
    resume_bullets: list[str]
    interview_questions: list[str]

    def is_empty(self) -> bool:
        return not (
            self.cover_letter_opener or self.resume_bullets or self.interview_questions
        )


@dataclass
class ScreenedJob:
    """A job that survived the pipeline, with its draft if one was generated."""

    job: Job
    draft: Draft | None = None
    uncertain: bool = False
