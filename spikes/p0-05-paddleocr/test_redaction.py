"""Prove the redaction actually masks, against synthetic fixtures only.

Run before any real invoice is ever processed. The point is not that the
masking functions return *something* — it is that no raw identifier
survives into the committed report, which is a property worth asserting
mechanically rather than eyeballing once.

Deliberately uses the synthetic fixtures and synthetic corruptions. No
real client data is involved, or should ever be added here.

    python test_redaction.py          # plain run, prints a summary
    pytest test_redaction.py          # also works
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from score_accuracy import (
    _as_dict,
    _char_diff,
    _mask_date,
    _mask_identifier,
    _mask_name,
    score,
)

HERE = Path(__file__).parent
GT_PATH = HERE / "samples" / "ground_truth.json"
OUT_DIR = HERE / "out"

# Synthetic corruptions, chosen to exercise each described error class.
CORRUPTIONS: dict[str, Any] = {
    "gstin": "33AABCU96O3R1ZX",      # 0 -> O, a classic OCR confusable
    "vendor_name": "Sundaram Ofice Supplies Pvt Ltd",
    "invoice_number": "SOS/2026/O417",
    "invoice_date": "2028-04-17",     # wrong year
    "grand_total": "8779.25",         # 0.05 drift
    "subtotal": "74400.00",           # order-of-magnitude slip
}


def _corrupted_results() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Load the synthetic run and corrupt one document's fields."""
    truth = json.loads(GT_PATH.read_text(encoding="utf-8"))
    results: dict[str, dict[str, Any]] = {}
    for name in truth["documents"]:
        path = OUT_DIR / f"{Path(name).stem}.json"
        results[name] = json.loads(path.read_text(encoding="utf-8"))
    target = "synthetic_001_classic.png"
    results[target]["fields"].update(CORRUPTIONS)
    return truth, results


def test_masking_primitives() -> None:
    """Each mask keeps only what it is supposed to keep."""
    assert _mask_identifier("33AABCU9603R1ZX") == "33***********ZX"
    assert len(_mask_identifier("33AABCU9603R1ZX")) == 15
    assert "AABCU" not in _mask_identifier("33AABCU9603R1ZX")
    assert _mask_name("Sundaram Office Supplies Pvt Ltd") == "Sun...(32 chars)"
    assert "Office" not in _mask_name("Sundaram Office Supplies Pvt Ltd")
    assert _mask_date("2026-04-17") == "2026-**-**"
    assert _mask_date("not a date") == "****-**-**"


def test_char_diff_flags_confusables() -> None:
    """A GSTIN miss is described by position and confusability, not value."""
    diff = _char_diff("33AABCU9603R1ZX", "33AABCU96O3R1ZX")
    assert diff["kind"] == "character_mismatch"
    assert diff["differing_count"] == 1
    assert diff["differing_positions"] == [9]
    assert diff["all_differences_are_confusables"] is True
    length = _char_diff("33AABCU9603R1ZX", "33AABCU9603R1Z")
    assert length["kind"] == "length_mismatch"


def _leaked(blob: str, secrets: list[str]) -> list[str]:
    return [s for s in secrets if s in blob]


def test_redacted_report_leaks_nothing() -> None:
    """The committed artifact must not contain any raw identifier."""
    truth, results = _corrupted_results()
    report = score(truth, results, Decimal("0.01"))
    redacted = json.dumps(_as_dict(report, Decimal("0.01"), redact=True))

    secrets = ["33AABCU9603R1ZX", "33AABCU96O3R1ZX", "Sundaram Office Supplies",
               "SOS/2026/0417", "8779.20", "8779.25", "7440.00", "74400.00",
               "27AAGCM1234P1Z5", "Meridian Logistics",
               # The reconstruction vector: a large exact delta alongside the
               # same delta as a percentage recovers the original figure.
               "66960.00", "900.0000"]
    leaks = _leaked(redacted, secrets)
    assert not leaks, f"redacted report leaked: {leaks}"
    assert redacted.count("***") > 0, "nothing was actually masked"


def test_unredacted_report_does_contain_values() -> None:
    """The opt-out must genuinely differ — otherwise the flag is theatre."""
    truth, results = _corrupted_results()
    report = score(truth, results, Decimal("0.01"))
    raw = json.dumps(_as_dict(report, Decimal("0.01"), redact=False))
    assert "33AABCU96O3R1ZX" in raw
    assert "do not commit" in raw.lower()


def test_accuracy_signal_survives_redaction() -> None:
    """Redaction must not cost the per-field or per-document signal."""
    truth, results = _corrupted_results()
    report = score(truth, results, Decimal("0.01"))
    payload = _as_dict(report, Decimal("0.01"), redact=True)
    assert payload["fields"]["gstin"]["correct"] == 2
    assert payload["fields"]["gstin"]["total"] == 3
    per_doc = payload["per_document"]["synthetic_001_classic.png"]
    assert per_doc["gstin"] is False
    assert per_doc["tax_total"] is True
    delta = payload["fields"]["grand_total"]["misses"][0]["detail"]
    assert delta["abs_delta"] == "0.05", "small deltas stay exact — that is the diagnostic"
    assert "pct_of_expected" not in delta, "percentage + delta reconstructs the value"
    slip = payload["fields"]["subtotal"]["misses"][0]["detail"]
    assert slip["order_of_magnitude_slip"] is True
    assert slip["abs_delta"] == ">10000", "large deltas are bucketed, not exact"


def main() -> None:
    tests = [
        test_masking_primitives,
        test_char_diff_flags_confusables,
        test_redacted_report_leaks_nothing,
        test_unredacted_report_does_contain_values,
        test_accuracy_signal_survives_redaction,
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n  {len(tests)} passed (synthetic fixtures only — no real data)")


if __name__ == "__main__":
    main()
