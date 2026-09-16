"""
Voucher reads that actually work.

FINDING #11 (resolved 2026-09-16): vouchers must be read with
`EXPORT / TYPE: DATA / ID: Day Book`. The `TYPE: COLLECTION` shape used
for ledgers silently returns zero vouchers when pointed at vouchers —
no error, just nothing.

FINDING #13 (same session): worse, `TYPE: COLLECTION` with `ID: Day Book`
raises a modal GUI dialog in TallyPrime —

    Error in TDL.
    'Collection:Day Book'
    Could not find description!

— which blocks the HTTP listener until a human clicks OK. Repeated
attempts crashed TallyPrime entirely. So this is not merely the wrong
query; it is a request shape that can take the server down.

Ledgers still use COLLECTION (that works). Vouchers use DATA + Day Book.
Do not mix them.

Verified working: `docs/../runs/2026-09-16T02-04-*-vchread-A-data-daybook`
returned both posted vouchers with full ledger entries.
"""

from __future__ import annotations

from decimal import Decimal
from xml.etree import ElementTree as ET

from tally_xml import sanitise


def build_daybook_read(company: str, from_date: str, to_date: str | None = None) -> str:
    """
    The verified-working voucher read.

    Dates are Tally's YYYYMMDD, not ISO — three backends, three formats
    (Zoho uses ISO, the GSP uses MMYYYY).
    """
    env = ET.Element("ENVELOPE")
    header = ET.SubElement(env, "HEADER")
    ET.SubElement(header, "VERSION").text = "1"
    ET.SubElement(header, "TALLYREQUEST").text = "EXPORT"
    ET.SubElement(header, "TYPE").text = "DATA"
    ET.SubElement(header, "ID").text = "Day Book"

    body = ET.SubElement(env, "BODY")
    desc = ET.SubElement(body, "DESC")
    sv = ET.SubElement(desc, "STATICVARIABLES")
    ET.SubElement(sv, "SVEXPORTFORMAT").text = "$$SysName:XML"
    ET.SubElement(sv, "SVCURRENTCOMPANY").text = company
    ET.SubElement(sv, "SVFROMDATE").text = from_date
    ET.SubElement(sv, "SVTODATE").text = to_date or from_date

    ET.indent(env, space="  ")
    return ET.tostring(env, encoding="unicode")


def parse_vouchers(response: str) -> list[dict]:
    """
    Vouchers with their ledger entries, from a Day Book response.

    Only vouchers carrying at least one ledger entry are returned —
    Tally emits placeholder VOUCHER elements that would otherwise be
    counted as real.
    """
    try:
        root = ET.fromstring(sanitise(response))
    except ET.ParseError:
        return []

    out: list[dict] = []
    for vch in root.iter():
        if vch.tag.upper() != "VOUCHER":
            continue

        entries: list[tuple[str, Decimal]] = []
        for e in vch.iter():
            if e.tag.upper() != "ALLLEDGERENTRIES.LIST":
                continue
            name = (e.findtext("LEDGERNAME") or "").strip()
            raw = (e.findtext("AMOUNT") or "").strip()
            if not name or not raw:
                continue
            try:
                entries.append((name, Decimal(raw)))
            except Exception:  # noqa: BLE001 — a malformed amount is itself a finding
                entries.append((name, Decimal("0")))

        if not entries:
            continue

        out.append(
            {
                # Tally discards our VOUCHERNUMBER and assigns its own
                # (finding #10), so REMOTEID/VCHKEY are the stable handles.
                "number": (vch.findtext("VOUCHERNUMBER") or "").strip(),
                "remote_id": vch.get("REMOTEID", ""),
                "vch_key": vch.get("VCHKEY", ""),
                "date": (vch.findtext("DATE") or "").strip(),
                "type": (vch.findtext("VOUCHERTYPENAME") or "").strip(),
                "party": (vch.findtext("PARTYLEDGERNAME") or "").strip(),
                "entries": entries,
            }
        )
    return out


def print_vouchers(vouchers: list[dict]) -> None:
    print(f"  Vouchers: {len(vouchers)}")
    for v in vouchers:
        label = v["number"] or "(no number)"
        print(f"\n  {label}  {v['type']}  {v['date']}  [{v['party']}]")
        for name, amt in v["entries"]:
            print(f"    {name:32} {amt:>12}")
        total = sum(a for _, a in v["entries"])
        flag = "" if total == 0 else "   <-- DOES NOT BALANCE"
        print(f"    {'balance':32} {total:>12}{flag}")
