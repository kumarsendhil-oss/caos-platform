"""
P0-02 — Is VCHTYPE="Sales" structurally analogous to VCHTYPE="Purchase"?

WHY: every voucher finding in this repo (#7, #8, #9, #21, #21a, #26,
#28, #29) is a Purchase voucher. "Sales" appears nowhere in
docs/CAOS-tally-integration-schema-reference.md, and the customer-facing
feature documentation now lists "Sales invoices to clients" as untested.
Sales is not even an enumerated unknown in section 6.2/6.3 — it is simply
absent. A CA practice posts at least as many sales invoices as purchase
bills, so this gap sits directly under BK-01.

The specific thing NOT being assumed: section 4.2 established that an
omitted OBJVIEW yields accounting view and posts fine without inventory
entries — across seven *Purchase* variants. Tally's UI defaults Sales to
invoice view where it does not default Purchase that way. So OBJVIEW is
sent EXPLICITLY here, removing the default from the experiment rather
than inheriting a Purchase-only result.

SCOPE LIMIT, so a pass is not over-read: tax amounts are supplied, not
derived (as in #8), and the party ledger carries no GSTIN and no
STATENAME. This tests the *structural* Sales shape only. It says nothing
about outward-supply GST determination, which is PENDING:018's
unreconciled-state-code problem and stays exactly as open afterwards.

Masters note: CGST and SGST already exist in this company (one tax
ledger serves both input and output tax; the Dr/Cr side distinguishes
them). This adds two masters that do NOT exist — a Sundry Debtors party
and a Sales Accounts ledger. Per #22 and PENDING:009, masters cannot be
reset through the API; these two are permanent. The voucher itself is
deletable via reset_sandbox.py, addressed by its VOUCHERNUMBER.

    python sales_invoice_probe.py            # print the payloads
    python sales_invoice_probe.py --send
    python sales_invoice_probe.py --send --company "Some Other Co"
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

COMPANY = "Coastal Services Ltd"
DATE = "20260801"  # Educational Mode allows the 1st, 2nd and 31st (section 1.1)
NUMBER = "SALES-INVOICE-PROBE-0001"
MARKER = "SALES-INVOICE-PROBE"

PARTY = "Coastal Retail Customer Pvt Ltd"
SALES = "Sales @18%"

# Distinct from every amount already in the sandbox, so a Trial Balance
# delta cannot be confused with an existing voucher (PENDING:009's method).
TAXABLE = Decimal("5000.00")
CGST = Decimal("450.00")
SGST = Decimal("450.00")
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


def build_ledger_read(company: str) -> str:
    """Step 0 existence check — the discipline #22 was missing."""
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = "CAOS Ledger Coll"
    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    tdl = ET.SubElement(desc, "TDL")
    tdlmsg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(
        tdlmsg, "COLLECTION", NAME="CAOS Ledger Coll", ISINITIALIZE="Yes"
    )
    ET.SubElement(coll, "TYPE").text = "Ledger"
    for field in ("Name", "Parent", "TaxType", "GSTDutyHead"):
        ET.SubElement(coll, "NATIVEMETHOD").text = field
    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_ledgers(company: str) -> str:
    """Only the two masters this company lacks. CGST/SGST already exist."""
    env, msg = _import_env(company, "All Masters")

    def ledger(name: str, parent: str) -> None:
        led = ET.SubElement(msg, "LEDGER", NAME=name, ACTION="Create")
        ET.SubElement(led, "NAME").text = name
        ET.SubElement(led, "PARENT").text = parent
        ET.SubElement(led, "OPENINGBALANCE").text = "0"

    ledger(PARTY, "Sundry Debtors")
    ledger(SALES, "Sales Accounts")

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def build_voucher(company: str, number: str = NUMBER) -> str:
    env, msg = _import_env(company, "Vouchers")
    vch = ET.SubElement(
        msg,
        "VOUCHER",
        VCHTYPE="Sales",
        ACTION="Create",
        OBJVIEW="Accounting Voucher View",
    )
    ET.SubElement(vch, "DATE").text = DATE
    ET.SubElement(vch, "EFFECTIVEDATE").text = DATE
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Sales"
    # Supplied only so reset_sandbox.py can address this for cleanup — it
    # SKIPs vouchers with no VOUCHERNUMBER. NOT identity (#10, #14).
    ET.SubElement(vch, "VOUCHERNUMBER").text = number
    ET.SubElement(vch, "PARTYLEDGERNAME").text = PARTY
    ET.SubElement(vch, "NARRATION").text = (
        # ASCII only: a non-ASCII narration that came back mangled would be
        # an encoding artifact confounded with the Sales result.
        f"{MARKER} - not a real transaction, safe to delete"
    )
    ET.SubElement(vch, "REFERENCE").text = MARKER

    def entry(ledger: str, amount: Decimal, debit: bool) -> None:
        e = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(e, "LEDGERNAME").text = ledger
        ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if debit else "No"
        ET.SubElement(e, "AMOUNT").text = str(-amount if debit else amount)

    # Mirror of section 4.3's verified Purchase, signs swapped: Sales
    # debits the party and credits income + output tax.
    entry(PARTY, TOTAL, debit=True)
    entry(SALES, TAXABLE, debit=False)
    entry("CGST", CGST, debit=False)
    entry("SGST", SGST, debit=False)

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
    for tag in ("CREATED", "ALTERED", "IGNORED", "ERRORS", "EXCEPTIONS", "LASTVCHID"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            out[tag] = el.text.strip()
    return out


def line_errors(response: str) -> list[str]:
    """Rule 2 — LINEERROR overrides every counter (#17)."""
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return []
    return [e.text.strip() for e in root.iter("LINEERROR") if e.text]


def ledger_names(response: str) -> set[str]:
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return set()
    names: set[str] = set()
    for led in root.iter("LEDGER"):
        name = led.get("NAME") or led.findtext("NAME")
        if name:
            names.add(name.strip())
    return names


def verify(response: str) -> None:
    vouchers = parse_vouchers(response)
    print_vouchers(vouchers)
    expect = {SALES: TAXABLE, "CGST": CGST, "SGST": SGST, PARTY: TOTAL}
    hits = [v for v in vouchers if v["type"] == "Sales" and v["party"] == PARTY]
    if not hits:
        print(f"\n  No Sales voucher for {PARTY!r} in the Day Book.")
        return
    for v in hits:
        print(f"\n  >>> probe voucher (number={v['number']!r} remote={v['remote_id']})")
        found = {n: abs(a) for n, a in v["entries"]}
        for want, amount in expect.items():
            got = found.get(want)
            if got is None:
                print(f"    MISSING: no {want} entry")
            elif got != amount:
                print(f"    WRONG: {want} is {got}, expected {amount}")
            else:
                print(f"    OK: {want} = {got}")


if __name__ == "__main__":
    company = company_from_argv(sys.argv, COMPANY)

    if "--send" not in sys.argv:
        print("=== ledgers ===")
        print(build_ledgers(company))
        print("\n=== voucher ===")
        print(build_voucher(company))
        print(f"\n(dry run — pass --send to run against {company!r})")
        sys.exit(0)

    print(f"Target company: {company!r}\n")

    print("--- 0. existence check: which ledgers are already here? ---")
    body = run("sales-0-ledger-read", build_ledger_read(company))
    if body is None:
        sys.exit("  no response — halting before any write.")
    present = ledger_names(body)
    for name in (PARTY, SALES, "CGST", "SGST"):
        print(f"  {'PRESENT' if name in present else 'ABSENT':8} {name}")
    if "CGST" not in present or "SGST" not in present:
        sys.exit("  CGST/SGST missing — halting; this probe assumes they exist.")

    print("\n--- 1. create the two missing masters ---")
    body = run("sales-1-ledgers", build_ledgers(company))
    if body is None:
        sys.exit("  no response — halting.")
    print(f"  counts: {counts(body)}")
    errs = line_errors(body)
    for err in errs:
        print(f"  LINEERROR: {err}")
    if errs:
        sys.exit("  master step reported a LINEERROR — halting before the voucher.")

    print("\n--- 2. post the Sales voucher ---")
    body = run("sales-2-post", build_voucher(company))
    if body is None:
        sys.exit("  no response — halting.")
    c = counts(body)
    print(f"  counts: {c}")
    for err in line_errors(body):
        print(f"  LINEERROR: {err}")

    if c.get("CREATED", "0") == "0":
        print(
            "\n  Sales voucher NOT created by the counters. Counters are not\n"
            "  the evidence either way — step 3 reads back to confirm."
        )
    else:
        print("\n  Reported CREATED. Counters prove nothing (#26) — read back.")

    print("\n--- 3. read back (Rule 1) ---")
    body = run("sales-3-readback", build_readback(company))
    if body:
        verify(body)

    print(
        "\n  Cleanup, if it landed:\n"
        f'    python reset_sandbox.py --company "{company}" '
        "--keep-file keep-coastal-services.txt --confirm"
    )
