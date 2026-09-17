"""
P0-06 — Zoho Books write-side spike. Mirrors what post_voucher.py does for
Tally: post something real, read it back, and check the *specific* fields
that matter for BK-04/ADR 0011 Amendment 1 — not just "did it return 200."

Specifically this checks the PRD's claim (v0.2.1 changelog) that Zoho takes
a per-line tax_id and computes the CGST/SGST split itself, rather than
requiring explicit split ledger lines like Tally does.

Self-healing: if the org has no GST tax configured (as Integra Agro's trial
org didn't — see FINDINGS.md #4), this creates a CGST9 + SGST9 tax group
automatically before posting.

Every real API call's request/response is written to runs/ via run_logger —
see that module for why (and what's deliberately never logged: headers/tokens).

Usage:
    python post_bill.py --send            # create vendor + tax lookup + post + read back
    python post_bill.py --send --duplicate  # also posts the same bill a 2nd time (BK-08 check)

Without --send, does a dry run: shows what would be posted, makes no writes.
"""
import argparse
import json
import sys
import time

from zoho_client import call, get_access_token

TEST_VENDOR_NAME = "P0-06 Spike Test Vendor"
TAXABLE_AMOUNT = 10000.0  # chosen so an 18% GST split is unambiguous: 900/900 or 1800
# Unique per run. This used to be the fixed string "P0-06-TEST-001", which made
# every rerun fail as a duplicate once the first one landed (FINDINGS.md #7 —
# Zoho enforces vendor+bill_number uniqueness natively, code 13011). The
# duplicate check is now driven explicitly by --duplicate, which reposts *this*
# run's number a second time, rather than depending on a collision with the
# leftover state of some earlier run.
TEST_BILL_NUMBER = f"P0-06-TEST-{time.strftime('%Y%m%d-%H%M%S')}"


def find_or_create_vendor(token: str) -> str:
    result = call(token, "GET", "/contacts", "list_contacts",
                   params={"contact_name": TEST_VENDOR_NAME})
    existing = result["data"].get("contacts", [])
    if existing:
        cid = existing[0]["contact_id"]
        print(f"Using existing vendor contact_id={cid}")
        return cid

    result = call(token, "POST", "/contacts", "create_vendor",
                   json_body={"contact_name": TEST_VENDOR_NAME, "contact_type": "vendor"})
    data = result["data"]
    if "contact" not in data:
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
    cid = data["contact"]["contact_id"]
    print(f"Created vendor contact_id={cid}")
    return cid


def _create_simple_tax(token: str, name: str, percentage: float, specific_type: str) -> dict:
    result = call(token, "POST", "/settings/taxes", f"create_tax_{specific_type}",
                   json_body={
                       "tax_name": name,
                       "tax_percentage": percentage,
                       "tax_type": "tax",
                       "tax_specific_type": specific_type,
                   })
    data = result["data"]
    if "tax" not in data:
        print(json.dumps(data, indent=2), file=sys.stderr)
        sys.exit(1)
    return data["tax"]


def ensure_gst_tax(token: str) -> dict:
    """
    Find an 18% GST tax to use, creating one if the org has none.

    NOTE — this is exploratory: a normal India-edition org auto-provisions
    CGST+SGST tax groups on setup, but this trial org came up with zero
    taxes configured (see FINDINGS.md #4). Once GST was enabled on the org,
    Zoho auto-provisioned one, so this fallback path hasn't actually been
    exercised live — kept in case a future org needs it.
    """
    result = call(token, "GET", "/settings/taxes", "list_taxes")
    taxes = result["data"].get("taxes", [])

    existing_18 = next((t for t in taxes if t.get("tax_percentage") == 18), None)
    if existing_18:
        print(f"Using existing tax: {existing_18.get('tax_name')} (18%) "
              f"id={existing_18.get('tax_id')}")
        return existing_18

    existing_group = next(
        (t for t in taxes if t.get("tax_type") == "tax_group"
         and t.get("tax_percentage") == 18),
        None,
    )
    if existing_group:
        print(f"Using existing tax group: {existing_group.get('tax_name')} (18%) "
              f"id={existing_group.get('tax_id')}")
        return existing_group

    print("No 18% GST tax found — creating CGST 9% + SGST 9% and grouping them.")
    cgst = _create_simple_tax(token, "CGST9 (P0-06)", 9, "cgst")
    sgst = _create_simple_tax(token, "SGST9 (P0-06)", 9, "sgst")

    result = call(token, "POST", "/settings/taxgroups", "create_tax_group",
                   json_body={
                       "tax_group_name": "GST18 (CGST9 + SGST9) — P0-06",
                       "taxes": [cgst["tax_id"], sgst["tax_id"]],
                   })
    group = result["data"].get("tax_group")
    if not group:
        print("Tax group creation failed — see runs/ for the full response.",
              file=sys.stderr)
        sys.exit(1)
    return group


