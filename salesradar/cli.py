"""Command line entry point.

    python -m salesradar                 one normal run
    python -m salesradar --dry-run       show what would be filtered and why
    python -m salesradar --weekly-summary  also post the 7-day conversion stats
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import ConfigError, load_config
from .logging_setup import setup_logging
from .runner import run
from .storage import Storage

log = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="salesradar",
        description=(
            "Find fresh GTA sales postings, filter out the commission-only "
            "junk, draft application material, and alert Telegram. "
            "It never applies to anything."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Fetch and filter, then print every posting with the rule that "
            "accepted or rejected it. Sends nothing and records nothing."
        ),
    )
    parser.add_argument(
        "--weekly-summary",
        action="store_true",
        help="Also post the 7-day applied/skipped conversion summary.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (defaults to the one in the repo root).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Override the level set in config.yaml.",
    )
    parser.add_argument(
        "--log-format",
        default=None,
        choices=["json", "text"],
        help="Override the format set in config.yaml. Use text for local runs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    setup_logging(
        level=args.log_level or config.logging.get("level", "INFO"),
        # A dry run is something a human reads, so default it to text.
        fmt=args.log_format
        or ("text" if args.dry_run else config.logging.get("format", "json")),
    )

    log.info(
        "salesradar starting",
        extra={"dry_run": args.dry_run, "db": str(config.db_path)},
    )

    try:
        with Storage(config.db_path) as storage:
            summary = asyncio.run(
                run(
                    config,
                    storage,
                    dry_run=args.dry_run,
                    weekly_summary=args.weekly_summary,
                )
            )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        log.exception("run failed", extra={"error": str(exc)})
        return 1

    # A run where every provider failed is a failure worth surfacing to Actions
    # as a red build; a run that simply found nothing is a success.
    if summary.provider_errors and summary.fetched == 0:
        log.error("every provider failed", extra={"errors": summary.provider_errors})
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
