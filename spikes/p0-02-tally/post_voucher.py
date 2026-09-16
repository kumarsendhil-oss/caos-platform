"""
P0-02 — Post a purchase voucher, verify the split, test duplicates.

Three questions, in order:

  1. Does the voucher import payload work at all? (TC-04, issue #2)
  2. Does the CGST/SGST split actually land? Per FINDINGS.md §2, a
     CREATED/ERRORS:0 response does not mean the data landed — Tally
     silently discards values it does not recognise. The only way to
     know is to read the voucher back. This also settles whether
     GSTDUTYHEAD="CGST" (accepted per §3) computes correctly, or was
     merely accepted.
  3. Does Tally reject a duplicate voucher? ADR 0001 says it does not,
     and CG7's entire justification rests on that. Tally's own TPA
     documentation says "invalid or duplicate requests will reflect in
     the error count", which points the other way. Unresolved, and it
     matters.

Educational Mode only accepts postings on the 1st, 2nd and 31st of a
month, so the date here is 1-Aug-2026, not the 15th used in
docs/spikes/tally_payloads.py.

    python post_voucher.py            # print the payloads
    python post_voucher.py --send     # reset CGST, post, verify, duplicate
    python post_voucher.py --send --company "Some Other Co"
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _args import company_from_argv  # noqa: E402
from _runner import run  # noqa: E402
from tally_voucher_read import (  # noqa: E402
    build_daybook_read,
    parse_vouchers,
    print_vouchers,
)
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Test Traders"

# Educational Mode: postings allowed only on the 1st, 2nd and 31st.
VOUCHER_DATE = "20260801"
VOUCHER_NUMBER = "TEST-INV-0001"

PARTY = "Coastal Components Pvt Ltd"
PURCHASE_LEDGER = "Purchase @18%"
TAXABLE = Decimal("18400.00")
CGST = Decimal("1656.00")   # 9%
SGST = Decimal("1656.00")   # 9%
TOTAL = TAXABLE + CGST + SGST  # 21712.00

# Per FINDINGS.md §3 this is an accepted value; "Central Tax" is silently
# dropped. Whether it *computes* correctly is what test 2 below decides.
CGST_DUTY_HEAD = "CGST"
SGST_DUTY_HEAD = "State Tax"


def _import_envelope(company: str, report: str) -> tuple[ET.Element, ET.Element]:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(env, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")
    reqdesc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(reqdesc, "REPORTNAME").text = report
    sv = ET.SubElement(reqdesc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company

    reqdata = ET.SubElement(importdata, "REQUESTDATA")
    msg = ET.SubElement(reqdata, "TALLYMESSAGE")
    msg.set("xmlns:UDF", "TallyUDF")
    return env, msg


def build_reset_duty_heads(company: str = COMPANY) -> str:
    """The probe left CGST's duty head empty. Restore both before posting."""
    env, msg = _import_envelope(company, "All Masters")
    for name, head in (("CGST", CGST_DUTY_HEAD), ("SGST", SGST_DUTY_HEAD)):
        ledger = ET.SubElement(msg, "LEDGER", NAME=name, ACTION="Alter")
        ET.SubElement(ledger, "NAME").text = name
        ET.SubElement(ledger, "TAXTYPE").text = "GST"
        ET.SubElement(ledger, "GSTDUTYHEAD").text = head
    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_voucher(company: str = COMPANY, number: str = VOUCHER_NUMBER) -> str:
    env, msg = _import_envelope(company, "Vouchers")

    vch = ET.SubElement(
        msg, "VOUCHER", VCHTYPE="Purchase", ACTION="Create", OBJVIEW="Invoice Voucher View"
    )
    ET.SubElement(vch, "DATE").text = VOUCHER_DATE
    ET.SubElement(vch, "EFFECTIVEDATE").text = VOUCHER_DATE
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Purchase"
    ET.SubElement(vch, "VOUCHERNUMBER").text = number
    ET.SubElement(vch, "PARTYLEDGERNAME").text = PARTY
    ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"
    ET.SubElement(vch, "NARRATION").text = "CAOS P0-02 spike — synthetic test voucher"

    # Tally's sign convention: ISDEEMEDPOSITIVE=Yes with a negative
    # AMOUNT is a debit; No with a positive AMOUNT is a credit.
    party = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(party, "LEDGERNAME").text = PARTY
    ET.SubElement(party, "ISDEEMEDPOSITIVE").text = "No"
    ET.SubElement(party, "AMOUNT").text = str(TOTAL)

    for ledger_name, amount in ((PURCHASE_LEDGER, TAXABLE), ("CGST", CGST), ("SGST", SGST)):
        entry = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(entry, "LEDGERNAME").text = ledger_name
        ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(entry, "AMOUNT").text = str(-amount)

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_read_daybook(company: str = COMPANY) -> str:
    """Delegates to the verified Day Book read — see findings #11 and #13."""
    return build_daybook_read(company, VOUCHER_DATE)


def _counts(response: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return out
    for tag in ("CREATED", "ALTERED", "IGNORED", "ERRORS", "EXCEPTIONS", "LASTVCHID"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            out[tag] = el.text.strip()
    return out


def verify_split(response: str) -> None:
    vouchers = parse_vouchers(response)
    print_vouchers(vouchers)
    for v in vouchers:
        found = {n: abs(a) for n, a in v["entries"]}
        for want, expect in (("CGST", CGST), ("SGST", SGST)):
            got = found.get(want)
            if got is None:
                print(f"    MISSING: no {want} entry — the split did not land")
            elif got != expect:
                print(f"    WRONG: {want} is {got}, expected {expect}")


if __name__ == "__main__":
    company = company_from_argv(sys.argv, COMPANY)

    if "--send" not in sys.argv:
        print("=== reset duty heads ===")
        print(build_reset_duty_heads(company))
        print("\n=== voucher ===")
        print(build_voucher(company))
        print(f"\n(dry run — pass --send to run against {company!r})")
        sys.exit(0)

    print(f"Target company: {company!r}\n")

    print("--- 0. reset CGST/SGST duty heads (probe left CGST empty) ---")
    run("voucher-0-reset-duty-heads", build_reset_duty_heads(company))

    print("\n--- 1. post the voucher ---")
    body = run("voucher-1-post", build_voucher(company))
    print(f"  counts: {_counts(body) if body else 'no response'}")

    print("\n--- 2. read it back and verify the split ---")
    body = run("voucher-2-readback", build_read_daybook(company))
    if body:
        verify_split(body)

    print("\n--- 3. post the IDENTICAL voucher again (CG7) ---")
    body = run("voucher-3-duplicate", build_voucher(company))
    counts = _counts(body) if body else {}
    print(f"  counts: {counts}")

    print("\n--- 4. read back again — one voucher or two? ---")
    body = run("voucher-4-readback-after-duplicate", build_read_daybook(company))
    if body:
        verify_split(body)

    print(f"\n{'=' * 64}")
    print("CG7: if step 4 shows TWO vouchers, Tally does NOT prevent")
    print("duplicates and ADR 0001 stands. If it shows ONE, or step 3")
    print("reported errors, ADR 0001's claim is wrong and CG7's")
    print("justification needs revisiting.")
    print("=" * 64)
