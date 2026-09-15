"""
Tally XML payload builders — P0-02 spike artifact.

These are the exact request envelopes TallyAdapter's stubbed methods
(PENDING:001, PENDING:002) will send. Built against Tally Solutions' own
documented envelope structure so they can be pasted into the TallyPrime
API Explorer and validated BEFORE any live client data or resolved
port-9000 reachability (per ADR 0001 / TC-01b).

Run this file to print each payload:  python tally_payloads.py

IMPORTANT — what this spike does and does not establish:
  - It DOES pin down the request shapes for extract + post.
  - It does NOT validate them. Nothing here has been sent to a real
    TallyPrime instance or the API Explorer. Every payload below is
    UNVERIFIED until someone runs it through the Explorer and pastes
    back the response.
  - It does NOT resolve port-9000 reachability on the practice's hosted
    instance. That remains an open question for the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from xml.etree import ElementTree as ET

# Tally's date format in STATICVARIABLES is YYYYMMDD.
TALLY_DATE_FMT = "%Y%m%d"


def _pretty(elem: ET.Element) -> str:
    ET.indent(elem, space="  ")
    return ET.tostring(elem, encoding="unicode")


# --------------------------------------------------------------------------
# EXPORT — reads (TC-02 / PENDING:001)
# --------------------------------------------------------------------------

def build_export_collection(
    collection_id: str,
    company: str,
    from_date: str,
    to_date: str,
) -> str:
    """
    Generic Collection export — the shape behind extract_purchase_register,
    extract_sales_register and extract_bank_book.

    collection_id is the TDL report/collection name. Candidates to try in
    the API Explorer (NOT yet confirmed which returns the register shape
    we want):
        "Purchase Register", "Sales Register", "Bank Book", "DayBook"
    """
    env = ET.Element("ENVELOPE")

    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "COLLECTION"
    ET.SubElement(header, "ID").text = collection_id

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    ET.SubElement(sv, "SVFROMDATE").text = from_date
    ET.SubElement(sv, "SVTODATE").text = to_date

    return _pretty(env)


def build_export_ledgers(company: str) -> str:
    """
    Ledger master list — feeds BK-02's fuzzy vendor-to-ledger matching.
    Uses an inline TDL collection so we get exactly the fields we need
    rather than Tally's full default ledger dump.
    """
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
    coll = ET.SubElement(tdlmsg, "COLLECTION", NAME="CAOS Ledger Coll", ISINITIALIZE="Yes")
    ET.SubElement(coll, "TYPE").text = "Ledger"
    for method in ("Name", "Parent", "PartyGSTIN", "OpeningBalance"):
        ET.SubElement(coll, "NATIVEMETHOD").text = method

    return _pretty(env)


# --------------------------------------------------------------------------
# IMPORT — writes (TC-04 / PENDING:002)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class PurchaseVoucher:
    """Minimal purchase voucher. Mirrors BooksConnector.DraftEntry."""

    date: str               # YYYYMMDD
    voucher_number: str
    party_ledger: str       # must already exist in Tally (BK-03 creates via task)
    purchase_ledger: str    # e.g. "Purchase @18%"
    amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    narration: str = ""


def build_import_purchase_voucher(v: PurchaseVoucher, company: str) -> str:
    """
    Voucher import — the shape behind post_entry.

    Tally's ledger-entry sign convention: ISDEEMEDPOSITIVE="Yes" with a
    negative AMOUNT is a debit; "No" with a positive AMOUNT is a credit.
    For a purchase: debit the expense + tax ledgers, credit the party.
    """
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
    vch = ET.SubElement(msg, "VOUCHER", VCHTYPE="Purchase", ACTION="Create", OBJVIEW="Invoice Voucher View")

    ET.SubElement(vch, "DATE").text = v.date
    ET.SubElement(vch, "EFFECTIVEDATE").text = v.date
    ET.SubElement(vch, "VOUCHERTYPENAME").text = "Purchase"
    ET.SubElement(vch, "VOUCHERNUMBER").text = v.voucher_number
    ET.SubElement(vch, "PARTYLEDGERNAME").text = v.party_ledger
    ET.SubElement(vch, "PERSISTEDVIEW").text = "Invoice Voucher View"
    if v.narration:
        ET.SubElement(vch, "NARRATION").text = v.narration

    # Credit the party for the invoice total (positive, ISDEEMEDPOSITIVE No).
    total = v.amount + v.cgst + v.sgst + v.igst
    party = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
    ET.SubElement(party, "LEDGERNAME").text = v.party_ledger
    ET.SubElement(party, "ISDEEMEDPOSITIVE").text = "No"
    ET.SubElement(party, "AMOUNT").text = str(total)

    # Debit the purchase ledger and each applicable tax ledger (negative).
    debits: list[tuple[str, Decimal]] = [(v.purchase_ledger, v.amount)]
    if v.cgst:
        debits.append(("CGST", v.cgst))
    if v.sgst:
        debits.append(("SGST", v.sgst))
    if v.igst:
        debits.append(("IGST", v.igst))

    for ledger_name, amt in debits:
        entry = ET.SubElement(vch, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(entry, "LEDGERNAME").text = ledger_name
        ET.SubElement(entry, "ISDEEMEDPOSITIVE").text = "Yes"
        ET.SubElement(entry, "AMOUNT").text = str(-amt)

    return _pretty(env)


# --------------------------------------------------------------------------

if __name__ == "__main__":
    COMPANY = "Coastal Test Traders"  # synthetic, per Testing Strategy §4

    blocks: list[tuple[str, str]] = [
        (
            "1. EXPORT — Purchase Register (TC-02)",
            build_export_collection("Purchase Register", COMPANY, "20260801", "20260831"),
        ),
        (
            "2. EXPORT — Ledger masters, for BK-02 vendor matching",
            build_export_ledgers(COMPANY),
        ),
        (
            "3. IMPORT — Purchase voucher, intra-state CGST+SGST (TC-04)",
            build_import_purchase_voucher(
                PurchaseVoucher(
                    date="20260815",
                    voucher_number="TEST-INV-0001",
                    party_ledger="Coastal Components Pvt Ltd",
                    purchase_ledger="Purchase @18%",
                    amount=Decimal("18400.00"),
                    cgst=Decimal("1656.00"),
                    sgst=Decimal("1656.00"),
                    igst=Decimal("0.00"),
                    narration="CAOS spike — synthetic test voucher",
                ),
                COMPANY,
            ),
        ),
    ]

    for title, payload in blocks:
        print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
        print(payload)
