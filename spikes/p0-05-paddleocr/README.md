# P0-05 — PaddleOCR (PP-StructureV3) Accuracy Validation

**Status:** harness built and mechanically proven against synthetic fixtures (2026-09-17).
**No real client invoice has been processed, and no accuracy claim about ADR 0008 can be made yet.**

ADR 0008 is **Accepted** and stays Accepted. Its own Consequences section names this spike's requirement explicitly:

> PaddleOCR's accuracy should be validated against a representative sample (20-50 real invoices across different vendor formats) before committing further — this is standard practice for evaluating open-source OCR fit, not just a formality, since production accuracy on this specific practice's actual documents is the only number that matters.

That number does not exist yet. This directory is what produces it once the documents are in hand.

## The two-part structure — read this before running anything

This spike is deliberately split, because one half can run today and the other cannot:

| Part | What it is | Runnable now? |
|---|---|---|
| **1. The harness** | `run_extraction.py` + `score_accuracy.py` + the ground-truth format. Generic — works against any folder of invoices | **Yes.** Proven against synthetic fixtures |
| **2. The evaluation** | Running the harness over 20–50 real invoices across vendor formats, and scoring it | **No.** Blocked on real documents |

**A high score on the synthetic fixtures means the plumbing works. It is not an accuracy result** and must never be quoted as one. The fixtures are clean, single-font, machine-rendered PNGs produced by the *same code that writes their ground truth* — they cannot fail in the ways real invoices fail (scan skew, stamps, handwriting, dot-matrix print, unusual column orders, multi-page tables). Treating them as a measurement would be exactly the "sound in theory, unproven in practice" mistake ADR 0008's open item exists to close.

## Setup

Python **3.12** — not 3.14. PaddlePaddle 3.0.0 publishes no cp314 wheel, so this spike keeps its own venv rather than reusing `services/api`'s.

```powershell
# From spikes/p0-05-paddleocr
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`paddlex[ocr]` is a **required** separate install, not a transitive dependency of `paddleocr`. Without it `PPStructureV3()` raises `DependencyError` at construction time, before any document is touched.

Confirm the CPU-only build ADR 0008 specifies:

```powershell
python -c "import paddle; print(paddle.is_compiled_with_cuda())"   # must print False
```

`run_extraction.py` prints this flag on every run for the same reason — so a GPU build can't be used by accident and then reported as if it were the ADR's configuration.

First run downloads ~1GB of PP-StructureV3 model weights to `~/.paddlex/official_models/` (gitignored). Allow several minutes; subsequent runs are cached.

## Usage

```powershell
# 1. Regenerate the synthetic fixtures (already committed; this is for editing them)
python make_synthetic_invoices.py

# 2. Extract — works against ANY folder of invoices
python run_extraction.py --input samples/ --out out/

# 3. Score against ground truth — REDACTED by default
python score_accuracy.py --results out/ --ground-truth samples/ground_truth.json

# Machine-readable report (also redacted — this is the committable artifact)
python score_accuracy.py --results out/ --ground-truth samples/ground_truth.json --json report.json

# Full values, for local debugging only. NEVER commit this output.
python score_accuracy.py --results real-results/ --ground-truth gt.json --unredacted

