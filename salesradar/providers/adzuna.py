"""Adzuna provider — employer sites and ATS postings across Canada.

Adzuna does NOT aggregate Indeed. Indeed coverage comes from the email-alert
provider in indeed_email.py; the two are merged and deduped by the pipeline.

Docs: https://developer.adzuna.com/
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


class AdzunaProvider:
    """Queries /v1/api/jobs/{country}/search/1 once per configured location."""

    name = "adzuna"

    def __init__(
        self,
        app_id: str,
        app_key: str,
        search: dict[str, Any],
        provider_config: dict[str, Any],
        session: requests.Session | None = None,
    ) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.search = search
        self.config = provider_config
        self.session = session or requests.Session()

    @classmethod
    def from_env(
        cls, search: dict[str, Any], provider_config: dict[str, Any]
    ) -> AdzunaProvider:
        app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
        app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
        if not app_id or not app_key:
            raise ProviderError(
                "ADZUNA_APP_ID and ADZUNA_APP_KEY must be set. "
                "See SETUP.md step 2."
            )
        return cls(app_id, app_key, search, provider_config)

    # --- fetching -----------------------------------------------------------

    def fetch(self) -> list[Job]:
        jobs: list[Job] = []
        for location in self.search.get("locations", []):
            try:
                results = self._search_location(location)
            except requests.RequestException as exc:
                # One bad location shouldn't cost us the other. Log and move on.
                log.error(
                    "adzuna request failed",
                    extra={"location": location, "error": str(exc)},
                )
                continue
            log.info(
                "adzuna results", extra={"location": location, "count": len(results)}
            )
            jobs.extend(results)
        return jobs

    def _search_location(self, location: str) -> list[Job]:
        country = self.search.get("country", "ca")
        base = self.config.get("base_url", "https://api.adzuna.com/v1/api/jobs")
        url = f"{base}/{country}/search/1"

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": self.search.get("what", "sales"),
            "where": location,
            "distance": self.search.get("distance_km", 25),
            "max_days_old": self.search.get("max_days_old", 1),
            "sort_by": self.search.get("sort_by", "date"),
            "results_per_page": self.search.get("results_per_page", 50),
            "content-type": "application/json",
        }

        response = self.session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        if response.status_code == 401:
            raise ProviderError(
                "Adzuna rejected the credentials (401). Check ADZUNA_APP_ID "
                "and ADZUNA_APP_KEY."
            )
        response.raise_for_status()

        payload = response.json()
        return [
            job
            for job in (self._to_job(item) for item in payload.get("results", []))
            if job is not None
        ]

    # --- normalization ------------------------------------------------------

    def _to_job(self, item: dict[str, Any]) -> Job | None:
        title = (item.get("title") or "").strip()
        if not title:
            return None

        company = (item.get("company") or {}).get("display_name", "") or "Unknown"
        location = (item.get("location") or {}).get("display_name", "") or ""

        return Job(
            source=self.name,
            source_id=str(item.get("id", "")),
            # Adzuna wraps matched terms in <strong>; strip them so filters and
            # the Telegram message see plain text.
            title=_strip_markup(title),
            company=_strip_markup(company),
            location=location,
            url=item.get("redirect_url", ""),
            description=_strip_markup(item.get("description", "") or ""),
            salary_min=_as_float(item.get("salary_min")),
            salary_max=_as_float(item.get("salary_max")),
            posted_at=_parse_created(item.get("created")),
            latitude=_as_float(item.get("latitude")),
            longitude=_as_float(item.get("longitude")),
            raw=item,
        )


def _strip_markup(value: str) -> str:
    return value.replace("<strong>", "").replace("</strong>", "").strip()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_created(value: Any) -> datetime | None:
    """Adzuna returns ISO 8601, usually with a trailing Z."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        log.debug("unparseable adzuna created date", extra={"value": value})
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
