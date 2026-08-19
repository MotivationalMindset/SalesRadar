"""SQLite state: seen jobs, draft cache, Telegram callbacks, applications.

The database file is committed back to the repo by the Actions workflow, so it
has to survive being checked out on a fresh runner every two hours. Everything
here is therefore idempotent, and schema changes are additive only.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .models import Draft, Job

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    dedupe_hash   TEXT PRIMARY KEY,
    slug          TEXT NOT NULL,
    source        TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT NOT NULL,
    location      TEXT NOT NULL,
    url           TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    alerted_at    TEXT
);

CREATE TABLE IF NOT EXISTS draft_cache (
    content_hash TEXT PRIMARY KEY,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_hash  TEXT NOT NULL,
    decision     TEXT NOT NULL,
    decided_at   TEXT NOT NULL,
    UNIQUE(dedupe_hash)
);

CREATE TABLE IF NOT EXISTS runtime_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_seen_first_seen ON seen_jobs(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_apps_decided ON applications(decided_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    """Thin wrapper over the SQLite file. Use as a context manager."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # --- seen jobs ----------------------------------------------------------

    def has_seen(self, dedupe_hash: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen_jobs WHERE dedupe_hash = ?", (dedupe_hash,)
        ).fetchone()
        return row is not None

    def filter_unseen(self, jobs: list[Job]) -> list[Job]:
        """Drop jobs already in the table, and de-dupe within this batch too.

        Both providers can surface the same posting in a single run, so the
        in-batch check matters as much as the database one.
        """
        if not jobs:
            return []
        seen_now: set[str] = set()
        fresh: list[Job] = []
        for job in jobs:
            key = job.dedupe_hash
            if key in seen_now or self.has_seen(key):
                continue
            seen_now.add(key)
            fresh.append(job)
        return fresh

    def record_seen(self, job: Job, alerted: bool) -> None:
        """Mark a job as seen. Re-recording an existing job is a no-op."""
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO seen_jobs (
                    dedupe_hash, slug, source, source_id, title, company,
                    location, url, first_seen_at, alerted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dedupe_hash) DO NOTHING
                """,
                (
                    job.dedupe_hash,
                    job.dedupe_slug,
                    job.source,
                    job.source_id,
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    _now(),
                    _now() if alerted else None,
                ),
            )

    def get_seen_job(self, dedupe_hash: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM seen_jobs WHERE dedupe_hash = ?", (dedupe_hash,)
        ).fetchone()

    def find_by_hash_prefix(self, prefix: str) -> sqlite3.Row | None:
        """Resolve a truncated hash back to its row.

        Telegram caps callback_data at 64 bytes, so the button carries only the
        first 32 characters of the hash. Anything shorter than 8 is refused
        rather than risking a wrong match.
        """
        if not prefix or len(prefix) < 8:
            return None
        return self._conn.execute(
            "SELECT * FROM seen_jobs WHERE dedupe_hash LIKE ? || '%' LIMIT 1",
            (prefix,),
        ).fetchone()

    def prune_seen(self, older_than_days: int = 120) -> int:
        """Keep the committed database small. Returns the number of rows cut."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=older_than_days)
        ).isoformat()
        with self._tx() as conn:
            cursor = conn.execute(
                "DELETE FROM seen_jobs WHERE first_seen_at < ?", (cutoff,)
            )
            return cursor.rowcount

    # --- draft cache --------------------------------------------------------

    def get_draft(self, content_hash: str, ttl_days: int = 30) -> Draft | None:
        row = self._conn.execute(
            "SELECT payload, created_at FROM draft_cache WHERE content_hash = ?",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        try:
            created = datetime.fromisoformat(row["created_at"])
        except ValueError:
            return None
        if datetime.now(timezone.utc) - created > timedelta(days=ttl_days):
            return None
        try:
            data = json.loads(row["payload"])
        except json.JSONDecodeError:
            log.warning("draft cache row was not valid JSON", extra={"hash": content_hash})
            return None
        return Draft(
            cover_letter_opener=data.get("cover_letter_opener", ""),
            resume_bullets=list(data.get("resume_bullets", [])),
            interview_questions=list(data.get("interview_questions", [])),
        )

    def put_draft(self, content_hash: str, draft: Draft) -> None:
        payload = json.dumps(
            {
                "cover_letter_opener": draft.cover_letter_opener,
                "resume_bullets": draft.resume_bullets,
                "interview_questions": draft.interview_questions,
            },
            ensure_ascii=False,
        )
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO draft_cache (content_hash, payload, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(content_hash) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (content_hash, payload, _now()),
            )

    # --- application decisions ---------------------------------------------

    def record_decision(self, dedupe_hash: str, decision: str) -> None:
        """Log an Applied/Skip button press. The latest press wins."""
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO applications (dedupe_hash, decision, decided_at)
                VALUES (?, ?, ?)
                ON CONFLICT(dedupe_hash) DO UPDATE SET
                    decision = excluded.decision,
                    decided_at = excluded.decided_at
                """,
                (dedupe_hash, decision, _now()),
            )

    def weekly_summary(self, days: int = 7) -> dict[str, int]:
        """Counts for the conversion summary: alerted, applied, skipped."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        alerted = self._conn.execute(
            "SELECT COUNT(*) AS n FROM seen_jobs "
            "WHERE alerted_at IS NOT NULL AND alerted_at >= ?",
            (cutoff,),
        ).fetchone()["n"]
        rows = self._conn.execute(
            "SELECT decision, COUNT(*) AS n FROM applications "
            "WHERE decided_at >= ? GROUP BY decision",
            (cutoff,),
        ).fetchall()
        counts = {row["decision"]: row["n"] for row in rows}
        return {
            "alerted": alerted,
            "applied": counts.get("applied", 0),
            "skipped": counts.get("skipped", 0),
            "no_response": max(
                alerted - counts.get("applied", 0) - counts.get("skipped", 0), 0
            ),
        }

    # --- runtime state ------------------------------------------------------

    def get_state(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM runtime_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_state(self, key: str, value: str) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO runtime_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
