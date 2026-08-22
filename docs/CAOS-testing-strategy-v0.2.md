# Testing Strategy — Practice Automation Platform
### v0.2

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial strategy: test pyramid, external-service mocking approach, critical end-to-end flows, test data rules (DPDP-aligned), confidence-threshold boundary testing, and CI gates. |
| v0.2 | 2026-08-22 | §2 mock boundary extended to include Zoho Books alongside Tally, GSP, and OCR. §3 critical flow #1 now explicitly requires running against both the Tally and Zoho adapters before it's considered passing, per ADR 0011. |

## 1. Test pyramid

```
        /\
       /e2e\        A handful — the critical flows in §3, run nightly
      /------\
     / integr. \    Against sandboxes (Tally API Explorer, Zoho Books sandbox,
    /------------\   WhiteBooks GSP sandbox) — run on merge to main, not every PR
   / unit tests  \  The bulk — every agent's matching/extraction
  /------------------\  logic, run on every PR
```

Most of the platform's actual risk lives in unit-testable logic — fuzzy vendor matching, confidence scoring, duplicate detection, Decimal-precision reconciliation math — not in the plumbing around it. Weight the suite accordingly rather than defaulting to broad, shallow end-to-end coverage.

## 2. What gets mocked, and what doesn't

*Amended in v0.2 — Zoho Books added to the mock boundary and sandbox list, per ADR 0011.*

Per CG10 (Coding Guidelines) and the amended CG7: Tally, **Zoho Books**, the GSP, and OCR calls are mocked at the client boundary in the unit/PR-level suite. CI never calls a real external service on every PR — those are rate-limited, sometimes cost money per call (GSP API, and potentially Zoho depending on plan tier), and would make the fast feedback loop slow and flaky.

- **Unit tests:** mock everything external. Fast, run on every push. This includes both the `TallyAdapter` and `ZohoAdapter` implementations of `BooksConnector` — agent-level tests (Bookkeeping, Reconciliation) mock the `BooksConnector` interface itself, not either adapter's internals, so the same test suite exercises both code paths by parametrizing on `books_system`.
- **Integration tests:** run against the real sandboxes — TallyPrime API Explorer (per ADR 0001), **Zoho Books' developer sandbox (per ADR 0011 — validate during the Phase 0 spike, P0-06)**, and the WhiteBooks GSP sandbox (per ADR 0002) — on merge to main, not on every PR. These catch drift between what the mocks assume and what the real APIs actually do.
- **Manual/exploratory testing:** anything requiring a real client's live Tally company, live Zoho organization, or live GSTIN never happens in an automated test — only in a controlled staging walkthrough with the practice's explicit involvement.

## 3. Critical end-to-end flows (test these explicitly, not incidentally)

These mirror the platform's actual value proposition — if these silently break, the automation isn't working even if unit tests are green.

1. **Document intake → bookkeeping → entry posted:** a sample invoice enters via the Dropbox webhook, gets OCR'd, matched to a vendor ledger, staged, approved, and posted — verify the posted entry matches the source document's amounts exactly (Decimal precision, per CG5). **Amended in v0.2: run this flow twice before it's considered passing — once against the `TallyAdapter` (posted as a voucher) and once against the `ZohoAdapter` (posted as a Bill/Journal Entry). The two adapters differ meaningfully in auth model and write shape, so passing on one gives no assurance about the other.**
2. **GSTR-2B fetch → reconciliation → task created:** a known mismatch in fixture data produces exactly one task, with the correct reason code and variance amount — not zero tasks (silently missed) and not duplicate tasks (per CG7's duplicate-prevention principle, applied to reconciliation flagging too). This flow reads purchase-register data via the Books Connector regardless of adapter, but since the reconciliation logic itself operates on the already-normalized schema (TC-03/ZB-02), a single adapter (Tally) is sufficient here — the normalization boundary is what's actually being tested, not the adapter.
3. **Task overdue → escalation:** a task past its due date auto-escalates to the correct role per the routing rule table (TE-02) — this is the mechanism the whole "not another notification system" design (ADR 0005) depends on, so it needs a real test, not just a code review nod.
4. **Invoice draft → approval → GST-compliant output:** a generated invoice contains a valid GSTIN, correct HSN/SAC codes, and a CGST/SGST breakup that sums correctly to the total (CB-09) — malformed invoices are a compliance problem, not just a bug.

## 4. Test data: synthetic only, never real client documents

No real client's GSTIN, financial documents, or extracted data ever appears in a test fixture, committed to the repository, or used in CI — this follows directly from the Logging Standard's PII rules (§6) and the platform's data-minimization architecture (ADR 0004). Test fixtures are synthetic: invented company names, valid-format-but-fake GSTINs, plausible but fictional invoice amounts, and (new in v0.2) a fictional Zoho Books organization ID for adapter tests.

```python
# tests/fixtures/invoices.py
SAMPLE_INVOICE = {
    "vendor_name": "Coastal Test Traders",
    "vendor_gstin": "33AAAAA0000A1Z5",  # valid checksum format, not a real GSTIN
    "invoice_number": "TEST-INV-0001",
    "amount": "18400.00",
}

SAMPLE_ZOHO_ORG = {
    "organization_id": "test-org-000001",  # fictional, not a real Zoho organization
    "client_id": "test-client-sr-enterprises",
}
```

## 5. Confidence-threshold boundary testing

Every agent that uses a confidence score to decide auto-stage vs. flag-for-review (BK-05) needs explicit tests at the boundary, not just "obviously high" and "obviously low" cases — boundary behavior is where real bugs hide. This applies identically regardless of which adapter the matched entry will eventually post through.

```python
def test_voucher_at_exact_confidence_threshold_is_flagged_not_auto_staged() -> None:
    result = score_and_route(confidence=CONFIDENCE_THRESHOLD)  # exactly at the line
    assert result.status == "flagged_for_review"  # threshold is inclusive on the safe side
```

## 6. CI gates

Required to pass before merge:

1. `ruff check . --no-fix` (CG1)
2. Type check (mypy or ruff's type-aware rules)
3. Unit test suite with coverage ≥85% (CG10)
4. No new dependency without a pinned version (CG9-equivalent in the eventual `requirements.txt` discipline)

Run on merge to main, not blocking every PR:

5. Integration suite against Tally API Explorer, **Zoho Books developer sandbox**, and WhiteBooks sandbox
6. The 4 critical end-to-end flows in §3, **including both adapter variants of flow #1**

## 7. What this doesn't cover

Load/performance testing has its own document (Performance & Scaling) — this strategy covers correctness, not throughput or latency targets.
