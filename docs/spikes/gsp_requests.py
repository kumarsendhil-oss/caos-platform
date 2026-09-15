"""
WhiteBooks GSP API request builders — P0-04 spike artifact.

These are the calls the Reconciliation Agent (RC-01) makes to fetch
GSTR-2A/2B, per ADR 0002 (direct GSP integration, bypassing Winman).

Run this file to print each request:  python gsp_requests.py

IMPORTANT — what this spike does and does not establish:
  - It DOES pin down the two-layer auth model and the request shapes.
  - It does NOT validate them. Nothing here has been executed. Every
    request is UNVERIFIED until run against the sandbox.
  - It does NOT resolve the per-client onboarding question raised in the
    runbook (GST portal API access, 30-day expiry). That is the finding
    that matters most from this spike and it is an operational question,
    not a technical one.

Two distinct auth layers — do not conflate them:

  1. GSP layer (us -> WhiteBooks). OAuth2 client_credentials. One
     credential pair for the practice. Token ~1 hour.
  2. Taxpayer layer (us -> GSTN, via WhiteBooks, per client GSTIN).
     OTP-based session, established per client. This is the layer
     ADR 0002 flagged as "doesn't go away".
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

SANDBOX_HOST = "https://apisandbox.whitebooks.in"
PRODUCTION_HOST = "https://api.whitebooks.in"

HOST = os.environ.get("GSP_BASE_URL", SANDBOX_HOST)


@dataclass
class Request:
    name: str
    method: str
    path: str
    layer: str  # "GSP" | "Taxpayer"
    params: dict[str, str] = field(default_factory=dict)
    body: dict | None = None
    headers: dict[str, str] = field(default_factory=dict)
    traces_to: str = ""
    note: str = ""

    def as_curl(self) -> str:
        url = f"{HOST}{self.path}"
        if self.params:
            url += "?" + "&".join(f"{k}={v}" for k, v in self.params.items())
        parts = [f"curl -X {self.method} '{url}'"]
        for k, v in self.headers.items():
            parts.append(f"  -H '{k}: {v}'")
        if self.body is not None:
            parts.append("  -H 'Content-Type: application/json'")
            parts.append(f"  -d '{json.dumps(self.body)}'")
        return " \\\n".join(parts)


# --------------------------------------------------------------------------
# Layer 1 — GSP authentication (practice-wide, once)
# --------------------------------------------------------------------------

def gsp_token() -> Request:
    """
    OAuth2 client_credentials. One credential pair for the whole practice,
    not per client. Token is ~1 hour, so this runs continuously in
    production — cache it rather than re-requesting per client call.
    """
    return Request(
        name="GSP: obtain bearer token (client_credentials)",
        method="POST",
        path="/oauth/token",
        layer="GSP",
        body={
            "grant_type": "client_credentials",
            "client_id": os.environ.get("GSP_CLIENT_ID", "<CLIENT_ID>"),
            "client_secret": os.environ.get("GSP_CLIENT_SECRET", "<CLIENT_SECRET>"),
        },
        traces_to="ADR 0002 / RC-01",
        note="Exact path unverified — confirm against WhiteBooks' own docs.",
    )


# --------------------------------------------------------------------------
# Layer 2 — Taxpayer authentication (per client GSTIN)
# --------------------------------------------------------------------------

def taxpayer_otp_request(gstin: str, username: str) -> Request:
    """
    Triggers an OTP to the client's registered mobile/email.

    This is RC-01a's "doesn't go away" step. ADR 0002 says it becomes
    "a scriptable, automated authentication step" — that framing needs
    testing. An OTP delivered to the CLIENT's phone is not something the
    practice can script unattended; someone has to relay it.
    """
    return Request(
        name="Taxpayer: request OTP for a client GSTIN",
        method="POST",
        path="/gst/authenticate",
        layer="Taxpayer",
        headers={"Authorization": "Bearer <GSP_TOKEN>", "gstin": gstin},
        body={"action": "OTPREQUEST", "username": username, "gstin": gstin},
        traces_to="ADR 0002 / RC-01a",
    )


def taxpayer_otp_verify(gstin: str, username: str, otp: str) -> Request:
    """Exchanges the OTP for an auth token scoped to that GSTIN."""
    return Request(
        name="Taxpayer: verify OTP, establish session",
        method="POST",
        path="/gst/authenticate",
        layer="Taxpayer",
        headers={"Authorization": "Bearer <GSP_TOKEN>", "gstin": gstin},
        body={"action": "AUTHTOKEN", "username": username, "gstin": gstin, "otp": otp},
        traces_to="ADR 0002 / RC-01a",
        note="Record the returned session's TTL — it determines re-auth frequency.",
    )


# --------------------------------------------------------------------------
# The actual payload — GSTR-2B fetch (RC-01)
# --------------------------------------------------------------------------

def fetch_gstr2b(gstin: str, period: str) -> Request:
    """
    The call the whole GSP integration exists for.

    period is MMYYYY (e.g. "082026"), NOT the ISO format Zoho uses or
    the YYYYMMDD Tally uses — three backends, three date formats.
    """
    return Request(
        name="Fetch GSTR-2B for a client/period",
        method="GET",
        path="/gst/returns/gstr2b",
        layer="Taxpayer",
        params={"gstin": gstin, "ret_period": period},
        headers={
            "Authorization": "Bearer <GSP_TOKEN>",
            "gstin": gstin,
            "auth-token": "<TAXPAYER_AUTH_TOKEN>",
        },
        traces_to="RC-01 / issue #1 equivalent",
    )


def fetch_gstr2a(gstin: str, period: str, section: str = "B2B") -> Request:
    """
    GSTR-2A is the live/dynamic view; 2B is the static monthly snapshot.
    RC-01 names both. 2B is the right default for reconciliation (it's
    what ITC eligibility is determined against); 2A matters for spotting
    supplier filings that landed after the 2B cutoff.
    """
    return Request(
        name="Fetch GSTR-2A (dynamic view, by section)",
        method="GET",
        path="/gst/returns/gstr2a",
        layer="Taxpayer",
        params={"gstin": gstin, "ret_period": period, "section": section},
        headers={
            "Authorization": "Bearer <GSP_TOKEN>",
            "gstin": gstin,
            "auth-token": "<TAXPAYER_AUTH_TOKEN>",
        },
        traces_to="RC-01",
    )


def search_gstin(gstin: str) -> Request:
    """
    Public API — no taxpayer auth needed. Useful for BK-02/RC-02: validating
    a vendor GSTIN scraped off an invoice before trying to match on it.
    Cheap win, worth testing since it needs no per-client consent.
    """
    return Request(
        name="Search/validate a GSTIN (public API, no taxpayer auth)",
        method="GET",
        path="/gst/public/search",
        layer="GSP",
        params={"gstin": gstin},
        headers={"Authorization": "Bearer <GSP_TOKEN>"},
        traces_to="BK-02 / RC-02 support",
    )


# --------------------------------------------------------------------------

def build_all() -> list[Request]:
    gstin = os.environ.get("GSP_TEST_GSTIN", "<SANDBOX_GSTIN>")
    username = os.environ.get("GSP_TEST_USERNAME", "<GST_PORTAL_USERNAME>")
    return [
        gsp_token(),
        taxpayer_otp_request(gstin, username),
        taxpayer_otp_verify(gstin, username, "<OTP>"),
        fetch_gstr2b(gstin, "082026"),
        fetch_gstr2a(gstin, "082026"),
        search_gstin(gstin),
    ]


def main() -> int:
    print(f"Host: {HOST}")
    print("(set GSP_BASE_URL to switch sandbox/production)\n")
    for req in build_all():
        print("=" * 70)
        print(f"[{req.layer}] {req.name}   ({req.traces_to})")
        print("=" * 70)
        print(req.as_curl())
        if req.note:
            print(f"\n  NOTE: {req.note}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
