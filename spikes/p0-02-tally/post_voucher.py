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
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _runner import run  # noqa: E402
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
    """Read vouchers back — the only reliable check that the split landed."""
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = "CAOS Voucher Dump"

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    ET.SubElement(sv, "SVFROMDATE").text = VOUCHER_DATE
    ET.SubElement(sv, "SVTODATE").text = VOUCHER_DATE

    tdl = ET.SubElement(desc, "TDL")
    tdlmsg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(tdlmsg, "COLLECTION", NAME="CAOS Voucher Dump", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Voucher"
    ET.SubElement(coll, "FETCH").text = "*"

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


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
    """Did the tax actually land on the right ledgers, in the right amounts?"""
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        print(f"  Could not parse voucher read-back: {exc}")
        return

    vouchers = [e for e in root.iter() if e.tag.upper() == "VOUCHER"]
    print(f"  Vouchers found on {VOUCHER_DATE}: {len(vouchers)}")

    for i, vch in enumerate(vouchers, 1):
        number = vch.findtext("VOUCHERNUMBER") or "(no number)"
        print(f"\n  Voucher {i}: {number}")
        entries: list[tuple[str, Decimal]] = []
        for entry in vch.iter():
            if entry.tag.upper() != "ALLLEDGERENTRIES.LIST":
                continue
            name = (entry.findtext("LEDGERNAME") or "").strip()
            raw = (entry.findtext("AMOUNT") or "").strip()
            if not name or not raw:
                continue
            try:
                entries.append((name, Decimal(raw)))
            except Exception:  # noqa: BLE001 — a malformed amount is itself the finding
                print(f"    {name}: unparseable amount {raw!r}")

        for name, amt in entries:
            print(f"    {name:32} {amt:>12}")

        total = sum((a for _, a in entries), Decimal("0"))
        print(f"    {'balance (should be 0)':32} {total:>12}")

        found = {n: a for n, a in entries}
        for want_name, want_abs in (("CGST", CGST), ("SGST", SGST)):
            got = found.get(want_name)
            if got is None:
                print(f"    MISSING: no {want_name} entry — the split did not land")
            elif abs(got) != want_abs:
                print(f"    WRONG: {want_name} is {abs(got)}, expected {want_abs}")


if __name__ == "__main__":
    if "--send" not in sys.argv:
        print("=== reset duty heads ===")
        print(build_reset_duty_heads())
        print("\n=== voucher ===")
        print(build_voucher())
        print("\n(dry run — pass --send to run the full sequence)")
        sys.exit(0)

    print("--- 0. reset CGST/SGST duty heads (probe left CGST empty) ---")
    run("voucher-0-reset-duty-heads", build_reset_duty_heads())

    print("\n--- 1. post the voucher ---")
    body = run("voucher-1-post", build_voucher())
    print(f"  counts: {_counts(body) if body else 'no response'}")

    print("\n--- 2. read it back and verify the split ---")
    body = run("voucher-2-readback", build_read_daybook())
    if body:
        verify_split(body)

    print("\n--- 3. post the IDENTICAL voucher again (CG7) ---")
    body = run("voucher-3-duplicate", build_voucher())
    counts = _counts(body) if body else {}
    print(f"  counts: {counts}")

    print("\n--- 4. read back again — one voucher or two? ---")
    body = run("voucher-4-readback-after-duplicate", build_read_daybook())
    if body:
        verify_split(body)

    print(f"\n{'=' * 64}")
    print("CG7: if step 4 shows TWO vouchers, Tally does NOT prevent")
    print("duplicates and ADR 0001 stands. If it shows ONE, or step 3")
    print("reported errors, ADR 0001's claim is wrong and CG7's")
    print("justification needs revisiting.")
    print("=" * 64)
