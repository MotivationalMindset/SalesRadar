#!/usr/bin/env python3
"""One-time Gmail authorization. Run this on your own computer, not in Actions.

GitHub Actions is headless — it cannot open a browser for you to click
"Allow". So you do it once here, and this script prints a refresh token that
Actions uses forever after.

    python auth_gmail.py

It opens your browser, asks you to sign in to the dedicated Gmail account, and
prints three values to paste into GitHub repo secrets. Nothing is uploaded
anywhere; the token stays in your terminal.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CLIENT_SECRET_FILE = "client_secret.json"

# gmail.modify is the narrowest scope that still allows marking an alert email
# read after parsing it. If you'd rather the bot never touch the mailbox, set
# providers.indeed_email.mark_read_after_parse to false in config.yaml and
# re-run this with --readonly.
MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print(
            "Missing dependency. Run this first:\n"
            "    pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1

    readonly = "--readonly" in sys.argv
    scopes = [READONLY_SCOPE if readonly else MODIFY_SCOPE]

    secret_path = Path(CLIENT_SECRET_FILE)
    if not secret_path.exists():
        print(
            f"Could not find {CLIENT_SECRET_FILE} in this folder.\n\n"
            "Download it from the Google Cloud Console:\n"
            "  1. https://console.cloud.google.com/apis/credentials\n"
            "  2. Create an OAuth client ID of type 'Desktop app'\n"
            "  3. Download the JSON and save it here as client_secret.json\n\n"
            "SETUP.md step 5 walks through this with screenshots' worth of detail.",
            file=sys.stderr,
        )
        return 1

    print(f"Requesting scope: {scopes[0]}")
    print("A browser window will open. Sign in with the DEDICATED Gmail account")
    print("you created for job alerts — not your personal one.\n")

    flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), scopes)
    # access_type=offline and prompt=consent together guarantee a refresh token
    # even if you've authorized this app before.
    credentials = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )

    if not credentials.refresh_token:
        print(
            "\nGoogle did not return a refresh token. This happens if you have "
            "authorized this app before. Revoke it at "
            "https://myaccount.google.com/permissions and run this again.",
            file=sys.stderr,
        )
        return 1

    with secret_path.open("r", encoding="utf-8") as handle:
        client_config = json.load(handle)
    installed = client_config.get("installed") or client_config.get("web") or {}

    print("\n" + "=" * 70)
    print("SUCCESS — add these three values as GitHub repo secrets")
    print("=" * 70)
    print("\nSecret name:  GMAIL_CLIENT_ID")
    print(f"Secret value: {installed.get('client_id', '')}")
    print("\nSecret name:  GMAIL_CLIENT_SECRET")
    print(f"Secret value: {installed.get('client_secret', '')}")
    print("\nSecret name:  GMAIL_REFRESH_TOKEN")
    print(f"Secret value: {credentials.refresh_token}")
    print("\n" + "=" * 70)
    print("Keep these private. Anyone holding all three can read that mailbox.")
    print("Do NOT commit client_secret.json — .gitignore already excludes it.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