def find_expense_account(token: str) -> dict:
    result = call(token, "GET", "/chartofaccounts", "list_chart_of_accounts")
    accounts = result["data"].get("chartofaccounts", [])
    if not accounts:
        print("No chart of accounts found at all.", file=sys.stderr)
        sys.exit(1)

    expense_accounts = [a for a in accounts if a.get("account_type") == "expense"
                         or a.get("classification") == "expense"]
    if not expense_accounts:
        print("No account with an Expense classification found — see runs/ for the full list.",
              file=sys.stderr)
        sys.exit(1)

    preferred = next(
        (a for a in expense_accounts
         if "purchase" in a.get("account_name", "").lower()
         or "cost of goods" in a.get("account_name", "").lower()),
        expense_accounts[0],
    )
    print(f"Using account: {preferred.get('account_name')} "
          f"({preferred.get('account_type')}) id={preferred.get('account_id')}")
    return preferred


def post_bill(token: str, vendor_id: str, tax_id: str, bill_number: str, account_id: str) -> dict:
    body = {
        "vendor_id": vendor_id,
        "bill_number": bill_number,
        # Our test vendor has no GSTIN, so this purchase falls under India's
        # Reverse Charge Mechanism (RCM) — see FINDINGS.md #6.
        "is_reverse_charge_applied": True,
        "line_items": [
            {
                "name": "P0-06 spike test line item",
                "rate": TAXABLE_AMOUNT,
                "quantity": 1,
                "account_id": account_id,
                # NOT tax_id — see FINDINGS.md #6: Zoho's docs example shows
                # both together, but the live API rejects that (code 71510).
                "reverse_charge_tax_id": tax_id,
            }
        ],
    }
    result = call(token, "POST", "/bills", "post_bill", json_body=body)
    print(json.dumps(result["data"], indent=2)[:2000])
    return result["data"]


def read_bill_back(token: str, bill_id: str):
    result = call(token, "GET", f"/bills/{bill_id}", f"get_bill_{bill_id}")
    bill = result["data"].get("bill", {})
    print("\n--- fields relevant to the tax-split question ---")
    for key in ("tax_id", "tax_total", "sub_total", "total",
                "cgst_total", "sgst_total", "igst_total", "is_inclusive_tax",
                "is_reverse_charge_applied", "source_of_supply", "destination_of_supply"):
        if key in bill:
            print(f"  {key}: {bill[key]}")
    for li in bill.get("line_items", []):
        print("  line_item:", {k: li.get(k) for k in
              ("tax_id", "tax_name", "tax_percentage", "tax_amount", "item_total")})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="actually make write calls")
    parser.add_argument("--duplicate", action="store_true",
                         help="also post the same bill a second time (BK-08 duplicate check)")
    args = parser.parse_args()

    if not args.send:
        print("Dry run — would create/find vendor, look up an 18% GST tax rate, "
              f"post a Bill for a {TAXABLE_AMOUNT} taxable line, and read it back.")
        print("Re-run with --send to actually do it.")
        return

    token = get_access_token()
    vendor_id = find_or_create_vendor(token)
    tax = ensure_gst_tax(token)
    account = find_expense_account(token)

    tax_ref = tax.get("tax_id") or tax.get("tax_group_id")
    data = post_bill(token, vendor_id, tax_ref, TEST_BILL_NUMBER, account["account_id"])
    bill = data.get("bill")
    if not bill:
        print("Bill creation failed — see runs/ for the full response.", file=sys.stderr)
        sys.exit(1)

    read_bill_back(token, bill["bill_id"])

    if args.duplicate:
        print("\n=== Posting the same bill again (duplicate check, BK-08) ===")
        print(f"Same vendor, same bill_number ({TEST_BILL_NUMBER}), same amount — "
              "on purpose, to see whether Zoho's write API rejects this as a "
              "duplicate on its own or silently allows it.")
        data2 = post_bill(token, vendor_id, tax_ref, TEST_BILL_NUMBER, account["account_id"])
        bill2 = data2.get("bill")
        if bill2:
            print(f"\nSecond post succeeded too -> bill_id={bill2['bill_id']} "
                  f"(different from first: {bill2['bill_id'] != bill['bill_id']})")
            print("If this succeeded without any warning/rejection, that "
                  "confirms BK-08's assumption: Zoho's write API does NOT "
                  "prevent duplicate bills on its own — the platform must.")


if __name__ == "__main__":
    main()
