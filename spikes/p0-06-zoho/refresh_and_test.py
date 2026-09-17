"""
P0-06 — Zoho Books OAuth spike, step 2: use the saved refresh token to get
a fresh access token (this is the flow the real ZohoAdapter will run on
every use — access tokens expire hourly), then confirm the org is reachable.

Usage:
    python refresh_and_test.py
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
ORG_ID = os.environ.get("ZOHO_ORG_ID")

TOKEN_URL = f"https://accounts.zoho.{DC}/oauth/v2/token"
API_BASE = f"https://www.zohoapis.{DC}/books/v3"
TOKENS_FILE = Path(__file__).parent / "tokens.json"


def refresh_access_token() -> str:
    if not TOKENS_FILE.exists():
        print("tokens.json not found — run get_tokens.py first.", file=sys.stderr)
        sys.exit(1)

    saved = json.loads(TOKENS_FILE.read_text())
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": saved["refresh_token"],
        },
        timeout=30,
    )
    data = resp.json()
    print(f"Refresh -> HTTP {resp.status_code}")
    if "access_token" not in data:
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
    return data["access_token"]


def test_read(access_token: str):
    resp = requests.get(
        f"{API_BASE}/organizations",
        headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        timeout=30,
    )
    print(f"\nGET /organizations -> HTTP {resp.status_code}")
    print(json.dumps(resp.json(), indent=2)[:1500])

    if ORG_ID:
        resp2 = requests.get(
            f"{API_BASE}/contacts",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"organization_id": ORG_ID},
            timeout=30,
        )
        print(f"\nGET /contacts (org {ORG_ID}) -> HTTP {resp2.status_code}")
        print(json.dumps(resp2.json(), indent=2)[:1500])


if __name__ == "__main__":
    token = refresh_access_token()
    test_read(token)
