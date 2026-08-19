"""JSearch (RapidAPI) provider — optional second API source.

Off by default. Adzuna plus the Indeed email parser already covers the ground;
this exists so the API source is genuinely swappable rather than hardcoded.
Turn it on in config.yaml and set JSEARCH_API_KEY to use it.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import requests

from ..models import Job
from .base import ProviderError

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class JSearchProvider:
    """Queries JSearch's /search endpoint once per configured location."""

    name = "jsearch"

    def __init__(
        self,
        api_key: str,
        search: dict[str, Any],
        provider_config: dict[str, Any],
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.search = search
        self.config = provider_config
        self.session = session or requests.Session()

    @classmethod
    def from_env(
        cls, search: dict[str, Any], provider_config: dict[str, Any]
    ) -> JSearchProvider:
        api_key = os.environ.get("JSEARCH_API_KEY", "").strip()
        if not api_key:
            raise ProviderError(
                "JSEARCH_API_KEY is not set but providers.jsearch.enabled is true. "
                "Either add the secret or set enabled: false in config.yaml."
            )
        return cls(api_key, search, provider_config)

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for location in self.search.get("locations", []):
            try:
                jobs.extend(self._search_location(location))
            except requests.RequestException as exc:
                log.error(
                    "jsearch request failed",
                    extra={"location": location, "error": str(exc)},
                )
        return jobs

    def _search_location(self, location: str) -> list[Job]:
        host = self.config.get("host", "jsearch.p.rapidapi.com")
        params = {
            "query": f"{self.search.get('what', 'sales')} in {location}, Ontario",
            "page": "1",
            "num_pages": str(self.config.get("num_pages", 1)),
            "date_posted": self.config.get("date_posted", "today"),
            "country": self.config.get("country", "ca"),
        }
        headers = {"X-RapidAPI-Key": self.api_key, "X-RapidAPI-Host": host}

        response = self.session.get(
            f"https://{host}/search",
            params=params,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        payload = response.json()
        return [
            job
            for job in (self._to_job(item) for item in payload.get("data", []))
            if job is not None
        ]

    def _to_job(self, item: dict[str, Any]) -> Job | None:
        title = (item.get("job_title") or "").strip()
        if not title:
            return None

        city = item.get("job_city") or ""
        state = item.get("job_state") or ""
        location = ", ".join(p for p in (city, state) if p)

        return Job(
            source=self.name,
            source_id=str(item.get("job_id", "")),
            title=title,
            company=(item.get("employer_name") or "Unknown").strip(),
            location=location,
            url=item.get("job_apply_link") or item.get("job_google_link") or "",
            description=(item.get("job_description") or "").strip(),
            salary_min=_annualize(
                item.get("job_min_salary"), item.get("job_salary_period")
            ),
            salary_max=_annualize(
                item.get("job_max_salary"), item.get("job_salary_period")
            ),
            posted_at=_parse_posted(item.get("job_posted_at_datetime_utc")),
            latitude=_as_float(item.get("job_latitude")),
            longitude=_as_float(item.get("job_longitude")),
            raw=item,
        )


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _annualize(value: Any, period: Any) -> float | None:
    """JSearch reports salary with a period; normalize everything to yearly."""
    amount = _as_float(value)
    if amount is None:
        return None
    multipliers = {"HOUR": 2080.0, "WEEK": 52.0, "MONTH": 12.0, "YEAR": 1.0}
    return amount * multipliers.get(str(period or "YEAR").upper(), 1.0)


def _parse_posted(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
