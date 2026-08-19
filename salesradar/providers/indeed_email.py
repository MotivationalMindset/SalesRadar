"""Indeed provider — parses Indeed's job-alert emails via the Gmail API.

This is where Indeed coverage comes from. Adzuna does not carry Indeed
listings, so the two providers are complementary rather than redundant, and the
pipeline merges and dedupes their output.

A note on scopes. The brief asked for `gmail.readonly` *and* for messages to be
marked read after parsing. Those are mutually exclusive: marking a message read
mutates a label, which `gmail.readonly` forbids. The resolution is a config
switch — with `mark_read_after_parse: true` the provider requests
`gmail.modify` (the narrowest scope that permits a label change); set it to
false and the provider stays strictly read-only and instead remembers the
last-seen message id in SQLite. Read-only is the safer default if you would
rather the bot never touch the mailbox; the trade is that a message it already
parsed can be re-read after a state reset, which the seen-jobs table absorbs.

Indeed rewrites this HTML periodically. Every selector lives in config.yaml,
the parser is written against tests/fixtures/indeed_alert.html, and a non-empty
email that yields zero jobs raises loudly with the raw HTML logged — a silent
zero would look exactly like a quiet job market.
"""

from __future__ import annotations

import base64
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup, Tag

from ..models import Job
from .base import ProviderError

log = logging.getLogger(__name__)

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"

# Indeed apply links carry the job key in one of these query params.
_JK_PARAMS = ("jk", "vjk", "jobkey")
_WS = re.compile(r"\s+")


class IndeedEmailParseError(ProviderError):
    """A non-empty alert email produced no jobs — the selectors have drifted."""


def required_scopes(mark_read: bool) -> list[str]:
    """The Gmail scope set this provider needs given the mark-read setting."""
    return [MODIFY_SCOPE if mark_read else READONLY_SCOPE]


class IndeedEmailProvider:
    """Reads unread Indeed alert mail and extracts one Job per posting card."""

    name = "indeed_email"

    def __init__(
        self,
        gmail_service: Any,
        provider_config: dict[str, Any],
        storage: Any | None = None,
    ) -> None:
        self.service = gmail_service
        self.config = provider_config
        self.storage = storage
        self.selectors: dict[str, list[str]] = provider_config.get("selectors", {})

    @classmethod
    def from_env(
        cls, provider_config: dict[str, Any], storage: Any | None = None
    ) -> IndeedEmailProvider:
        """Build a Gmail client from the refresh token in the environment."""
        from ..gmail_auth import build_gmail_service

        mark_read = bool(provider_config.get("mark_read_after_parse", True))
        service = build_gmail_service(scopes=required_scopes(mark_read))
        return cls(service, provider_config, storage)

    # --- fetching -----------------------------------------------------------

    def fetch(self) -> list[Job]:
        query = self._build_query()
        max_messages = int(self.config.get("max_messages", 25))

        try:
            listing = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_messages)
                .execute()
            )
        except Exception as exc:  # googleapiclient raises a wide range here
            raise ProviderError(f"Gmail list failed: {exc}") from exc

        message_ids = [m["id"] for m in listing.get("messages", [])]
        log.info(
            "indeed alert messages found",
            extra={"count": len(message_ids), "query": query},
        )
        if not message_ids:
            return []

        jobs: list[Job] = []
        for message_id in message_ids:
            try:
                jobs.extend(self._process_message(message_id))
            except IndeedEmailParseError:
                # Already logged with the raw HTML. Keep going so one drifted
                # template doesn't cost us every other alert in the mailbox.
                continue
            except Exception as exc:
                log.error(
                    "failed to process indeed message",
                    extra={"message_id": message_id, "error": str(exc)},
                )
        return jobs

    def _build_query(self) -> str:
        senders = self.config.get("senders", [])
        template = self.config.get("query", "is:unread from:({senders})")
        return template.format(senders=" OR ".join(senders))

    def _process_message(self, message_id: str) -> list[Job]:
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        html = _extract_html(message.get("payload", {}))
        received = _received_at(message)

        if not html or not html.strip():
            log.warning("indeed message had no HTML body", extra={"message_id": message_id})
            return []

        jobs = self.parse_html(html, received_at=received, message_id=message_id)

        if jobs and self.config.get("mark_read_after_parse", True):
            self._mark_read(message_id)
        return jobs

    def _mark_read(self, message_id: str) -> None:
        try:
            self.service.users().messages().modify(
                userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]}
            ).execute()
        except Exception as exc:
            # Almost always a scope problem — worth naming explicitly, since the
            # symptom is the same messages being re-parsed every run.
            log.warning(
                "could not mark message read (is the token scoped gmail.modify?)",
                extra={"message_id": message_id, "error": str(exc)},
            )

    # --- parsing ------------------------------------------------------------

    def parse_html(
        self,
        html: str,
        received_at: datetime | None = None,
        message_id: str = "",
    ) -> list[Job]:
        """Extract jobs from one alert email's HTML body.

        Raises IndeedEmailParseError when a non-trivial email yields nothing,
        logging the raw HTML so the selectors can be repaired from the failure.
        """
        soup = BeautifulSoup(html, "html.parser")
        cards = self._select_all(soup, "job_card")

        jobs: list[Job] = []
        for card in cards:
            job = self._card_to_job(card, received_at)
            if job is not None:
                jobs.append(job)

        if not jobs and _looks_like_a_real_alert(html):
            log.error(
                "indeed alert parsed to zero jobs — selectors have probably "
                "drifted; update providers.indeed_email.selectors in config.yaml",
                extra={
                    "message_id": message_id,
                    "html_length": len(html),
                    "cards_matched": len(cards),
                    "raw_html": html[:20000],
                },
            )
            raise IndeedEmailParseError(
                f"Indeed alert {message_id or '(unknown)'} produced no jobs from "
                f"{len(html)} characters of HTML."
            )

        return jobs

    def _card_to_job(self, card: Tag, received_at: datetime | None) -> Job | None:
        title = self._select_text(card, "title")
        if not title:
            return None

        url = self._select_url(card)
        company = self._select_text(card, "company") or "Unknown"
        location = self._select_text(card, "location") or ""
        salary_text = self._select_text(card, "salary") or None

        return Job(
            source=self.name,
            source_id=_job_key(url) or _WS.sub("-", title.lower())[:64],
            title=title,
            company=company,
            location=location,
            url=url,
            # Alert emails carry only a teaser, so the commission filter has
            # much less to work with here than on an Adzuna posting. That is
            # exactly why ambiguity is flagged UNCERTAIN rather than dropped.
            description=self._card_text(card),
            salary_text=salary_text,
            salary_min=_parse_salary_min(salary_text),
            # The email's arrival time is the best posting-time proxy available;
            # these alerts are configured for "last 24 hours" at the Indeed end.
            posted_at=received_at,
            raw={"html": str(card)},
        )

    # --- selector helpers ---------------------------------------------------

    def _select_all(self, soup: BeautifulSoup, key: str) -> list[Tag]:
        """Try each configured selector in order; first one that matches wins."""
        for selector in self.selectors.get(key, []):
            found = soup.select(selector)
            if found:
                log.debug(
                    "selector matched", extra={"key": key, "selector": selector,
                                               "count": len(found)}
                )
                return found
        return []

    def _select_text(self, card: Tag, key: str) -> str:
        for selector in self.selectors.get(key, []):
            element = card.select_one(selector)
            if element is not None:
                text = _clean(element.get_text(" ", strip=True))
                if text:
                    return text
        return ""

    def _select_url(self, card: Tag) -> str:
        for selector in self.selectors.get("url", ["a[href]"]):
            element = card.select_one(selector)
            if element is not None:
                href = element.get("href")
                if href:
                    return str(href)
        # The card itself may be the anchor.
        if card.name == "a" and card.get("href"):
            return str(card.get("href"))
        return ""

    @staticmethod
    def _card_text(card: Tag) -> str:
        return _clean(card.get_text(" ", strip=True))


