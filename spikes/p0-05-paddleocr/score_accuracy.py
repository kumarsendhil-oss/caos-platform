"""Score extraction output against manually-verified ground truth.

Reports a **per-field breakdown**, deliberately, not one aggregate number.
A single "85% accurate" figure hides the only thing that matters here:
whether the failures cluster on GSTIN — which must be exact, because it
keys the whole GST reconciliation — or on a field where a near miss is
recoverable. Those two outcomes have the same aggregate score and
completely different consequences for ADR 0008.

Each field is scored under the tolerance that field actually deserves:

    gstin           exact, after whitespace/case normalisation. A GSTIN is a
                    checksummed identifier; "close" is wrong.
    invoice_number  exact, after whitespace/case normalisation.
    invoice_date    compared as parsed dates, so 17/04/2026 == 2026-04-17.
                    Format variation is a parsing concern, not an OCR error.
    vendor_name     normalised (case, punctuation, collapsed whitespace, and
                    common suffixes like "Pvt Ltd"). Reported BOTH ways —
                    exact and normalised — because the gap between them is
                    itself the finding.
    amounts         Decimal comparison within a tolerance (default 0.01).
                    Never float: CG5, and a 0.01 drift on a total is a real
                    reconciliation break, not a rounding curiosity.

Line items are scored on count first, then per-item on description and
amount, matched in order. Getting 4 of 5 items is a materially different
failure from getting 5 items with one wrong amount, so both are reported.

REDACTION — this output is **redacted by default**.

Against real client invoices, an unredacted miss list quotes real GSTINs,
real vendor names and real amounts. That is the exact class of data ADR
0004 and ADR 0008 exist to keep off third-party infrastructure, and git
history makes a mistake permanent — the same rule this project already
applies to tokens and secrets, which are never committed even to a
private remote.

So the safe mode is the default and the dangerous one is opt-in:
`--unredacted` is for local debugging against `real-results/` and its
output must never be committed. Redacted mode still shows pass/fail per
field per document, so the accuracy signal is fully intact; what it
removes is the ability to reconstruct a client's invoice from the report.

Diagnostic value is preserved by describing the *error*, not the values:
a GSTIN miss reports how many characters differ, at which positions, and
whether they are known OCR confusables (0/O, 1/I, 5/S, 8/B); an amount
miss reports the delta rather than the two figures.

Usage:
    python score_accuracy.py --results out/ --ground-truth samples/ground_truth.json
    python score_accuracy.py --results out/ --ground-truth gt.json --json report.json
    python score_accuracy.py --results real-results/ --ground-truth gt.json --unredacted
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCALAR_FIELDS = (
    "gstin",
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "subtotal",
    "tax_total",
    "grand_total",
)
AMOUNT_FIELDS = frozenset({"subtotal", "tax_total", "grand_total"})
EXACT_FIELDS = frozenset({"gstin", "invoice_number"})

_VENDOR_SUFFIXES = (
    "private limited", "pvt ltd", "pvt. ltd.", "p ltd", "limited", "ltd",
    "llp", "inc", "co", "company", "services", "and sons",
)
_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d %b %Y", "%d %B %Y",
                 "%d-%b-%Y", "%b %d, %Y")

# Character pairs OCR habitually confuses. Reported by position on a GSTIN
# miss because a *systematic* confusion is fixable with a checksum-validated
# correction pass, while scattered errors are not — that distinction is one
# of FINDINGS.md's secondary questions, and it survives redaction intact.
_CONFUSABLES = frozenset({
    frozenset("0O"), frozenset("1I"), frozenset("1L"), frozenset("IL"),
    frozenset("5S"), frozenset("8B"), frozenset("2Z"), frozenset("6G"),
})


@dataclass
class FieldTally:
    """Correct/total for one field, with the misses kept for inspection."""

    correct: int = 0
    total: int = 0
    misses: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return (self.correct / self.total) if self.total else 0.0

    def record(self, ok: bool, doc: str, expected: Any, got: Any) -> None:
        self.total += 1
        if ok:
            self.correct += 1
        else:
            self.misses.append({"document": doc, "expected": expected, "got": got})


def _norm_text(value: str) -> str:
    """Case-fold, strip accents and punctuation, collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = re.sub(r"[^\w\s]", " ", ascii_only.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _norm_vendor(value: str) -> str:
    """Vendor names vary in legal suffix and punctuation; strip both."""
    text = _norm_text(value)
    for suffix in sorted(_VENDOR_SUFFIXES, key=len, reverse=True):
        if text.endswith(" " + suffix):
            text = text[: -(len(suffix) + 1)].strip()
    return text


def _parse_date(value: str) -> date | None:
    """Accept any of the formats an Indian invoice plausibly uses."""
    from datetime import datetime

    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> Decimal | None:
    """Decimal from string (CG5). Tolerates thousands separators and ₹."""
    text = re.sub(r"[^\d.\-]", "", str(value).replace(",", ""))
    if not text or text in {"-", "."}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _amounts_match(expected: str, got: Any, tolerance: Decimal) -> bool:
    exp, act = _parse_amount(expected), _parse_amount(got) if got is not None else None
    if exp is None or act is None:
        return False
    return abs(exp - act) <= tolerance


def _scalar_match(name: str, expected: Any, got: Any, tolerance: Decimal) -> bool:
    """Apply the tolerance appropriate to this specific field."""
    if got is None or expected is None:
        return False
    if name in AMOUNT_FIELDS:
        return _amounts_match(str(expected), got, tolerance)
    if name == "invoice_date":
        exp_d, got_d = _parse_date(str(expected)), _parse_date(str(got))
        return exp_d is not None and exp_d == got_d
    if name in EXACT_FIELDS:
        return str(expected).strip().upper() == str(got).strip().upper()
    return _norm_vendor(str(expected)) == _norm_vendor(str(got))


def _score_line_items(
    expected: list[dict[str, Any]],
    got: list[dict[str, Any]],
    tolerance: Decimal,
) -> dict[str, Any]:
    """Count first, then per-item description and amount, matched in order."""
    count_ok = len(expected) == len(got)
    desc_ok = amt_ok = 0
    compared = min(len(expected), len(got))
    for exp, act in zip(expected[:compared], got[:compared], strict=False):
        exp_desc = _norm_text(str(exp.get("description", "")))
        if exp_desc and exp_desc == _norm_text(str(act.get("description", ""))):
            desc_ok += 1
        if _amounts_match(str(exp.get("amount", "")), act.get("amount"), tolerance):
            amt_ok += 1
    return {
        "expected_count": len(expected),
        "extracted_count": len(got),
        "count_correct": count_ok,
        "compared": compared,
        "description_correct": desc_ok,
        "amount_correct": amt_ok,
    }


def _mask_identifier(value: str, keep_head: int = 2, keep_tail: int = 2) -> str:
    """Length-preserving mask keeping the ends: 33AABCU9603R1ZX -> 33***********ZX.

    Length is preserved because a GSTIN's length is fixed and public (15),
    so it reveals nothing, while a truncated mask would hide the useful
    fact that the extractor returned the wrong number of characters.
    """
    text = str(value).strip()
    if len(text) <= keep_head + keep_tail:
        return "*" * len(text)
    return text[:keep_head] + "*" * (len(text) - keep_head - keep_tail) + text[-keep_tail:]


def _mask_name(value: str, keep: int = 3) -> str:
    """Vendor names are directly identifying: Sundaram... -> 'Sun...(31 chars)'."""
    text = str(value).strip()
    head = text[:keep]
    return f"{head}...({len(text)} chars)"


def _mask_date(value: str) -> str:
    """Keep the year, mask month and day.

    A year alone does not identify a transaction; a full date plus an
    amount narrows it considerably. Year is retained because 'the model
    read 2026 as 2028' and 'the model read the day wrong' are different
    problems worth telling apart.
    """
    parsed = _parse_date(str(value))
    return f"{parsed.year}-**-**" if parsed else "****-**-**"


def _char_diff(expected: str, got: str) -> dict[str, Any]:
    """Describe an exact-field miss without revealing either value."""
    exp, act = str(expected).strip().upper(), str(got).strip().upper()
    if len(exp) != len(act):
        return {"kind": "length_mismatch", "expected_len": len(exp), "got_len": len(act)}
    positions = [i for i, (a, b) in enumerate(zip(exp, act, strict=False)) if a != b]
    confusable = [
        i for i in positions if frozenset({exp[i], act[i]}) in _CONFUSABLES
    ]
    return {
        "kind": "character_mismatch",
        "differing_positions": positions,
        "differing_count": len(positions),
        "ocr_confusable_positions": confusable,
        "all_differences_are_confusables": bool(positions) and len(confusable) == len(positions),
    }


def _amount_delta(expected: str, got: Any) -> dict[str, Any]:
    """Describe an amount miss as a delta, not as the two figures.

    The delta is what diagnoses the error class — a 0.01 rounding drift, a
    transposed digit, a factor-of-ten magnitude slip — and unlike the
    figures themselves it does not disclose what the client was invoiced.

    Two deliberate limits, because a delta is not automatically safe:

    - The percentage is NOT reported. Publishing both an absolute delta
      and that delta as a percentage of the expected value reconstructs
      the expected value exactly (66960.00 at 900% => 7440.00). Either
      alone is harmless; together they are the invoice.
    - Only small deltas are given exactly. Below 1.00 the precise figure
      is the whole diagnostic — 0.01 rounding versus 0.05 drift — and
      reveals nothing about the invoice's size. Above that it is bucketed,
      since a large exact delta combined with a magnitude flag narrows the
      original value more than the diagnosis is worth.
    """
    exp, act = _parse_amount(str(expected)), _parse_amount(got) if got is not None else None
    if exp is None:
        return {"kind": "unparseable_ground_truth"}
    if act is None:
        return {"kind": "not_extracted"}
    delta = act - exp
    magnitude = (abs(delta) / abs(exp) * 100) > 500 if exp else False
    return {
        "kind": "value_mismatch",
        "direction": "over" if delta > 0 else "under",
        "abs_delta": _bucket_delta(abs(delta)),
        "order_of_magnitude_slip": magnitude,
    }


def _bucket_delta(abs_delta: Decimal) -> str:
    """Exact below 1.00 (the diagnostic range), bucketed above it."""
    if abs_delta <= Decimal("1.00"):
        return str(abs_delta)
    for bound in (Decimal("100"), Decimal("10000")):
        if abs_delta <= bound:
            return f"<={bound.to_integral_value()}"
    return ">10000"


def _describe_miss(name: str, expected: Any, got: Any, redact: bool) -> dict[str, Any]:
    """One miss, as either raw values or a redacted error description."""
    if not redact:
        return {"expected": expected, "got": got}
    if got is None:
        base: dict[str, Any] = {"detail": {"kind": "not_extracted"}}
    elif name in AMOUNT_FIELDS:
        base = {"detail": _amount_delta(str(expected), got)}
    elif name in EXACT_FIELDS:
        base = {"detail": _char_diff(str(expected), str(got))}
    else:
        base = {"detail": {"kind": "value_mismatch"}}
    base["expected_masked"] = _mask_value(name, expected)
    base["got_masked"] = _mask_value(name, got) if got is not None else None
    return base


def _mask_value(name: str, value: Any) -> str:
    """Apply the masking rule appropriate to the field."""
    if value is None:
        return "<none>"
    if name == "gstin" or name == "invoice_number":
        return _mask_identifier(str(value))
    if name == "vendor_name":
        return _mask_name(str(value))
    if name == "invoice_date":
        return _mask_date(str(value))
    if name in AMOUNT_FIELDS:
        return "<amount redacted>"
    return "<redacted>"


def _load_results(results_dir: Path) -> dict[str, dict[str, Any]]:
    """Index extraction JSON by the source filename it records."""
    indexed: dict[str, dict[str, Any]] = {}
    for path in sorted(results_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = payload.get("source_file") or path.stem
        indexed[key] = payload
    return indexed


@dataclass
class Report:
    """Accumulated scores. Aggregate exists, but is never the headline."""

    fields: dict[str, FieldTally] = field(default_factory=dict)
    line_items: list[dict[str, Any]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    vendor_exact: FieldTally = field(default_factory=FieldTally)
    # document -> field -> passed. Survives redaction untouched: it is the
    # accuracy signal, and it identifies nobody.
    per_document: dict[str, dict[str, bool]] = field(default_factory=dict)

    def tally(self, name: str) -> FieldTally:
        return self.fields.setdefault(name, FieldTally())


def score(
    ground_truth: dict[str, Any],
    results: dict[str, dict[str, Any]],
    tolerance: Decimal,
) -> Report:
    """Compare every ground-truth document against its extraction."""
    report = Report()
    for filename, truth in ground_truth.get("documents", {}).items():
        extracted = results.get(filename)
        if extracted is None:
            report.missing.append(filename)
            continue
        got_fields = extracted.get("fields", {})
        for name in SCALAR_FIELDS:
            expected = truth.get(name)
            if expected is None:
                continue
            got = got_fields.get(name)
            ok = _scalar_match(name, expected, got, tolerance)
            report.tally(name).record(ok, filename, expected, got)
            report.per_document.setdefault(filename, {})[name] = ok
            if name == "vendor_name":
                exact = got is not None and str(expected).strip() == str(got).strip()
                report.vendor_exact.record(exact, filename, expected, got)
        item_score = _score_line_items(
            truth.get("line_items", []), extracted.get("line_items", []), tolerance
        )
        item_score["document"] = filename
        report.line_items.append(item_score)
    return report


def _print_fields(report: Report) -> None:
    print("\n  Field-level accuracy (per field, not aggregated)")
    print(f"  {'field':<16} {'correct':>9} {'total':>7} {'rate':>8}   tolerance")
    print(f"  {'-' * 16} {'-' * 9} {'-' * 7} {'-' * 8}   {'-' * 24}")
    notes = {
        "gstin": "exact (critical)",
        "invoice_number": "exact",
        "invoice_date": "parsed date equality",
        "vendor_name": "normalised",
        "subtotal": "Decimal +/- tol",
        "tax_total": "Decimal +/- tol",
        "grand_total": "Decimal +/- tol",
    }
    for name in SCALAR_FIELDS:
        t = report.fields.get(name)
        if t is None or t.total == 0:
            print(f"  {name:<16} {'-':>9} {'-':>7} {'not in GT':>8}")
            continue
        print(f"  {name:<16} {t.correct:>9} {t.total:>7} {t.rate:>7.1%}   {notes.get(name, '')}")
    ve = report.vendor_exact
    if ve.total:
        print(f"\n  vendor_name, exact-string: {ve.correct}/{ve.total} ({ve.rate:.1%}) "
              f"— the gap vs. normalised is itself a finding")


def _print_line_items(report: Report) -> None:
    if not report.line_items:
        return
    print("\n  Line-item extraction")
    docs_ok = sum(1 for d in report.line_items if d["count_correct"])
    print(f"  correct item COUNT: {docs_ok}/{len(report.line_items)} documents")
    tot_cmp = sum(d["compared"] for d in report.line_items)
    tot_desc = sum(d["description_correct"] for d in report.line_items)
    tot_amt = sum(d["amount_correct"] for d in report.line_items)
    if tot_cmp:
        print(f"  description correct: {tot_desc}/{tot_cmp} ({tot_desc / tot_cmp:.1%}) "
              f"of items compared")
        print(f"  amount correct:      {tot_amt}/{tot_cmp} ({tot_amt / tot_cmp:.1%}) "
              f"of items compared")
    for d in report.line_items:
        flag = " " if d["count_correct"] else "!"
        print(f"   {flag} {d['document']}: expected {d['expected_count']}, "
              f"got {d['extracted_count']}; desc {d['description_correct']}/{d['compared']}, "
              f"amt {d['amount_correct']}/{d['compared']}")


def _print_grid(report: Report) -> None:
    """Pass/fail per field per document — the accuracy signal, unredacted.

    This grid is identical in both modes. It carries no values, so there
    is nothing in it to leak, and it is what makes redacted mode still
    useful: you can see exactly which document failed which field.
    """
    if not report.per_document:
        return
    abbrev = {
        "gstin": "gstin", "vendor_name": "vendor", "invoice_number": "inv#",
        "invoice_date": "date", "subtotal": "subtot", "tax_total": "tax",
        "grand_total": "total",
    }
    print("\n  Pass/fail by document")
    header = "  ".join(f"{abbrev[n]:>6}" for n in SCALAR_FIELDS)
    print(f"  {'document':<34} {header}")
    for doc, results in report.per_document.items():
        cells = "  ".join(
            f"{('ok' if results.get(n) else 'FAIL' if n in results else '-'):>6}"
            for n in SCALAR_FIELDS
        )
        print(f"  {doc[:34]:<34} {cells}")


def _print_misses(report: Report, limit: int, redact: bool) -> None:
    misses = [(n, m) for n in SCALAR_FIELDS
              for m in report.fields.get(n, FieldTally()).misses]
    if not misses:
        print("\n  No field misses.")
        return
    label = "masked" if redact else "RAW VALUES"
    print(f"\n  Misses ({len(misses)}) — {label}")
    for name, miss in misses[:limit]:
        described = _describe_miss(name, miss["expected"], miss["got"], redact)
        print(f"   {name:<16} {miss['document']}")
        if redact:
            print(f"     expected: {described['expected_masked']}")
            print(f"     got:      {described['got_masked']}")
            print(f"     detail:   {described['detail']}")
        else:
            print(f"     expected: {described['expected']!r}")
            print(f"     got:      {described['got']!r}")
    if len(misses) > limit:
        print(f"   … and {len(misses) - limit} more (use --json for the full list)")


def _as_dict(report: Report, tolerance: Decimal, redact: bool) -> dict[str, Any]:
    return {
        "tolerance": str(tolerance),
        "redacted": redact,
        "redaction_note": (
            "Values masked; misses describe the error, not the data. Safe to commit."
            if redact
            else "CONTAINS RAW EXTRACTED VALUES — local debugging only, do not commit."
        ),
        "per_document": report.per_document,
        "fields": {
            name: {
                "correct": t.correct,
                "total": t.total,
                "rate": round(t.rate, 4),
                "misses": [
                    {"document": m["document"],
                     **_describe_miss(name, m["expected"], m["got"], redact)}
                    for m in t.misses
                ],
            }
            for name, t in report.fields.items()
        },
        "vendor_name_exact": {
            "correct": report.vendor_exact.correct,
            "total": report.vendor_exact.total,
            "rate": round(report.vendor_exact.rate, 4),
        },
        "line_items": report.line_items,
        "missing_results": report.missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Score OCR extraction against ground truth.")
    parser.add_argument("--results", type=Path, required=True, help="dir of extraction JSON")
    parser.add_argument("--ground-truth", type=Path, required=True, help="ground_truth.json")
    parser.add_argument("--tolerance", default="0.01", help="amount tolerance (Decimal)")
    parser.add_argument("--json", type=Path, default=None, help="also write the report as JSON")
    parser.add_argument("--max-misses", type=int, default=20)
    parser.add_argument(
        "--unredacted",
        action="store_true",
        help="show raw expected/extracted values. LOCAL DEBUGGING ONLY — output "
             "contains real GSTINs, vendor names and amounts and must never be committed.",
    )
    args = parser.parse_args()

    redact = not args.unredacted
    tolerance = Decimal(args.tolerance)
    truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    results = _load_results(args.results)
    report = score(truth, results, tolerance)

    if redact:
        print("\n  mode: REDACTED (default) — values masked, safe to commit as evidence")
    else:
        print("\n  mode: UNREDACTED — !! raw client values below. Local only. DO NOT COMMIT.")
    print(f"  ground truth: {len(truth.get('documents', {}))} documents"
          f"   extraction results: {len(results)}")
    if report.missing:
        print(f"  !! no extraction output for {len(report.missing)}: "
              f"{', '.join(report.missing[:5])}")
    _print_fields(report)
    _print_grid(report)
    _print_line_items(report)
    _print_misses(report, args.max_misses, redact)

    if args.json:
        args.json.write_text(
            json.dumps(_as_dict(report, tolerance, redact), indent=2), encoding="utf-8"
        )
        print(f"\n  wrote {args.json}"
              f"{'' if redact else '   !! UNREDACTED — do not commit this file'}")
    print()


if __name__ == "__main__":
    main()
