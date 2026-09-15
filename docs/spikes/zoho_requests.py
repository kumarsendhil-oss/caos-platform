"""
Zoho Books API request builders — P0-06 spike artifact.

These are the exact HTTP requests ZohoAdapter's stubbed methods
(issues #4, #5, #6) will make. Built against Zoho's own documented API
so they can be validated BEFORE any live client data.

Run this file to print each request:  python zoho_requests.py
Run with credentials in the environment to actually execute them:
    ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET / ZOHO_REFRESH_TOKEN /
    ZOHO_ORGANIZATION_ID / ZOHO_REGION  (default: in)
    python zoho_requests.py --live

IMPORTANT — what this spike does and does not establish:
  - It DOES pin down the endpoints, auth flow and request shapes.
  - It does NOT validate them. Nothing here has been executed against
    Zoho. Every request below is UNVERIFIED until someone runs it with
    real sandbox credentials and pastes back the response.
  - Region matters: the practice is in India, so the accounts server is
    almost certainly accounts.zoho.in and the API domain
    www.zohoapis.in. CONFIRM this rather than assuming — the .com
    defaults in most tutorials will silently fail against an .in account.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from decimal import Decimal

# Region-specific hosts. Zoho enforces these strictly — a token issued by
# accounts.zoho.in will not work against www.zohoapis.com.
REGION = os.environ.get("ZOHO_REGION", "in")
ACCOUNTS_HOST = f"https://accounts.zoho.{REGION}"
API_HOST = f"https://www.zohoapis.{REGION}"

# Scopes needed for the three ZohoAdapter methods.
#   READ  — extract_purchase_register / sales / bank book (#4)
#   CREATE — post_entry, creating Bills (#5)
SCOPES = ",".join([
    "ZohoBooks.bills.CREATE",
    "ZohoBooks.bills.READ",
    "ZohoBooks.invoices.READ",
    "ZohoBooks.contacts.READ",
    "ZohoBooks.contacts.CREATE",
    "ZohoBooks.banking.READ",
    "ZohoBooks.settings.READ",
])


@dataclass
class Request:
    """A single HTTP request, printable as curl or executable via httpx."""

    name: str
    method: str
    url: str
    params: dict[str, str] = field(default_factory=dict)
    body: dict | None = None
    form: dict[str, str] | None = None
    traces_to: str = ""

    def as_curl(self, token: str = "<ACCESS_TOKEN>") -> str:
        parts = [f"curl -X {self.method} '{self.url}"]
        if self.params:
            qs = "&".join(f"{k}={v}" for k, v in self.params.items())
            parts[0] += f"?{qs}"
        parts[0] += "'"
        if self.form:
            for k, v in self.form.items():
                parts.append(f"  --data-urlencode '{k}={v}'")
        else:
            parts.append(f"  -H 'Authorization: Zoho-oauthtoken {token}'")
        if self.body is not None:
            parts.append("  -H 'Content-Type: application/json'")
            parts.append(f"  -d '{json.dumps(self.body)}'")
        return " \\\n".join(parts)


# --------------------------------------------------------------------------
# AUTH — issue #6 (ZB-01, ZB-05)
# --------------------------------------------------------------------------

def auth_step_1_consent_url(client_id: str, redirect_uri: str) -> str:
    """
    Step 1 — one-time browser consent. access_type=offline is REQUIRED to
    receive a refresh token; without it you get an access token only and
    the whole unattended-sync design fails.
    """
    return (
        f"{ACCOUNTS_HOST}/oauth/v2/auth"
        f"?client_id={client_id}"
        f"&response_type=code"
        f"&redirect_uri={redirect_uri}"
        f"&scope={SCOPES}"
        f"&access_type=offline"
    )


def auth_step_2_exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> Request:
    """Step 2 — exchange the one-time code for access + refresh tokens."""
    return Request(
        name="Exchange authorization code for tokens",
        method="POST",
        url=f"{ACCOUNTS_HOST}/oauth/v2/token",
        form={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        traces_to="ZB-01 / issue #6",
    )


def auth_refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> Request:
    """
    Step 3 — refresh. Access tokens expire after 1 hour (3600s), so this
    runs constantly in production; the refresh token itself is permanent.
    """
    return Request(
        name="Refresh access token",
        method="POST",
        url=f"{ACCOUNTS_HOST}/oauth/v2/token",
        form={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        traces_to="ZB-01 / issue #6",
    )


# --------------------------------------------------------------------------
# READ — issue #4 (ZB-02)
# --------------------------------------------------------------------------

def get_organizations() -> Request:
    """
    Every other call needs organization_id. This is the only endpoint that
    doesn't, so it's the correct first call and the natural health check
    for connection_health (issue #6).
    """
    return Request(
        name="List organizations (get organization_id)",
        method="GET",
        url=f"{API_HOST}/books/v3/organizations",
        traces_to="ZB-05 / issue #6",
    )


def get_bills(org_id: str, date_start: str, date_end: str, page: int = 1) -> Request:
    """
    Purchase register equivalent. In Zoho, a supplier invoice is a 'Bill'.
    Normalizes to BooksConnector.LedgerLine.
    """
    return Request(
        name="List bills (purchase register)",
        method="GET",
        url=f"{API_HOST}/books/v3/bills",
        params={
            "organization_id": org_id,
            "date_start": date_start,   # YYYY-MM-DD
            "date_end": date_end,
            "page": str(page),
            "per_page": "200",
        },
        traces_to="ZB-02 / issue #4",
    )


def get_invoices(org_id: str, date_start: str, date_end: str, page: int = 1) -> Request:
    """Sales register equivalent."""
    return Request(
        name="List invoices (sales register)",
        method="GET",
        url=f"{API_HOST}/books/v3/invoices",
        params={
            "organization_id": org_id,
            "date_start": date_start,
            "date_end": date_end,
            "page": str(page),
            "per_page": "200",
        },
        traces_to="ZB-02 / issue #4",
    )


def get_bank_transactions(org_id: str, account_id: str, page: int = 1) -> Request:
    """Bank book equivalent. Feeds Bank Reconciliation (BR-01)."""
    return Request(
        name="List bank transactions (bank book)",
        method="GET",
        url=f"{API_HOST}/books/v3/banktransactions",
        params={
            "organization_id": org_id,
            "account_id": account_id,
            "page": str(page),
            "per_page": "200",
        },
        traces_to="ZB-02 / issue #4",
    )


def get_contacts(org_id: str, page: int = 1) -> Request:
    """
    Vendor/customer master — the Zoho equivalent of Tally's ledger list,
    feeding BK-02's fuzzy vendor matching.
    """
    return Request(
        name="List contacts (vendor master, for BK-02 matching)",
        method="GET",
        url=f"{API_HOST}/books/v3/contacts",
        params={
            "organization_id": org_id,
            "contact_type": "vendor",
            "page": str(page),
            "per_page": "200",
        },
        traces_to="BK-02 / issue #4",
    )


# --------------------------------------------------------------------------
# WRITE — issue #5 (ZB-03)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class BillLine:
    name: str
    account_id: str
    rate: Decimal
    quantity: Decimal = Decimal("1")
    hsn_or_sac: str | None = None
    tax_id: str | None = None


def create_bill(
    org_id: str,
    vendor_id: str,
    bill_number: str,
    bill_date: str,
    lines: list[BillLine],
    gst_treatment: str = "business_gst",
    source_of_supply: str = "TN",
    destination_of_supply: str = "TN",
) -> Request:
    """
    Post a purchase entry — the Zoho equivalent of a Tally purchase voucher.

    Note the structural difference from Tally: Zoho does NOT want explicit
    CGST/SGST/IGST ledger lines. You attach a tax_id per line item and
    Zoho computes the split itself, deriving intra- vs inter-state from
    source_of_supply vs destination_of_supply.

    This finding is what raised ADR 0011 Amendment 1: DraftEntry used to
    carry cgst/sgst/igst amounts, which could not map 1:1 onto this
    request. It now carries tax determinants instead (tax_rate,
    place_of_supply, supplier_state), so the adapter resolves tax_rate to
    a tax_id by direct match rather than inferring a rate from amounts.
    """
    return Request(
        name="Create bill (post purchase entry)",
        method="POST",
        url=f"{API_HOST}/books/v3/bills",
        params={"organization_id": org_id},
        body={
            "vendor_id": vendor_id,
            "bill_number": bill_number,
            "date": bill_date,          # YYYY-MM-DD
            "gst_treatment": gst_treatment,
            "source_of_supply": source_of_supply,
            "destination_of_supply": destination_of_supply,
            "line_items": [
                {
                    "name": ln.name,
                    "account_id": ln.account_id,
                    "rate": str(ln.rate),      # CG5 — Decimal as string, never float
                    "quantity": str(ln.quantity),
                    **({"hsn_or_sac": ln.hsn_or_sac} if ln.hsn_or_sac else {}),
                    **({"tax_id": ln.tax_id} if ln.tax_id else {}),
                }
                for ln in lines
            ],
        },
        traces_to="ZB-03 / issue #5",
    )


def search_bill_by_number(org_id: str, bill_number: str) -> Request:
    """
    CG7 duplicate-prevention support.

    NOTE: CG7's check runs against the platform's OWN Voucher table before
    either adapter is called — this request is NOT that check. It exists to
    answer a spike question: does Zoho itself reject a duplicate
    bill_number? ADR 0001 established Tally does not. If Zoho does, that's
    a difference between adapters worth documenting (CG7 stays either way,
    as defence in depth).
    """
    return Request(
        name="Search bill by number (does Zoho reject duplicates?)",
        method="GET",
        url=f"{API_HOST}/books/v3/bills",
        params={"organization_id": org_id, "bill_number": bill_number},
        traces_to="CG7 spike question",
    )


# --------------------------------------------------------------------------

def build_all() -> list[Request]:
    org = os.environ.get("ZOHO_ORGANIZATION_ID", "<ORGANIZATION_ID>")
    return [
        auth_refresh_access_token(
            os.environ.get("ZOHO_CLIENT_ID", "<CLIENT_ID>"),
            os.environ.get("ZOHO_CLIENT_SECRET", "<CLIENT_SECRET>"),
            os.environ.get("ZOHO_REFRESH_TOKEN", "<REFRESH_TOKEN>"),
        ),
        get_organizations(),
        get_bills(org, "2026-08-01", "2026-08-31"),
        get_invoices(org, "2026-08-01", "2026-08-31"),
        get_contacts(org),
        get_bank_transactions(org, "<BANK_ACCOUNT_ID>"),
        create_bill(
            org,
            vendor_id="<VENDOR_ID>",
            bill_number="TEST-INV-0001",
            bill_date="2026-08-15",
            lines=[
                BillLine(
                    name="Test purchase line",
                    account_id="<EXPENSE_ACCOUNT_ID>",
                    rate=Decimal("18400.00"),
                    hsn_or_sac="998313",
                    tax_id="<GST18_TAX_ID>",
                )
            ],
        ),
        search_bill_by_number(org, "TEST-INV-0001"),
    ]


def main() -> int:
    if "--live" in sys.argv:
        print("Live mode is intentionally not implemented in this spike artifact.")
        print("Run the printed curl commands manually so each response can be")
        print("inspected and recorded in the runbook — see P0-06 runbook step 4.")
        return 1

    print("=" * 70)
    print("ONE-TIME CONSENT URL (open in a browser, step 1 of the OAuth flow)")
    print("=" * 70)
    print(auth_step_1_consent_url(
        os.environ.get("ZOHO_CLIENT_ID", "<CLIENT_ID>"),
        os.environ.get("ZOHO_OAUTH_REDIRECT_URI", "http://localhost:8000/auth/zoho/callback"),
    ))

    for req in build_all():
        print(f"\n{'=' * 70}")
        print(f"{req.name}   [{req.traces_to}]")
        print("=" * 70)
        print(req.as_curl())
    return 0


if __name__ == "__main__":
    sys.exit(main())
