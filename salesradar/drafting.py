"""Generates application material with the Anthropic API.

Three cost controls, in order of how much they save:

1. **Cache.** Every draft is stored in SQLite keyed by a hash of the posting's
   text. A posting that reappears never costs a second call.
2. **Batch.** Uncached jobs go up several at a time in one request, so the
   resume and instructions are sent once per batch rather than once per job.
3. **Prompt caching.** The resume and system instructions sit in a cached
   system block, so repeat calls within the cache window read them at a tenth
   of the input price.

Graceful degradation is the rule: if anything here fails, the caller gets
`None` and the alert goes out without a draft. A missing cover letter is an
inconvenience; a missed job posting is the actual failure.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .models import Draft, Job
from .storage import Storage

log = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = """\
You help a sales professional in the Greater Toronto Area apply to jobs. For \
each posting you are given, produce application material grounded in the \
candidate's actual resume, which follows.

Rules:
- Reference the specific company and role. Generic material is worthless here.
- Draw the resume bullets from real experience in the resume below, rephrased \
to mirror the language of the posting. Never invent an employer, a metric, or \
a credential the resume does not contain.
- The interview questions should be ones a serious candidate would ask: about \
the territory, the quota, the ramp, the team, the product. Not questions whose \
answers are already in the posting.
- Write plainly. No filler openers, no "I am writing to express my interest".

CANDIDATE RESUME
================
{resume}
"""

USER_TEMPLATE = """\
Write application material for each of the {count} job posting(s) below.

For each posting produce:
- cover_letter_opener: about {words} words, naming the company and role
- resume_bullets: exactly {bullets} rewritten resume bullets tuned to the \
keywords in this posting
- interview_questions: exactly {questions} questions to ask the interviewer

Return ONLY a JSON array with one object per posting, in the same order as the \
postings, each with the keys: id, cover_letter_opener, resume_bullets, \
interview_questions. No prose before or after the JSON.

POSTINGS
========
{postings}
"""


class DraftingUnavailable(RuntimeError):
    """Drafting can't run. The caller sends alerts without drafts."""