# Prove the masking works, before any real document is processed
python test_redaction.py
```

## The ground-truth format

One JSON file, keyed by source filename. Money is a **string**, parsed to `Decimal` — never a float (CG5). Dates are ISO-8601 in the fixtures, but the scorer parses several common Indian invoice formats, so hand-written ground truth may use whichever form the document actually shows.

```json
{
  "schema_version": "1",
  "documents": {
    "invoice_001.png": {
      "gstin": "33AABCU9603R1ZX",
      "vendor_name": "Sundaram Office Supplies Pvt Ltd",
      "invoice_number": "SOS/2026/0417",
      "invoice_date": "2026-04-17",
      "subtotal": "7440.00",
      "tax_total": "1339.20",
      "grand_total": "8779.20",
      "line_items": [
        {"description": "A4 Copier Paper 75gsm Ream",
         "quantity": "20", "unit_price": "240.00", "amount": "4800.00"}
      ]
    }
  }
}
```

A field that is genuinely absent from a document should be **omitted**, not set to `null` or `""` — the scorer skips absent fields rather than counting them as misses, so "this invoice has no separate subtotal line" doesn't become a false failure.

## How scoring works, and why it isn't one number

`score_accuracy.py` reports **per field**, because a single aggregate hides the only distinction that matters. "85% accurate" is the same number whether the 15% of failures are GSTINs or line-item descriptions, and those are not remotely the same problem: a wrong GSTIN breaks GST reconciliation outright, while a slightly-off description is cosmetic.

Each field is scored under the tolerance it deserves:

| Field | Tolerance | Why |
|---|---|---|
| `gstin` | Exact (case/space-normalised) | A checksummed statutory identifier. "Close" is wrong |
| `invoice_number` | Exact | Keys duplicate detection (CG7) |
| `invoice_date` | Parsed date equality | `17/04/2026` == `2026-04-17`; format variance is a parsing concern, not an OCR error |
| `vendor_name` | Normalised, **and** exact, reported separately | The gap between the two numbers is itself a finding — it says how much normalisation the intake agent must do |
| amounts | `Decimal`, ±0.01 default (`--tolerance`) | CG5. A 0.01 drift on a total is a reconciliation break, not a rounding curiosity |

Line items are scored on **count first**, then per item on description and amount. Getting 4 of 5 line items is a different failure from getting all 5 with one wrong amount, and the report distinguishes them.

## ⚠ DPDP handling — real client invoices

**Once real documents are provided, they must not be committed to this repo.** This is a genuine difference from the earlier spikes, not boilerplate caution:

- P0-02, P0-06 and P0-07 commit their `runs/` captures because that data is **fictitious** — spike sandboxes, throwaway accounts, a test file called `p0-07-test.txt`.
- Real client invoices are **actual financial records of identifiable persons and businesses**, squarely within the DPDP Act. Committing them to a git remote would place exactly the data ADR 0004 and ADR 0008 exist to protect onto third-party infrastructure — and git history makes it effectively permanent.

The self-hosting rationale in ADR 0008 is only worth anything if the documents stay put. Pushing them to GitHub at the evaluation stage would undo the whole decision at the first step.

**Recommended handling, for confirmation once documents are actually in hand:**

1. Real invoices go in **`real-samples/`** — gitignored, local only, never pushed.
2. Extraction output goes in **`real-results/`** — also gitignored by default.
3. The ground truth for real invoices (`real-samples/ground_truth.json`) is itself sensitive: it contains transcribed GSTINs, vendor names and amounts. Gitignored with the rest.
4. **What gets committed as evidence is the redacted score report** — and redaction is now enforced by the tool rather than left to discipline. See *Redacted by default* below.

**Decided (2026-09-17): committed evidence is redacted or summary-only, never raw identifiers.** This applies the rule the project already uses for tokens and secrets — never in git history, even a private one — to client data, which deserves it at least as much. Points 1–3 above remain recommendations to confirm once documents are in hand.

### Redacted by default

`score_accuracy.py` masks values unless you explicitly opt out. The safe mode is the default and the dangerous one needs a flag, because the failure mode is asymmetric: forgetting to redact a report you then commit is unrecoverable once it is in git history, while forgetting `--unredacted` during local debugging costs you one re-run.

| | Default | `--unredacted` |
|---|---|---|
| Per-field accuracy rates | full | full |
| Pass/fail per field per document | full | full |
| GSTIN | `33***********ZX` | raw |
| Vendor name | `Sun...(32 chars)` | raw |
| Invoice number | `SO*********17` | raw |
| Invoice date | `2026-**-**` | raw |
| Amounts | `<amount redacted>` | raw |
| Committable? | **yes** | **never** |

**The accuracy signal is fully intact under redaction.** What is removed is the ability to reconstruct a client's invoice — not the ability to see which document failed which field.

Diagnostic value is preserved by describing the *error* rather than the values:

- A GSTIN or invoice-number miss reports how many characters differ, at which positions, and whether they are known OCR confusables (`0`/`O`, `1`/`I`, `5`/`S`, `8`/`B`). That directly answers FINDINGS.md's question about whether GSTIN errors are systematic — fixable with a checksum-validated correction pass — or scattered.
- An amount miss reports the delta and direction, not the two figures. Deltas at or below 1.00 are exact, because that is the diagnostic range (0.01 rounding versus 0.05 drift). Larger deltas are bucketed, and the delta is deliberately **not** also reported as a percentage of the expected value: publishing both recovers the original exactly — 66960.00 at 900% is 7440.00. Either alone is harmless; together they are the invoice.

`test_redaction.py` asserts these properties mechanically against the synthetic fixtures: that the redacted JSON contains none of a list of known values, that something was actually masked, that `--unredacted` genuinely differs (a flag that changes nothing is worse than no flag), and that the per-field and per-document signal survives masking intact.

`.gitignore` already covers `real-samples/` and `real-results/`, with the rule kept in this directory so it travels with the data rather than depending on a file three levels up — the gap that caused P0-06 finding #13.

## What is blocked, and on whom

**The harness is done and works.** What it cannot do is obtain its own input.

Required to produce the number ADR 0008 asks for: **20–50 real invoices from the practice, spanning different vendor formats.** Format variety is the actual requirement, not the count — 40 invoices from one vendor would be a worse test than 20 from twenty vendors, because layout variance is the specific thing PP-Structure is being trusted to handle. Worth including, if they exist: at least a few scans rather than born-digital PDFs, and at least one handwritten document, to test the ~1% assumption below.

Only the practice can supply these. They cannot be fabricated, and they cannot be sourced from a public dataset without the result measuring the wrong documents.

## Scope limits, stated up front

- **Not an EasyOCR comparison.** ADR 0008's handwritten fallback path is not implemented here. The spike can only identify *where it would need to trigger*.
- **Not an invoice2data comparison.** The template fast-path is a later optimisation and is out of scope.
- **Not a GPU benchmark.** CPU-only by decision. Timings here say nothing about a GPU deployment.
- **Not a throughput test.** Per-document timing is recorded, but three synthetic pages on one laptop is not a volume measurement.
- **The field extractor is heuristics, deliberately.** Thin enough to see through, so a miss is attributable to OCR or to layout analysis rather than buried in a clever parser. A finding should name which of the two it was.
