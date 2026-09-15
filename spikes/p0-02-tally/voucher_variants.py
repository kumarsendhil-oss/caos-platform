"""
P0-02 — Find a voucher shape Tally accepts.

post_voucher.py returned EXCEPTIONS:1, CREATED:0 — Tally rejected the
voucher and gave no detail. The response carries nothing beyond the
counts, and Tally's install-directory log is the scheduler's, not an
integration log. So bisect: post several variants, each with a distinct
voucher number, then read back and see which exist.

Variants run simplest-first, so the first success tells us the minimum
that works and every later failure tells us what broke it.

Hypotheses being tested, in order:
  A. OBJVIEW="Invoice Voucher View" requires inventory entries, which
     this voucher has none of (the company has Maintain Inventory: Yes).
  B. PERSISTEDVIEW is the problem rather than OBJVIEW.
  C. The GST tax ledgers are the problem — a voucher with only party
     and purchase ledger should post if so.
  D. VOUCHERNUMBER conflicts with Tally's own numbering.
  E. Something about the date, despite 1-Aug being an Educational Mode
     allowed day.

    python voucher_variants.py            # print them
    python voucher_variants.py --send     # post all, then read back
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
DATE = "20260801"
PARTY = "Coastal Components Pvt Ltd"
PURCHASE = "Purchase @18%"

TAXABLE = Decimal("18400.00")
CGST = Decimal("1656.00")
SGST = Decimal("1656.00")


def _envelope(company: str) -> tuple[ET.Element, ET.Element]:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"
    body = ET.SubElement(env, "BODY")
    importdata = ET.SubElement(body, "IMPORTDATA")
    reqdesc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(reqdesc, "REPORTNAME").text = "Vouchers"
    sv = ET.SubElement(reqdesc, "STATICVARIABLES")
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    reqdata = ET.SubElement(importdata, "REQUESTDATA")
    msg = ET.SubElement(reqdata, "TALLYMESSAGE")
    msg.set("xmlns:UDF", "TallyUDF")
    return env, msg


def _entry(vch: ET.Element, ledger: str, amount: Decimal, positive: bool) -> None:
    e = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(e, "LEDGERNAME").text = ledger
    ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if positive else "No"
    ET.SubElement(e, "AMOUNT").text = str(-amount if positive else amount)


def build(
    number: str | None,
    *,
    company: str = COMPANY,
    objview: str | None = None,
    persistedview: bool = False,
    with_tax: bool = True,
    party_ledger_name: bool = True,
) -> str:
    env, msg = _envelope(company)

    attrs = {"VCHTYPE": "Purchase", "ACTION": "Create"}
    if objview:
        attrs["OBJVIEW"] = objview
    vch = ET.SubElement(msg, "VOUCHER", **attrs)

    ET.SubElement(vch, "DATE").text = DATE
    ET.SubElement(vch, "EFFECTIVEDATE").text = DATE
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Purchase"
    if number:
        ET.SubElement(vch, "VOUCHERNUMBER").text = number
    if party_ledger_name:
        ET.SubElement(vch, "PARTYLEDGERNAME").text = PARTY
    if persistedview:
        ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"

    total = TAXABLE + (CGST + SGST if with_tax else Decimal("0"))
    _entry(vch, PARTY, total, positive=False)
    _entry(vch, PURCHASE, TAXABLE, positive=True)
    if with_tax:
        _entry(vch, "CGST", CGST, positive=True)
        _entry(vch, "SGST", SGST, positive=True)

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


VARIANTS: list[tuple[str, str, dict]] = [
    ("A-minimal-no-tax", "VAR-A", {"with_tax": False, "objview": None, "persistedview": False}),
    ("B-minimal-with-tax", "VAR-B", {"with_tax": True, "objview": None, "persistedview": False}),
    (
        "C-accounting-objview",
        "VAR-C",
        {"with_tax": True, "objview": "Accounting Voucher View", "persistedview": False},
    ),
    (
        "D-invoice-objview",
        "VAR-D",
        {"with_tax": True, "objview": "Invoice Voucher View", "persistedview": False},
    ),
    (
        "E-invoice-plus-persisted",
        "VAR-E",
        {"with_tax": True, "objview": "Invoice Voucher View", "persistedview": True},
    ),
    ("F-no-voucher-number", None, {"with_tax": True, "objview": None, "persistedview": False}),
    (
        "G-no-partyledgername",
        "VAR-G",
        {"with_tax": True, "objview": None, "persistedview": False, "party_ledger_name": False},
    ),
]


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


def build_readback(company: str = COMPANY) -> str:
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = "CAOS Vch Readback"

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    ET.SubElement(sv, "SVFROMDATE").text = DATE
    ET.SubElement(sv, "SVTODATE").text = DATE

    tdl = ET.SubElement(desc, "TDL")
    tdlmsg = ET.SubElement(tdl, "TDLMESSAGE")
    coll = ET.SubElement(tdlmsg, "COLLECTION", NAME="CAOS Vch Readback", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Voucher"
    ET.SubElement(coll, "FETCH").text = "*"

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def report(response: str) -> None:
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError as exc:
        print(f"  unparseable: {exc}")
        return

    found = []
    for vch in root.iter():
        if vch.tag.upper() != "VOUCHER":
            continue
        num = (vch.findtext("VOUCHERNUMBER") or "").strip()
        entries = [
            (e.findtext("LEDGERNAME") or "").strip()
            for e in vch.iter()
            if e.tag.upper() == "ALLLEDGERENTRIES.LIST"
        ]
        entries = [e for e in entries if e]
        if num or entries:
            found.append((num or "(no number)", entries))

    print(f"\n  Vouchers on {DATE}: {len(found)}")
    for num, entries in found:
        print(f"    {num}: {', '.join(entries) if entries else '(no ledger entries)'}")


if __name__ == "__main__":
    if "--send" not in sys.argv:
        for label, number, kwargs in VARIANTS:
            print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
            print(build(number, **kwargs))
        sys.exit(0)

    results = []
    for label, number, kwargs in VARIANTS:
        print(f"\n--- {label} ---")
        body = run(f"variant-{label}", build(number, **kwargs))
        c = counts(body) if body else {}
        created = c.get("CREATED", "?")
        exc = c.get("EXCEPTIONS", "?")
        results.append((label, created, exc))
        print(f"  CREATED={created} EXCEPTIONS={exc}")

    print(f"\n{'=' * 60}\nSUMMARY\n{'=' * 60}")
    for label, created, exc in results:
        mark = "OK  " if created not in ("0", "?") else "fail"
        print(f"  [{mark}] {label:28} CREATED={created} EXCEPTIONS={exc}")

    print("\n--- read back ---")
    body = run("variants-readback", build_readback())
    if body:
        report(body)
