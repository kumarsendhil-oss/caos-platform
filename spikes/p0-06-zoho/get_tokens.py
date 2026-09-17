"""
P0-06 — Zoho Books OAuth spike, step 1: exchange the Self Client grant code
for an access token + refresh token. Run this ONCE per grant code (they
expire in minutes and are single-use). The refresh token it saves is what
every later script/run will actually depend on.

Usage:
    cp .env.example .env
    # fill in ZOHO_DC, ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, ZOHO_GRANT_CODE
    pip install requests python-dotenv
    python get_tokens.py
"""
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

load_dotenv()

DC = os.environ.get("ZOHO_DC", "in")
CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
GRANT_CODE = os.environ.get("ZOHO_GRANT_CODE")

TOKEN_URL = f"https://accounts.zoho.{DC}/oauth/v2/token"
TOKENS_FILE = Path(__file__).parent / "tokens.json"  # gitignore this file


def main():
    missing = [
        name
        for name, val in [
            ("ZOHO_CLIENT_ID", CLIENT_ID),
            ("ZOHO_CLIENT_SECRET", CLIENT_SECRET),
            ("ZOHO_GRANT_CODE", GRANT_CODE),
        ]
        if not val
    ]
    if missing:
        print(f"Missing in .env: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": "https://www.zoho.com/books",
            "code": GRANT_CODE,
        },
        timeout=30,
    )

    data = resp.json()
    print(f"HTTP {resp.status_code}")
    print(json.dumps(data, indent=2))

    if "refresh_token" not in data:
        print(
            "\nNo refresh_token in response — grant code likely expired or "
            "already used. Generate a fresh one from the Self Client's "
            "Generate Code tab and retry.",
            file=sys.stderr,
        )
        sys.exit(1)

    TOKENS_FILE.write_text(json.dumps(data, indent=2))
    print(f"\nSaved to {TOKENS_FILE} (refresh_token is the durable one).")


if __name__ == "__main__":
    main()
