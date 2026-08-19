"""Gmail credentials from environment variables.

GitHub Actions is headless, so it can't run an OAuth consent flow. You run
`python auth_gmail.py` once on your own machine; it opens a browser, you
approve, and it prints a refresh token. That token goes into a repo secret and
is exchanged for a fresh access token on every run.
"""

from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger(__name__)

TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailAuthError(RuntimeError):
    """Gmail credentials are missing or rejected."""


def build_gmail_service(scopes: list[str]) -> Any:
    """Return an authorized Gmail API client built from the env secrets."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise GmailAuthError(
            "Google API libraries are missing. Run: pip install -r requirements.txt"
        ) from exc

    client_id = os.environ.get("GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "").strip()

    missing = [
        name
        for name, value in (
            ("GMAIL_CLIENT_ID", client_id),
            ("GMAIL_CLIENT_SECRET", client_secret),
            ("GMAIL_REFRESH_TOKEN", refresh_token),
        )
        if not value
    ]
    if missing:
        raise GmailAuthError(
            f"Missing Gmail secret(s): {', '.join(missing)}. "
            "Run auth_gmail.py locally and follow SETUP.md step 5."
        )

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri=TOKEN_URI,
        scopes=scopes,
    )

    # cache_discovery=False keeps googleapiclient from trying to write a cache
    # directory on an ephemeral runner.
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)
