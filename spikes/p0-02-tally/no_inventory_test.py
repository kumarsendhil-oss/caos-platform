"""
P0-02 — Does a purchase voucher post to a company without inventory?

WHY: every one of the seven payload variants failed against
'Coastal Test Traders' with a content-free EXCEPTIONS:1. Creating the
same voucher by hand in Tally revealed the cause — that company has
Maintain Inventory: Yes with Integrate Accounts with Inventory: Yes, so
Tally requires stock item entries on a Purchase voucher. None of the
XML variants supplied any.

That leaves a question that matters well beyond this test: must
TallyAdapter always handle inventory, or only for inventory-enabled
clients? Many CA-practice clients are service businesses with no
inventory at all. If an accounting-only purchase posts cleanly to a
no-inventory company, the requirement is conditional on client
configuration — which is a much smaller problem than a universal one,
and it shapes BK-01's extraction scope.

Runs the whole sequence against the new company: create ledgers, post,
read back, verify the split.

    python no_inventory_test.py            # print the payloads
    python no_inventory_test.py --send
    python no_inventory_test.py --send --company "Some Other Co"
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
from tally_voucher_read import (  # noqa: E402
    build_daybook_read,
    parse_vouchers,
    print_vouchers,
)
from tally_xml import sanitise  # noqa: E402

COMPANY = "Coastal Services Ltd"
DATE = "20260801"  # Educational Mode allows the 1st, 2nd and 31st
NUMBER = "SVC-INV-0001"

PARTY = "Coastal Components Pvt Ltd"
PURCHASE = "Purchase @18%"
TAXABLE = Decimal("18400.00")
CGST = Decimal("1656.00")
SGST = Decimal("1656.00")
TOTAL = TAXABLE + CGST + SGST


def _import_env(company: str, report: str) -> tuple[ET.Element, ET.Element]:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(env, "BODY")
    imp = ET.SubElement(body, "IMPORTDATA")
    desc = ET.SubElement(imp, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = report
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    data = ET.SubElement(imp, "REQUESTDATA")
    msg = ET.SubElement(data, "TALLYMESSAGE")
    msg.set("xmlns:UDF", "TallyUDF")
    return env, msg


def build_ledgers(company: str) -> str:
    env, msg = _import_env(company, "All Masters")

    def ledger(name: str, parent: str, duty_head: str | None = None) -> None:
        led = ET.SubElement(msg, "LEDGER", NAME=name, ACTION="Create")
        ET.SubElement(led, "NAME").text = name
        ET.SubElement(led, "PARENT").text = parent
        ET.SubElement(led, "OPENINGBALANCE").text = "0"
        if duty_head:
            ET.SubElement(led, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(led, "TAXTYPE").text = "GST"
            # Per FINDINGS.md section 3: "CGST" and "State Tax" are
            # accepted; "Central Tax" is silently discarded.
            ET.SubElement(led, "GSTDUTYHEAD").text = duty_head
            ET.SubElement(led, "RATEOFTAXCALCULATION").text = "0"

    ledger(PARTY, "Sundry Creditors")
    ledger(PURCHASE, "Purchase Accounts")
    ledger("CGST", "Duties & Taxes", duty_head="CGST")
    ledger("SGST", "Duties & Taxes", duty_head="State Tax")

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_voucher(company: str, number: str = NUMBER) -> str:
    env, msg = _import_env(company, "Vouchers")
    vch = ET.SubElement(msg, "VOUCHER", VCHTYPE="Purchase", ACTION="Create")
    ET.SubElement(vch, "DATE").text = DATE
    ET.SubElement(vch, "EFFECTIVEDATE").text = DATE
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Purchase"
    ET.SubElement(vch, "VOUCHERNUMBER").text = number
    ET.SubElement(vch, "PARTYLEDGERNAME").text = PARTY

    def entry(ledger: str, amount: Decimal, debit: bool) -> None:
        e = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(e, "LEDGERNAME").text = ledger
        ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
        ET.SubElement(e, "AMOUNT").text = str(-amount if debit else amount)

    entry(PARTY, TOTAL, debit=False)
    entry(PURCHASE, TAXABLE, debit=True)
    entry("CGST", CGST, debit=True)
    entry("SGST", SGST, debit=True)

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_readback(company: str) -> str:
    """Delegates to the verified Day Book read — see findings #11 and #13."""
    return build_daybook_read(company, DATE)


def counts(response: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return out
    for tag in ("CREATED", "ALTERED", "IGNORED", "ERRORS", "EXCEPTIONS"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            out[tag] = el.text.strip()
    return out


def verify(response: str) -> None:
    vouchers = parse_vouchers(response)
    print_vouchers(vouchers)
    for v in vouchers:
        found = {n: abs(a) for n, a in v["entries"]}
        for want, expect in (("CGST", CGST), ("SGST", SGST)):
            got = found.get(want)
            if got is None:
                print(f"    MISSING: no {want} entry")
            elif got != expect:
                print(f"    WRONG: {want} is {got}, expected {expect}")


if __name__ == "__main__":
    company = COMPANY
    if "--company" in sys.argv:
        company = sys.argv[sys.argv.index("--company") + 1]

    if "--send" not in sys.argv:
        print("=== ledgers ===")
        print(build_ledgers(company))
        print("\n=== voucher ===")
        print(build_voucher(company))
        print(f"\n(dry run — pass --send to run against {company!r})")
        sys.exit(0)

    print(f"Target company: {company!r}\n")

    print("--- 1. create ledgers ---")
    body = run("noinv-1-ledgers", build_ledgers(company))
    print(f"  counts: {counts(body) if body else 'no response'}")

    print("\n--- 2. post the voucher ---")
    body = run("noinv-2-post", build_voucher(company))
    c = counts(body) if body else {}
    print(f"  counts: {c}")

    created = c.get("CREATED", "0")
    if created == "0":
        print(
            "\n  Voucher NOT created. If this company has Maintain Inventory: No,\n"
            "  then inventory is not the cause and the earlier conclusion was\n"
            "  wrong — look elsewhere."
        )
    else:
        print(
            "\n  Voucher CREATED. Inventory config is the differentiator:\n"
            "  TallyAdapter needs inventory entries only for inventory-enabled\n"
            "  clients, not universally."
        )

    print("\n--- 3. read back and verify the split ---")
    body = run("noinv-3-readback", build_readback(company))
    if body:
        verify(body)

    print("\n--- 4. post the IDENTICAL voucher again (CG7) ---")
    body = run("noinv-4-duplicate", build_voucher(company))
    dup = counts(body) if body else {}
    print(f"  counts: {dup}")

    print("\n--- 5. read back — one voucher or two? ---")
    body = run("noinv-5-readback-after-duplicate", build_readback(company))
    if body:
        verify(body)

    if created != "0":
        print(
            "\n  CG7: two vouchers above means Tally does NOT prevent duplicates,\n"
            "  and ADR 0001 stands. One voucher, or errors at step 4, means\n"
            "  ADR 0001 is wrong and CG7's justification needs revisiting."
        )
    else:
        print("\n  CG7 untested — step 2 never created a voucher.")
