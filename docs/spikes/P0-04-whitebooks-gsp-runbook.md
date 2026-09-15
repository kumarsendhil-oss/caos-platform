# P0-04 Spike — WhiteBooks GSP Runbook

**Status:** requests drafted, **nothing validated yet**
**Blocks:** Sprint 7's Reconciliation Agent (RC-01)
**Companion file:** `gsp_requests.py` — run it to print every request as curl

## Finding that needs attention before Sprint 7

Researching this surfaced an operational problem that ADR 0002 anticipated only partially, and it scales badly.

**GSTN requires each taxpayer to enable API access from the GST portal, and that consent has a duration — commonly 30 days.** It is set by logging into the portal as that taxpayer: *View Profile → Quick Links → Manage API Access → Enable API Request → Duration*.

Stacked on top of that is the per-GSTIN OTP session ADR 0002 already flagged (RC-01a).

ADR 0002 says the OTP step "becomes a scriptable, automated authentication step within the platform rather than a manual per-client action in Winman." That framing needs revisiting on two counts:

1. **The OTP goes to the client, not the practice.** It's delivered to the mobile/email registered against that GSTIN. A practice can script the *request* and the *submission*, but not the *receipt* — someone at the client has to relay a code. That's a per-client human interaction, not an automated step.
2. **API access itself appears to expire.** If the 30-day duration holds, every client's access needs re-enabling on a rolling basis — each requiring a portal login as that taxpayer.

At 500 clients, if both hold as described, that's a recurring per-client manual workflow. It doesn't invalidate ADR 0002 — a GSP is still far better than driving Winman's desktop UI per client per period — but "removes the manual bottleneck at its root" is too strong. It relocates and shrinks the bottleneck rather than eliminating it.

**This is the single most important thing to verify in this spike**, and it's more consequential than any request shape here. It affects the Client Communication Agent's scope (CC-05 already flags OTP-dependent actions as needing a priority call to the client — this makes that pattern central rather than incidental), the Practice Management capacity model, and the feasibility narrative in the customer-facing documentation.

If confirmed, it likely warrants an amendment to ADR 0002 in the same shape as ADR 0011's Amendment 1.

## Setup

1. **Sandbox account** at `apisandbox.whitebooks.in` — free, no card, per ADR 0002/RC-01d. WhiteBooks states sandbox access takes ~5 minutes and provides a sample GSTIN.
2. **Do not use WhiteBooks' published pricing** in any cost conversation. ADR 0002 already flags it as internally inconsistent on their own site; get a direct sales quote.
3. Note the two auth layers are independent: one GSP credential pair for the practice, plus a separate per-GSTIN taxpayer session.

## Tests

Run `python gsp_requests.py` to print each request. Save every full response.

### Test 1 — GSP token (Layer 1)

`client_credentials` exchange for a bearer token.

**Record:** the token TTL (documentation suggests ~1 hour), and the exact endpoint path — the path in `gsp_requests.py` is a reasonable guess, not verified. Correct the file once known.

### Test 2 — Taxpayer OTP flow (Layer 2) — **the important one**

Run the OTP request and verify steps against the sandbox GSTIN.

**Record:**
- Where the OTP is actually delivered in the sandbox (it may be stubbed — if so, that tells you nothing about production behaviour, and the question stays open).
- The **session TTL** returned. This sets how often each client must re-authenticate, which is the number that determines whether this is a weekly annoyance or a daily one.
- Whether the session can be refreshed without a new OTP. If yes, the burden drops sharply. If no, every expiry is another client phone call.

**Also establish, outside the sandbox** (ask WhiteBooks directly, since a sandbox won't show it): does the GST portal's "Manage API Access" duration really cap at 30 days, and does it apply per-GSTIN? This is the question with the biggest downstream impact.

### Test 3 — GSTR-2B fetch (RC-01)

The call the integration exists for.

**Record:** the response's invoice-level structure — specifically whether each line carries supplier GSTIN, invoice number, invoice date and taxable value, since those are exactly what RC-02 matches on. Also note the pagination model if the response is large; a client with thousands of purchase invoices in a period is the normal case, not an edge case.

**Note the date format:** `MMYYYY`. Tally uses `YYYYMMDD`, Zoho uses ISO `YYYY-MM-DD`. Three backends, three formats — worth a single normalisation helper rather than three ad-hoc conversions scattered through the agents.

### Test 4 — GSTR-2A (RC-01)

RC-01 names both 2A and 2B.

**Record:** how the two differ in the sandbox's sample data, and whether 2A is worth fetching at all for reconciliation. 2B is the static monthly snapshot ITC eligibility is determined against; 2A is the live view. The likely answer is "2B for reconciliation, 2A only to spot late supplier filings" — but confirm rather than assume, since fetching both doubles the call volume.

### Test 5 — GSTIN search (public API)

Needs no taxpayer authentication, which makes it the cheapest thing to test and potentially useful well beyond reconciliation: validating a vendor GSTIN scraped off an invoice before BK-02 tries to match on it.

**Record:** what it returns (legal name? registration status? state?) and whether it's rate-limited differently from the authenticated endpoints.

### Test 6 — Rate limits and cost

**Record:** published per-call or per-tier limits, and whether responses carry rate-limit headers.

Combine with Test 3's pagination finding to sanity-check the call volume at 500 clients. Per Security Standard §8, internal rate limiting is required regardless — a retry loop against a per-call-billed API is a cost incident, not just a performance one.

## After the spike

- Paste real request/response pairs in as an appendix, and **correct the endpoint paths** in `gsp_requests.py` — several are inferred.
- **If the per-client consent finding holds, draft an amendment to ADR 0002.** Same pattern as ADR 0011 Amendment 1: the decision stands, one of its stated consequences was optimistic.
- Feed the call-volume numbers into the cost model revision that ADR 0012 already triggered.
- Update `docs/STUB_ISSUES.md` if any of this changes the scope of the reconciliation work.
