"""
P0-06 task 4 — Journal Entries, the other posting path ADR 0011 says
`DraftEntry` may route through. Everything in this spike so far has been
Bills; nothing established that Journals behave the same way.

The specific question is not "does POST /journals work" but whether the
*tax determinants* carry over: Bills accept `source_of_supply` /
`destination_of_supply` and a line-item `tax_id`, and reject a mismatched
CGST/SGST-vs-IGST choice with code 3032. If Journals model tax differently,
`ZohoAdapter.post_entry` cannot treat the two paths as one shape with a
different URL.

Three journals are attempted, each read back:
  1. plain balanced journal, no tax fields at all — the baseline;
  2. the same, plus `source_of_supply`/`destination_of_supply` — do they
     survive a round trip or get dropped?
  3. the same, plus a line-item `tax_id` — accepted, ignored, or rejected?

Usage:
    python post_journal.py            # dry run
    python post_journal.py --send     # post and read back
"""
from __future__ import annotations

import argparse
import sys
import time

from zoho_client import call, get_access_token

AMOUNT = 10000.0
INTRA_STATE = "TN"
INTER_STATE = "KA"


def list_existing_journals(token: str) -> None:
    result = call(token, "GET", "/journals", "list_journals")
    journals = result["data"].get("journals", [])
    print(f"Existing journals in org: {len(journals)}")
    for j in journals[:5]:
        print(f"  {j.get('journal_id')} {j.get('journal_date')} "
              f"{j.get('reference_number')!r} total={j.get('total')}")


def pick_accounts(token: str) -> tuple[dict, dict]:
    """One account to debit, one to credit. Any two real accounts will do."""
    result = call(token, "GET", "/chartofaccounts", "list_chart_of_accounts_jrnl")
    accounts = result["data"].get("chartofaccounts", [])
    debit = next((a for a in accounts
                  if a.get("account_type") == "expense"
                  or a.get("classification") == "expense"), None)
    credit = next((a for a in accounts
                   if a.get("account_id") != (debit or {}).get("account_id")
                   and a.get("account_type") in ("accounts_payable", "other_current_liability",
                                                 "bank", "cash", "other_liability")), None)
    if not debit or not credit:
        print("Could not find a debit/credit account pair. Accounts available:",
              file=sys.stderr)
        for a in accounts:
            print(f"  {a.get('account_name')!r} type={a.get('account_type')}",
                  file=sys.stderr)
        sys.exit(1)
    print(f"Debit : {debit.get('account_name')!r} ({debit.get('account_type')}) "
          f"id={debit.get('account_id')}")
    print(f"Credit: {credit.get('account_name')!r} ({credit.get('account_type')}) "
          f"id={credit.get('account_id')}")
    return debit, credit


def pick_gst18_group(token: str) -> dict | None:
    result = call(token, "GET", "/settings/taxes", "list_taxes_jrnl")
    taxes = result["data"].get("taxes", [])
    return next((t for t in taxes if t.get("tax_percentage") == 18
                 and t.get("tax_type") == "tax_group"), None)


def build_journal(debit_id: str, credit_id: str, reference: str,
                  with_supply_states: bool = False,
                  tax_id: str | None = None) -> dict:
    debit_line = {
        "account_id": debit_id,
        "description": "P0-06 journal probe — debit leg",
        "amount": AMOUNT,
        "debit_or_credit": "debit",
    }
    if tax_id:
        debit_line["tax_id"] = tax_id
    body = {
        "journal_date": time.strftime("%Y-%m-%d"),
        "reference_number": reference,
        "notes": "P0-06 spike — Journal posting probe (ADR 0011)",
        "line_items": [
            debit_line,
            {
                "account_id": credit_id,
                "description": "P0-06 journal probe — credit leg",
                "amount": AMOUNT,
                "debit_or_credit": "credit",
            },
        ],
    }
    if with_supply_states:
        body["source_of_supply"] = INTRA_STATE
        body["destination_of_supply"] = INTER_STATE
    return body


JOURNAL_KEYS = ("journal_id", "journal_date", "reference_number", "total",
                "status", "journal_type", "source_of_supply",
                "destination_of_supply", "gst_treatment", "gst_no",
                "tax_total", "taxes", "is_bill_of_supply", "vat_treatment")


def read_journal_back(token: str, journal_id: str, heading: str) -> dict:
    result = call(token, "GET", f"/journals/{journal_id}", f"get_journal_{journal_id}")
    journal = result["data"].get("journal", {})
    print(f"\n--- {heading} (journal_id={journal_id}) ---")
    for key in JOURNAL_KEYS:
        if key in journal:
            print(f"  {key}: {journal[key]}")
    absent = [k for k in ("source_of_supply", "destination_of_supply", "tax_total", "taxes")
              if k not in journal]
    if absent:
        print(f"  ABSENT from response: {', '.join(absent)}")
    for li in journal.get("line_items", []):
        print("  line_item:", {k: li.get(k) for k in
              ("account_name", "debit_or_credit", "amount", "tax_id",
               "tax_name", "tax_percentage", "tax_amount")})
    return journal


def attempt(token: str, body: dict, label: str, heading: str) -> None:
    result = call(token, "POST", "/journals", label, json_body=body)
    data = result["data"]
    journal = data.get("journal")
    if not journal:
        print(f"\n--- {heading}: REJECTED ---")
        print(f"  code={data.get('code')} message={data.get('message')!r}")
        return
    read_journal_back(token, journal["journal_id"], heading)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args()

    if not args.send:
        print("Dry run — would post three journals (plain / with supply states / "
              "with a line-item tax_id) and read each back.")
        return

    token = get_access_token()
    list_existing_journals(token)
    debit, credit = pick_accounts(token)
    tax_group = pick_gst18_group(token)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    debit_id, credit_id = debit["account_id"], credit["account_id"]

    print("\n=== 1. plain balanced journal, no tax fields ===")
    attempt(token, build_journal(debit_id, credit_id, f"P0-06-JRNL-PLAIN-{stamp}"),
            "post_journal_plain", "PLAIN JOURNAL")

    print("\n=== 2. journal + source/destination of supply ===")
    attempt(token,
            build_journal(debit_id, credit_id, f"P0-06-JRNL-SUPPLY-{stamp}",
                          with_supply_states=True),
            "post_journal_supply_states", "JOURNAL + SUPPLY STATES")

    if tax_group:
        print(f"\n=== 3. journal + line-item tax_id ({tax_group['tax_name']}) ===")
        attempt(token,
                build_journal(debit_id, credit_id, f"P0-06-JRNL-TAX-{stamp}",
                              with_supply_states=True, tax_id=tax_group["tax_id"]),
                "post_journal_with_tax", "JOURNAL + TAX_ID")
    else:
        print("\nNo 18% tax group found — skipping the tax_id journal.")


if __name__ == "__main__":
    main()
