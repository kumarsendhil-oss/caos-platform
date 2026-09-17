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

Usage:
    python score_accuracy.py --results out/ --ground-truth samples/ground_truth.json
    python score_accuracy.py --results out/ --ground-truth gt.json --json report.json
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
            report.tally(name).record(
                _scalar_match(name, expected, got, tolerance), filename, expected, got
            )
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


def _print_misses(report: Report, limit: int) -> None:
    misses = [(n, m) for n in SCALAR_FIELDS
              for m in report.fields.get(n, FieldTally()).misses]
    if not misses:
        print("\n  No field misses.")
        return
    print(f"\n  Misses ({len(misses)}) — expected vs. extracted")
    for name, miss in misses[:limit]:
        print(f"   {name:<16} {miss['document']}")
        print(f"     expected: {miss['expected']!r}")
        print(f"     got:      {miss['got']!r}")
    if len(misses) > limit:
        print(f"   … and {len(misses) - limit} more (use --json for the full list)")


def _as_dict(report: Report, tolerance: Decimal) -> dict[str, Any]:
    return {
        "tolerance": str(tolerance),
        "fields": {
            name: {
                "correct": t.correct,
                "total": t.total,
                "rate": round(t.rate, 4),
                "misses": t.misses,
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
    args = parser.parse_args()

    tolerance = Decimal(args.tolerance)
    truth = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    results = _load_results(args.results)
    report = score(truth, results, tolerance)

    print(f"\n  ground truth: {len(truth.get('documents', {}))} documents"
          f"   extraction results: {len(results)}")
    if report.missing:
        print(f"  !! no extraction output for {len(report.missing)}: "
              f"{', '.join(report.missing[:5])}")
    _print_fields(report)
    _print_line_items(report)
    _print_misses(report, args.max_misses)

    if args.json:
        args.json.write_text(json.dumps(_as_dict(report, tolerance), indent=2), encoding="utf-8")
        print(f"\n  wrote {args.json}")
    print()


if __name__ == "__main__":
    main()