# --- module-level helpers ---------------------------------------------------


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace("\xa0", " ")).strip()


def _looks_like_a_real_alert(html: str) -> bool:
    """Distinguish a drifted template from a genuinely empty alert.

    Indeed does send "no new jobs" emails. Those are short and say so; failing
    loudly on one of those would cry wolf every quiet morning.
    """
    if len(html) < 2000:
        return False
    lowered = html.lower()
    empty_markers = (
        "no new jobs",
        "there are no new",
        "we didn't find any new",
        "we did not find any new",
    )
    return not any(marker in lowered for marker in empty_markers)


def _extract_html(payload: dict[str, Any]) -> str:
    """Walk the MIME tree and return the first text/html part found."""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime_type == "text/html" and body.get("data"):
        return _b64(body["data"])

    for part in payload.get("parts", []) or []:
        found = _extract_html(part)
        if found:
            return found

    # Some alerts arrive as a single text/plain part; better than nothing.
    if mime_type == "text/plain" and body.get("data"):
        return _b64(body["data"])
    return ""


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", "replace")


def _received_at(message: dict[str, Any]) -> datetime | None:
    internal = message.get("internalDate")
    if not internal:
        return None
    try:
        return datetime.fromtimestamp(int(internal) / 1000, tz=timezone.utc)
    except (TypeError, ValueError):
        return None


def _job_key(url: str) -> str:
    """Pull Indeed's stable job key out of the apply URL, if it's there."""
    if not url:
        return ""
    query = parse_qs(urlparse(url).query)
    for param in _JK_PARAMS:
        values = query.get(param)
        if values:
            return values[0]
    return ""


def _parse_salary_min(text: str | None) -> float | None:
    """Best-effort annual floor from a snippet like '$55,000 - $70,000 a year'.

    Hourly and monthly figures are annualized so the commission filter's
    salary threshold compares like with like.
    """
    if not text:
        return None
    numbers = re.findall(r"\$\s?([\d,]+(?:\.\d+)?)", text)
    if not numbers:
        return None
    try:
        value = float(numbers[0].replace(",", ""))
    except ValueError:
        return None

    lowered = text.lower()
    if "hour" in lowered:
        return value * 2080  # 40h/week, 52 weeks
    if "month" in lowered:
        return value * 12
    if "week" in lowered:
        return value * 52
    return value


def iter_cards(soup: BeautifulSoup, selectors: Iterable[str]) -> list[Tag]:
    """Exposed for tests: first matching selector wins."""
    for selector in selectors:
        found = soup.select(selector)
        if found:
            return found
    return []


def gmail_env_present() -> bool:
    """True when the Gmail refresh-token secrets are configured."""
    return all(
        os.environ.get(key)
        for key in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")
    )
