# ADR 0008 — Self-Hosted OCR Engine: PaddleOCR (PP-StructureV3)

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

ADR 0004 established the platform as a thin layer over Tally/Dropbox to narrow the DPDP Act surface, but left the OCR/LLM vendor decision open. Given DPDP Act stringency, the decision was made to self-host OCR rather than send client financial documents to a third-party cloud OCR/LLM API. Documents are confirmed to be ~99% printed PDFs (mostly clean invoices) with ~1% handwritten (per discovery), and extraction needs to cover structured fields (GSTIN, vendor, amounts, dates) and tabular line items, not just raw text.

## Decision

Use PaddleOCR with the PP-StructureV3 module as the primary, self-hosted OCR/extraction engine. PP-Structure provides built-in layout analysis, table recognition, and key-value extraction — directly relevant to invoice line-item extraction, which is the hardest part of this pipeline and not something raw OCR text output handles well. Run CPU-only initially, given document volume is moderate and processing is already asynchronous (ADR 0003) with no real-time latency requirement — GPU is a scale-up option, not a day-one cost. Two complementary pieces, not primary engines:

- EasyOCR as a secondary path specifically for the ~1% handwritten documents, where PaddleOCR is weaker.
- invoice2data (template- based) as a fast-path optimization for previously-seen vendor formats over time — ties into the existing confidence-scoring design (BK-05): a known vendor template gives high confidence and can auto-stage, while an unrecognized layout goes through the full PaddleOCR pipeline and a lower confidence score.

## Consequences

- No client financial document is ever sent to a third-party OCR/LLM API — directly satisfies the DPDP data-residency principle established in ADR 0004, provided hosting

itself is also India-resident (see ADR 0007 revision).

- Starting CPU-only keeps infrastructure cost low; if throughput becomes a genuine bottleneck as volume scales toward 500 clients, GPU provisioning is a targeted upgrade, not a rebuild.
- PaddleOCR’s accuracy should be validated against a representative sample (20-50 real invoices across different vendor formats) before committing further — this is standard practice for evaluating open-source OCR fit, not just a formality, since production accuracy on this specific practice’s actual documents is the only number that matters.
- DocTR was considered as an alternative but confirmed to lack table structure recognition in its current release — a real gap for line-item extraction specifically, so it wasn’t chosen as primary.
- Open-weight VLMs (Qwen2.5-VL, DeepSeek-OCR, etc.) remain a future option for hard/low-confidence cases, but are not the primary engine — numeric accuracy on financial figures needs validation before trusting VLM-style extraction over deterministic OCR, and GPU cost/latency are real constraints.

## Alternatives considered

- Cloud OCR/LLM API (Claude, GPT-4V, AWS Textract, Azure Document Intelligence, Google Document AI) — rejected as the primary path given DPDP stringency, even though some of these offer India-region processing (e.g., AWS Textract via Mumbai). Self-hosting removes the question entirely rather than relying on a vendor’s regional processing guarantee.

- Tesseract as primary — rejected; CPU-only and fast, but raw-text-only output would require substantial custom logic to reconstruct table/line-item structure that PP- Structure provides out of the box.
- DocTR as primary — rejected due to confirmed lack of table structure recognition in the current release.
