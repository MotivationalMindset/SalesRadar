"""Telegram delivery: alerts out, button presses in.

SalesRadar runs as a cron job, not a long-lived bot process, so there is no
webhook and nothing listening between runs. Button presses queue up on
Telegram's side and are drained at the start of the next run via getUpdates,
using an offset stored in SQLite. A press is therefore logged within two hours
rather than instantly, which is fine for a weekly conversion summary.
"""

from __future__ import annotations

import html
import logging
import os
from typing import Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .models import ScreenedJob
from .storage import Storage

log = logging.getLogger(__name__)

APPLIED = "applied"
SKIPPED = "skipped"

# Telegram caps callback_data at 64 bytes, so the 64-char dedupe hash is
# truncated. 32 hex characters is 128 bits of prefix — collision risk is nil at
# this scale, and storage resolves the prefix back to the full row.
_HASH_PREFIX_LEN = 32
_OFFSET_KEY = "telegram_update_offset"
_MAX_MESSAGE_CHARS = 4096


class TelegramNotifier:
    """Sends alerts and drains queued button presses."""

    def __init__(
        self,
        bot: Bot,
        chat_id: str,
        config: dict[str, Any],
        storage: Storage,
    ) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.config = config
        self.storage = storage

    @classmethod
    def from_env(cls, config: dict[str, Any], storage: Storage) -> TelegramNotifier:
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        missing = [
            name
            for name, value in (
                ("TELEGRAM_BOT_TOKEN", token),
                ("TELEGRAM_CHAT_ID", chat_id),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing Telegram secret(s): {', '.join(missing)}. See SETUP.md step 4."
            )
        return cls(Bot(token=token), chat_id, config, storage)

    # --- sending ------------------------------------------------------------

    async def send_alert(self, screened: ScreenedJob) -> bool:
        """Send one job alert. Returns True when Telegram accepted it."""
        text = format_alert(screened)
        keyboard = _build_keyboard(screened.job.dedupe_hash)

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=not self.config.get(
                    "disable_web_page_preview", False
                ),
            )
        except TelegramError as exc:
            log.error(
                "telegram send failed",
                extra={
                    "error": str(exc),
                    "title": screened.job.title,
                    "company": screened.job.company,
                },
            )
            return False
        return True

    async def send_text(self, text: str) -> bool:
        """Send a plain message (used for the weekly summary and run errors)."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text[:_MAX_MESSAGE_CHARS],
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except TelegramError as exc:
            log.error("telegram send failed", extra={"error": str(exc)})
            return False
        return True

    # --- receiving ----------------------------------------------------------

    async def drain_callbacks(self) -> int:
        """Process button presses queued since the last run.

        Returns the number of decisions recorded. Failures here are logged and
        swallowed — a stuck callback must never stop the run from alerting.
        """
        stored_offset = self.storage.get_state(_OFFSET_KEY)
        offset = int(stored_offset) if stored_offset else None

        try:
            updates = await self.bot.get_updates(
                offset=offset, timeout=0, allowed_updates=["callback_query"]
            )
        except TelegramError as exc:
            log.warning("could not fetch telegram updates", extra={"error": str(exc)})
            return 0

        recorded = 0
        last_update_id: int | None = None

        for update in updates:
            last_update_id = update.update_id
            query = update.callback_query
            if query is None or not query.data:
                continue

            action, _, hash_prefix = query.data.partition(":")
            decision = {"a": APPLIED, "s": SKIPPED}.get(action)
            if decision is None:
                continue

            row = self.storage.find_by_hash_prefix(hash_prefix)
            if row is None:
                log.warning("callback referenced an unknown job", extra={"data": query.data})
                await _answer(query, "That job is no longer in the database.")
                continue

            self.storage.record_decision(row["dedupe_hash"], decision)
            recorded += 1

            label = "Applied ✅" if decision == APPLIED else "Skipped ❌"
            await _answer(query, f"Logged: {label}")
            # Replace the buttons with the decision so the chat history shows
            # what was chosen without needing to open the database.
            try:
                await query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton(label, callback_data="noop")]]
                    )
                )
            except TelegramError:
                # Message too old to edit, or unchanged. The decision is saved.
                pass

        if last_update_id is not None:
            # +1 acknowledges everything up to here so it isn't re-delivered.
            self.storage.set_state(_OFFSET_KEY, str(last_update_id + 1))

        if recorded:
            log.info("telegram decisions recorded", extra={"count": recorded})
        return recorded


# --- formatting -------------------------------------------------------------


def format_alert(screened: ScreenedJob) -> str:
    """Build the alert message body. HTML parse mode, so text is escaped."""
    job = screened.job
    parts: list[str] = []

    warning = "⚠️ " if screened.uncertain else ""
    parts.append(f"{warning}🎯 <b>{_esc(job.title)}</b> @ {_esc(job.company)}")

    location = _esc(job.location) or "Location not given"
    parts.append(f"📍 {location} · 💰 {_esc(job.salary_display)}")

    age = job.age_hours
    if age is None:
        parts.append("⏱️ Posted recently")
    elif age < 1:
        parts.append("⏱️ Posted less than an hour ago")
    else:
        parts.append(f"⏱️ Posted {age:.0f} hours ago")

    if job.url:
        parts.append(f'<a href="{_esc(job.url)}">Apply here</a>')

    if screened.uncertain and job.uncertain_reasons:
        reasons = "; ".join(job.uncertain_reasons[:2])
        parts.append(f"\n⚠️ <i>Check this one: {_esc(reasons)}</i>")

    draft = screened.draft
    if draft is not None and not draft.is_empty():
        parts.append("\n———")
        if draft.cover_letter_opener:
            parts.append(f"\n<b>Cover letter opener</b>\n{_esc(draft.cover_letter_opener)}")
        if draft.resume_bullets:
            bullets = "\n".join(f"• {_esc(b)}" for b in draft.resume_bullets)
            parts.append(f"\n<b>Resume tweaks</b>\n{bullets}")
        if draft.interview_questions:
            questions = "\n".join(f"{i}. {_esc(q)}" for i, q in enumerate(draft.interview_questions, 1))
            parts.append(f"\n<b>Ask them</b>\n{questions}")
    else:
        parts.append("\n———\n<i>No draft generated for this one.</i>")

    message = "\n".join(parts)
    if len(message) > _MAX_MESSAGE_CHARS:
        message = message[: _MAX_MESSAGE_CHARS - 20].rstrip() + "\n<i>…truncated</i>"
    return message


def format_weekly_summary(counts: dict[str, int]) -> str:
    """The conversion summary posted at the end of the week."""
    alerted = counts.get("alerted", 0)
    applied = counts.get("applied", 0)
    skipped = counts.get("skipped", 0)
    no_response = counts.get("no_response", 0)
    rate = (applied / alerted * 100) if alerted else 0.0

    return (
        "📊 <b>SalesRadar — last 7 days</b>\n\n"
        f"Jobs alerted: <b>{alerted}</b>\n"
        f"Applied ✅: <b>{applied}</b>\n"
        f"Skipped ❌: <b>{skipped}</b>\n"
        f"No decision: {no_response}\n\n"
        f"Application rate: <b>{rate:.0f}%</b>"
    )


def _build_keyboard(dedupe_hash: str) -> InlineKeyboardMarkup:
    prefix = dedupe_hash[:_HASH_PREFIX_LEN]
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Applied ✅", callback_data=f"a:{prefix}"),
                InlineKeyboardButton("Skip ❌", callback_data=f"s:{prefix}"),
            ]
        ]
    )


async def _answer(query: Any, text: str) -> None:
    try:
        await query.answer(text=text)
    except TelegramError:
        # Callback answers expire after ~15 minutes; the decision still saved.
        pass


def _esc(value: str) -> str:
    return html.escape(value or "", quote=True)