class Drafter:
    """Turns postings into cover-letter openers, bullets, and questions."""

    def __init__(
        self,
        config: dict[str, Any],
        resume_path: Path,
        storage: Storage,
        client: Any | None = None,
    ) -> None:
        self.config = config
        self.resume_path = Path(resume_path)
        self.storage = storage
        self._client = client
        self._resume: str | None = None

    # --- setup --------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise DraftingUnavailable(
                "The anthropic package is not installed."
            ) from exc
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            raise DraftingUnavailable("ANTHROPIC_API_KEY is not set.")
        self._client = anthropic.Anthropic()
        return self._client

    def _get_resume(self) -> str:
        if self._resume is not None:
            return self._resume
        if not self.resume_path.exists():
            raise DraftingUnavailable(
                f"Resume not found at {self.resume_path}. "
                "Drafts need it as context — see SETUP.md step 7."
            )
        self._resume = self.resume_path.read_text(encoding="utf-8").strip()
        if not self._resume:
            raise DraftingUnavailable(f"{self.resume_path} is empty.")
        return self._resume

    # --- public API ---------------------------------------------------------

    def draft_all(self, jobs: list[Job]) -> dict[str, Draft]:
        """Return {job.dedupe_hash: Draft} for as many jobs as we can manage.

        Never raises. Jobs missing from the returned mapping simply get an
        alert with no draft attached.
        """
        if not jobs or not self.enabled:
            return {}

        ttl = int(self.config.get("cache_ttl_days", 30))
        drafts: dict[str, Draft] = {}
        uncached: list[Job] = []

        for job in jobs:
            cached = self.storage.get_draft(job.content_hash, ttl_days=ttl)
            if cached is not None:
                drafts[job.dedupe_hash] = cached
            else:
                uncached.append(job)

        log.info(
            "draft cache checked",
            extra={"cache_hits": len(drafts), "to_generate": len(uncached)},
        )
        if not uncached:
            return drafts

        batch_size = max(1, int(self.config.get("batch_size", 5)))
        for start in range(0, len(uncached), batch_size):
            batch = uncached[start : start + batch_size]
            try:
                generated = self._generate_batch(batch)
            except DraftingUnavailable as exc:
                # Configuration problem — every later batch fails the same way.
                log.warning("drafting unavailable", extra={"error": str(exc)})
                break
            except Exception as exc:
                # A transient API failure. Skip this batch, try the next.
                log.error(
                    "draft batch failed; alerts will send without drafts",
                    extra={"error": str(exc), "batch_size": len(batch)},
                )
                continue

            for job, draft in generated.items():
                drafts[job] = draft

        return drafts

    # --- generation ---------------------------------------------------------

    def _generate_batch(self, jobs: list[Job]) -> dict[str, Draft]:
        client = self._get_client()
        resume = self._get_resume()

        postings = "\n\n".join(_render_posting(i, job) for i, job in enumerate(jobs))
        user_prompt = USER_TEMPLATE.format(
            count=len(jobs),
            words=self.config.get("cover_letter_words", 120),
            bullets=self.config.get("resume_bullets", 3),
            questions=self.config.get("interview_questions", 2),
            postings=postings,
        )

        response = client.messages.create(
            model=self.config.get("model", "claude-sonnet-4-6"),
            max_tokens=int(self.config.get("max_tokens", 4096)),
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_INSTRUCTIONS.format(resume=resume),
                    # The resume and instructions are byte-identical on every
                    # call, so caching them makes repeat runs ~10x cheaper on
                    # the input side.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        if getattr(response, "stop_reason", None) == "refusal":
            raise DraftingUnavailable("The model declined this request.")

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        parsed = _parse_response(text, len(jobs))

        drafts: dict[str, Draft] = {}
        for index, item in parsed.items():
            if index < 0 or index >= len(jobs):
                continue
            job = jobs[index]
            draft = Draft(
                cover_letter_opener=str(item.get("cover_letter_opener", "")).strip(),
                resume_bullets=[str(b).strip() for b in item.get("resume_bullets", [])],
                interview_questions=[
                    str(q).strip() for q in item.get("interview_questions", [])
                ],
            )
            if draft.is_empty():
                continue
            drafts[job.dedupe_hash] = draft
            self.storage.put_draft(job.content_hash, draft)

        log.info(
            "drafts generated",
            extra={"requested": len(jobs), "returned": len(drafts)},
        )
        return drafts


# --- helpers ----------------------------------------------------------------


def _render_posting(index: int, job: Job) -> str:
    # 3000 chars is plenty for the model to pick up the keywords and keeps a
    # long posting from crowding out the others in the batch.
    description = job.description[:3000]
    return (
        f"--- POSTING id={index} ---\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n"
        f"Salary: {job.salary_display}\n"
        f"Description: {description}"
    )


def _parse_response(text: str, expected: int) -> dict[int, dict[str, Any]]:
    """Pull the JSON array out of the response, tolerating stray prose."""
    payload = _extract_json_array(text)
    if payload is None:
        raise ValueError("no JSON array found in the model response")

    items = json.loads(payload)
    if not isinstance(items, list):
        raise ValueError("model response JSON was not an array")

    result: dict[int, dict[str, Any]] = {}
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        # Prefer the id the model echoed back; fall back to array position.
        try:
            index = int(item.get("id", position))
        except (TypeError, ValueError):
            index = position
        result[index] = item

    if len(result) < expected:
        log.warning(
            "model returned fewer drafts than postings",
            extra={"expected": expected, "received": len(result)},
        )
    return result


def _extract_json_array(text: str) -> str | None:
    """Return the outermost [...] block, ignoring brackets inside strings."""
    start = text.find("[")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False

    for position in range(start, len(text)):
        char = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start : position + 1]
    return None
