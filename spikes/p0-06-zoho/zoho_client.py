"""
Shared Zoho Books call plumbing for the P0-06 spike scripts.

Extracted from post_bill.py so that every later script (forward-charge test,
duplicate probe, rate-limit probe, journals) goes through *one* request path
and therefore one run_logger call site — rather than each script re-inventing
its own, which is how spike evidence quietly stops being comparable.

Same discipline as before: request headers are never logged (that's where the
bearer token is); response headers now are (see run_logger for why).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

from run_logger import log_call

load_dotenv(Path(__file__).parent / ".env")

# Zoho's India responses carry '₹' in every *_formatted field, which the
# Windows console's default cp1252 cannot encode — printing a raw response
# body crashed a run mid-probe. The run_logger files were already UTF-8, so
# no evidence was lost, but the script died before its later calls.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DC = os.environ.get("ZOHO_DC", "in")
CLIENT_ID = os.environ.get("ZOHO_CLIENT_ID")
CLIENT_SECRET = os.environ.get("ZOHO_CLIENT_SECRET")
ORG_ID = os.environ.get("ZOHO_ORG_ID")

TOKEN_URL = f"https://accounts.zoho.{DC}/oauth/v2/token"
API_BASE = f"https://www.zohoapis.{DC}/books/v3"
TOKENS_FILE = Path(__file__).parent / "tokens.json"

TIMEOUT = 30  # CG6: every external call carries an explicit timeout


def call(token: str, method: str, path_or_url: str, label: str,
         params: dict | None = None, json_body: dict | None = None,
         quiet: bool = False) -> dict:
    """Make an API call and log the real request/response to runs/."""
    url = path_or_url if path_or_url.startswith("http") else f"{API_BASE}{path_or_url}"
    all_params = {"organization_id": ORG_ID, **(params or {})}
    hdrs = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}

    resp = requests.request(method, url, headers=hdrs, params=all_params,
                            json=json_body, timeout=TIMEOUT)
    try:
        data = resp.json()
    except ValueError:
        data = {"_non_json_body": resp.text}

    log_call(label, method, url, params=all_params, body=json_body,
             status_code=resp.status_code, response_body=data,
             response_headers=resp.headers)
    if not quiet:
        print(f"{method} {path_or_url} -> HTTP {resp.status_code}")
    return {"status_code": resp.status_code, "data": data, "headers": dict(resp.headers)}


def get_access_token() -> str:
    """Refresh and return an access token. Never logs the refresh token itself."""
    saved = json.loads(TOKENS_FILE.read_text())
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": saved["refresh_token"],
        },
        timeout=TIMEOUT,
    )
    data = resp.json()
    log_call("refresh_token", "POST", TOKEN_URL,
             body={"grant_type": "refresh_token"},  # not the actual refresh token
             status_code=resp.status_code,
             response_body={"has_access_token": "access_token" in data},
             response_headers=resp.headers)
    if "access_token" not in data:
        # FINDINGS.md #1: Zoho can return HTTP 200 with an error body — never
        # branch on the status code alone.
        print("Refresh failed:", json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
    return data["access_token"]
