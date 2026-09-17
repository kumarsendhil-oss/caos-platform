"""
P0-06 task 1 + 2 — forward-charge (normal `tax_id`) Bill posting, and a
sharper BK-08 duplicate probe.

Why this exists: FINDINGS.md #6 only ever exercised the Reverse Charge path,
which by design reports `tax_total: 0.0` and an empty line-item `tax_id` —
RCM *hides* the split, so it could not answer the question the PRD v0.2.1
changelog actually makes a claim about: does Zoho compute a CGST/SGST (or
IGST) breakdown itself when given a `tax_id` and two state codes?

Answering it needs a GST-registered vendor (`gst_treatment: business_gst`
plus a GSTIN), because a vendor without a GSTIN forces RCM (code 71512).
The GSTIN below is fictitious but carries a correctly-computed check digit,
since Zoho validates the checksum.

Two bills are posted when possible:
  - intra-state (source == destination == the org's own state) — should
    produce CGST+SGST if Zoho splits at all;
  - inter-state (source != destination) — should produce IGST.
The pair is what makes the result conclusive: one bill alone cannot
distinguish "Zoho computed a split" from "Zoho echoed what we sent."

Usage:
    python forward_charge_test.py                 # dry run, no writes
    python forward_charge_test.py --send          # post + read back
    python forward_charge_test.py --send --dup-variants
        # additionally reposts the intra-state bill under bill_number
        # variants (trailing space, case change, punctuation) to find out
        # how literal Zoho's native duplicate guard really is — finding #7
        # only proved it catches a byte-identical repeat.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from zoho_client import call, get_access_token

VENDOR_NAME = "P0-06 GST-Registered Test Vendor"
TAXABLE_AMOUNT = 10000.0  # 18% of this is 1800 -> 900/900 if split, unambiguous
INTRA_STATE = "TN"        # org's own state (confirmed live: state_code "TN")
INTER_STATE = "KA"        # any other state, to force the IGST branch

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit(first14: str) -> str:
    """
    Compute the 15th (check) character of a GSTIN.

    Standard algorithm: each of the first 14 characters is valued by its
    position in [0-9A-Z], multiplied by an alternating factor of 1 and 2,
    the product folded as (product // 36) + (product % 36), and the running
    total's complement mod 36 mapped back to a character.
    """
    total = 0
    for i, ch in enumerate(first14):
        value = _GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += value // 36 + value % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def fictitious_gstin(state_code_numeric: str = "33") -> str:
    """A syntactically valid, checksum-correct, entirely fictitious GSTIN."""
    body = f"{state_code_numeric}AACCP1234F1Z"  # 14 chars incl. entity code + 'Z'
    return body + gstin_check_digit(body)


def find_or_create_gst_vendor(token: str, gstin: str) -> dict:
    result = call(token, "GET", "/contacts", "list_contacts_gst_vendor",
                  params={"contact_name": VENDOR_NAME})
    existing = result["data"].get("contacts", [])
    if existing:
        print(f"Using existing GST vendor contact_id={existing[0]['contact_id']}")
        return existing[0]

    body = {
        "contact_name": VENDOR_NAME,
        "contact_type": "vendor",
        "gst_treatment": "business_gst",
        "gst_no": gstin,
        "place_of_contact": INTRA_STATE,
    }
    result = call(token, "POST", "/contacts", "create_gst_vendor", json_body=body)
    contact = result["data"].get("contact")
    if not contact:
        print(json.dumps(result["data"], indent=2), file=sys.stderr)
        sys.exit(1)
    print(f"Created GST vendor contact_id={contact['contact_id']} gstin={gstin}")
    return contact


def pick_tax(token: str) -> tuple[dict, list[dict]]:
    result = call(token, "GET", "/settings/taxes", "list_taxes_fc")
    taxes = result["data"].get("taxes", [])
    print("Taxes visible to this org:")
    for t in taxes:
        print(f"  {t.get('tax_name')!r} id={t.get('tax_id')} "
              f"pct={t.get('tax_percentage')} type={t.get('tax_type')} "
              f"specific={t.get('tax_specific_type')}")
    chosen = next((t for t in taxes if t.get("tax_percentage") == 18), None)
    if not chosen:
        print("No 18% tax available — cannot run the forward-charge test.", file=sys.stderr)
        sys.exit(1)
    return chosen, taxes


def find_expense_account(token: str) -> dict:
    result = call(token, "GET", "/chartofaccounts", "list_chart_of_accounts_fc")
    accounts = result["data"].get("chartofaccounts", [])
    expense = [a for a in accounts
               if a.get("account_type") == "expense" or a.get("classification") == "expense"]
    if not expense:
        print("No expense account found.", file=sys.stderr)
        sys.exit(1)
    preferred = next((a for a in expense
                      if "purchase" in a.get("account_name", "").lower()
                      or "cost of goods" in a.get("account_name", "").lower()),
                     expense[0])
    print(f"Using account {preferred.get('account_name')!r} id={preferred.get('account_id')}")
    return preferred


def post_forward_charge_bill(token: str, vendor_id: str, tax_id: str, account_id: str,
                             bill_number: str, destination: str, label: str) -> dict:
    """Forward charge: line carries `tax_id`, NOT `reverse_charge_tax_id`."""
    body = {
        "vendor_id": vendor_id,
        "bill_number": bill_number,
        "source_of_supply": INTRA_STATE,
        "destination_of_supply": destination,
        "line_items": [
            {
                "name": "P0-06 forward-charge test line item",
                "rate": TAXABLE_AMOUNT,
                "quantity": 1,
                "account_id": account_id,
                "tax_id": tax_id,
            }
        ],
    }
    result = call(token, "POST", "/bills", label, json_body=body)
    return result


TAX_KEYS = ("tax_total", "sub_total", "total", "cgst_total", "sgst_total",
            "igst_total", "cess_total", "is_reverse_charge_applied",
            "gst_treatment", "gst_no", "source_of_supply",
            "destination_of_supply", "tax_rounding", "taxes")


def report_tax_shape(token: str, bill_id: str, heading: str) -> dict:
    result = call(token, "GET", f"/bills/{bill_id}", f"get_bill_fc_{bill_id}")
    bill = result["data"].get("bill", {})
    print(f"\n--- {heading} (bill_id={bill_id}) ---")
    present = [k for k in TAX_KEYS if k in bill]
    for key in present:
        print(f"  {key}: {bill[key]}")
    absent = [k for k in ("cgst_total", "sgst_total", "igst_total") if k not in bill]
    if absent:
        print(f"  ABSENT from response: {', '.join(absent)}")
    for li in bill.get("line_items", []):
        print("  line_item:", {k: li.get(k) for k in
              ("tax_id", "tax_name", "tax_percentage", "tax_type",
               "item_total", "tax_amount")})
    return bill


def run_duplicate_variants(token: str, vendor_id: str, tax_id: str, account_id: str,
                           base_number: str, account_label: str = "") -> None:
    """
    BK-08 probe. Finding #7 proved Zoho rejects a byte-identical
    (vendor, bill_number). The open question is whether that guard is an
    exact string match or something normalised — which decides whether the
    platform's own CG7 duplicate check is redundant for Zoho or essential.
    """
    variants = [
        (base_number + " ", "trailing space"),
        (" " + base_number, "leading space"),
        (base_number.lower(), "lowercased"),
        (base_number.replace("-", ""), "hyphens stripped"),
    ]
    print("\n=== BK-08 duplicate-guard variants ===")
    results = []
    for number, description in variants:
        print(f"\n-- variant: {description} -> {number!r}")
        result = post_forward_charge_bill(
            token, vendor_id, tax_id, account_id, number, INTRA_STATE,
            f"dup_variant_{description.replace(' ', '_')}")
        data = result["data"]
        bill = data.get("bill")
        if bill:
            print(f"   ACCEPTED as a new bill: bill_id={bill['bill_id']} "
                  f"stored bill_number={bill.get('bill_number')!r}")
            results.append((description, "ACCEPTED", bill.get("bill_number")))
        else:
            print(f"   REJECTED: code={data.get('code')} message={data.get('message')!r}")
            results.append((description, f"REJECTED {data.get('code')}", data.get("message")))
        time.sleep(1)

    print("\n=== duplicate-variant summary ===")
    for description, outcome, detail in results:
        print(f"  {description:<18} {outcome:<16} {detail!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="actually make write calls")
    parser.add_argument("--dup-variants", action="store_true",
                        help="also run the BK-08 bill_number variant probe")
    args = parser.parse_args()

    gstin = fictitious_gstin()
    print(f"Fictitious test GSTIN: {gstin} (check digit computed, not guessed)")
    if not args.send:
        print("Dry run — would create a business_gst vendor, post an intra-state "
              "and an inter-state forward-charge Bill, and read both back.")
        return

    token = get_access_token()
    vendor = find_or_create_gst_vendor(token, gstin)
    tax, all_taxes = pick_tax(token)
    account = find_expense_account(token)
    tax_id = tax.get("tax_id")
    account_id = account["account_id"]
    stamp = time.strftime("%Y%m%d-%H%M%S")

    intra_number = f"P0-06-FC-INTRA-{stamp}"
    intra = post_forward_charge_bill(token, vendor["contact_id"], tax_id, account_id,
                                     intra_number, INTRA_STATE, "post_bill_fc_intra")
    if intra["data"].get("bill"):
        report_tax_shape(token, intra["data"]["bill"]["bill_id"],
                         f"INTRA-STATE ({INTRA_STATE} -> {INTRA_STATE})")
    else:
        print(json.dumps(intra["data"], indent=2))

    # Inter-state, deliberately sent with the SAME intra-state tax group first.
    # If Zoho derived the split from the state codes (as the Bills schema
    # reference currently asserts) this would silently come back as IGST.
    inter = post_forward_charge_bill(token, vendor["contact_id"], tax_id, account_id,
                                     f"P0-06-FC-INTER-{stamp}", INTER_STATE,
                                     "post_bill_fc_inter_wrong_tax")
    if inter["data"].get("bill"):
        report_tax_shape(token, inter["data"]["bill"]["bill_id"],
                         f"INTER-STATE ({INTRA_STATE} -> {INTER_STATE}), intra-state tax group")
    else:
        print("Inter-state with the CGST/SGST group was REJECTED: "
              f"code={inter['data'].get('code')} {inter['data'].get('message')!r}")
        igst = next((t for t in all_taxes
                     if t.get("tax_specific_type") == "igst"
                     and t.get("tax_percentage") == 18), None)
        if not igst:
            print("No IGST18 tax available to retry with.")
            return
        print(f"Retrying the same bill with {igst['tax_name']!r} id={igst['tax_id']}")
        inter2 = post_forward_charge_bill(token, vendor["contact_id"], igst["tax_id"],
                                          account_id, f"P0-06-FC-INTER-IGST-{stamp}",
                                          INTER_STATE, "post_bill_fc_inter_igst")
        if inter2["data"].get("bill"):
            report_tax_shape(token, inter2["data"]["bill"]["bill_id"],
                             f"INTER-STATE ({INTRA_STATE} -> {INTER_STATE}), IGST18")
        else:
            print(json.dumps(inter2["data"], indent=2))

    if args.dup_variants and intra["data"].get("bill"):
        run_duplicate_variants(token, vendor["contact_id"], tax_id, account_id, intra_number)


if __name__ == "__main__":
    main()
