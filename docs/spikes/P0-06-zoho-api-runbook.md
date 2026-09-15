# P0-06 Spike — Zoho Books API Runbook

**Status:** requests drafted, **nothing validated yet**
**Blocks:** Sprint 1-2's `ZohoAdapter` build (issues #4, #5, #6)
**Companion file:** `zoho_requests.py` — run it to print every request as curl

## Finding that needs a decision before the adapter is built

Drafting these requests surfaced a structural mismatch that ADR 0011 didn't anticipate, and it affects the `BooksConnector` interface itself.

**Tally and Zoho model GST differently.**

| | Tally | Zoho Books |
|---|---|---|
| Tax representation | Explicit CGST/SGST/IGST **ledger lines** in the voucher | A `tax_id` **per line item**; Zoho computes the split itself |
| Intra- vs inter-state | Caller decides which ledgers to use | Zoho derives it from `source_of_supply` vs `destination_of_supply` |
| What the caller supplies | Pre-computed tax amounts | Tax *rate reference*, and the two state codes |

`BooksConnector.DraftEntry` currently carries `cgst`, `sgst`, `igst` as `Decimal` amounts — which is a faithful model of Tally and a poor fit for Zoho. The `ZohoAdapter` can't pass these through; it has to reverse them into a `tax_id` plus two state codes.

Three options, to decide before writing either adapter's real implementation:

1. **Keep `DraftEntry` as-is; `ZohoAdapter` translates.** Needs a tax-rate → `tax_id` lookup per organization, and source/destination state codes from somewhere (client master? the invoice?). Most work, but leaves the interface honest about what the Bookkeeping Agent actually extracted.
2. **Add optional Zoho-shaped fields to `DraftEntry`.** Pollutes the shared interface with backend-specific concepts — directly against ADR 0011's premise that agents never see backend detail.
3. **Change `DraftEntry` to carry tax *rate* rather than computed amounts**, and let each adapter derive what it needs. Cleaner conceptually; means `TallyAdapter` computes the split instead of receiving it.

**Recommendation: option 1**, but this is a real architectural decision and belongs in an ADR amendment, not a quiet implementation choice. Resolve before issue #5 is started.

## Prerequisites

1. **Zoho Books account** with API access (any paid plan or trial).
2. **Register a Self Client** at the Zoho Developer Console (`https://api-console.zoho.in/` for India). Self Client is the right type here — it's Zoho's documented pattern for server-to-server integrations and avoids a browser redirect on every token refresh.
3. **Confirm the region.** The practice is in India, so this spike assumes `accounts.zoho.in` / `www.zohoapis.in`. Zoho enforces this strictly — a token from `.in` will not work against `.com`. If the client's Zoho account turns out to be on a different data centre, set `ZOHO_REGION` accordingly. **Verify rather than assume.**

## Tests

Run `python zoho_requests.py` to print every request. Save the full JSON response from each — the response shapes are what `ZohoAdapter`'s parsing gets written against.

### Test 1 — OAuth flow end to end (issue #6)

Complete the consent → code → tokens exchange, then a refresh.

**Record:** the `expires_in` value (expected 3600), and confirm a `refresh_token` actually came back. If it didn't, `access_type=offline` was missing from the consent URL — without a refresh token the whole unattended-sync design fails.

**Also record:** whether the token response's `api_domain` matches the region assumed above. Zoho returns the correct domain in the response; if it disagrees with `ZOHO_REGION`, trust the response.

### Test 2 — Organizations (issue #6)

`GET /organizations` — the only endpoint not requiring `organization_id`, which makes it the natural implementation of `connection_health`.

**Record:** the `organization_id`, and whether the response distinguishes an expired token from a revoked one. ADR 0011's Admin — Connections screen shows `connected | token_expired | revoked` as distinct states; if the API can't distinguish the latter two, that UI promises more than the backend can deliver.

### Test 3 — Reads (issue #4)

Bills, invoices, contacts, bank transactions.

**Record for each:** the pagination shape (`page_context`?), whether `per_page=200` is actually honoured or silently capped, and — for bills — whether the line-item detail is present in the list response or requires a second `GET /bills/{id}` per record. That last point matters a lot: if detail needs a per-bill call, extracting a month of purchases becomes N+1 requests and the rate limit (below) becomes the binding constraint.

**Also record:** whether vendor GSTIN is present on contacts. Same question as the Tally spike — if it's absent, BK-02's matching loses its most reliable key.

### Test 4 — Rate limits (ADR 0011 open item)

ADR 0011 explicitly flagged Zoho's rate limits as needing verification against current docs rather than assumption. This spike is where that gets answered.

**Record:** the actual published limits for the account's plan tier, and whether responses carry rate-limit headers (`X-Rate-Limit-Remaining` or similar). Combine with the N+1 finding from Test 3 to sanity-check feasibility at 500 clients — per Security Standard §8, internal rate limiting is required independent of whatever Zoho enforces.

### Test 5 — Create a bill (issue #5)

**Prerequisites:** a vendor contact, an expense account, and a GST tax rate must exist in the sandbox org — the request needs their IDs. Create them via the UI first and note the IDs.

**Record:** the created bill's computed tax breakdown. Verify Zoho split it into CGST/SGST as expected for an intra-state supply (both state codes `TN`), then repeat with `destination_of_supply` set to a different state and confirm it produces IGST instead. This is what validates the option-1 translation approach above.

### Test 6 — Duplicate bill number (CG7)

Send Test 5's request again, unchanged.

ADR 0001 established that Tally does not prevent duplicate vouchers, which is why CG7 requires a platform-side check. **Does Zoho behave the same way?**

**Expected:** unknown — genuinely worth finding out.
**If Zoho rejects it:** that's a real difference between adapters. CG7 stays regardless (defence in depth, and the check runs before either adapter is called), but it's worth documenting that the two backends differ here.

## After the spike

- Paste real request/response pairs into this file as an appendix.
- **Resolve the `DraftEntry` tax-modelling question** above before starting issue #5.
- Update `docs/STUB_ISSUES.md` with anything that changes the scope of issues #4, #5, #6.
- If the N+1 finding from Test 3 is bad, flag it against ADR 0012 — it materially affects the per-client API call volume that cost model assumes.
