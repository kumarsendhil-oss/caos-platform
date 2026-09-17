# P0-06 — Zoho Books Sandbox Spike: Findings

Validates, per ADR 0011 and the Sprint Plan: the OAuth2 authorization flow,
the Bill/Journal-posting API request/response shape, and Zoho's currently
published rate limits — against the "Integra Agro" trial org (India DC,
org ID 60088150280).

## Setup log

- [x] Self Client registered on api-console.zoho.in
- [x] Grant code exchanged for access + refresh token (get_tokens.py)
- [x] Refresh flow confirmed working (refresh_and_test.py)
- [x] `/organizations` read confirms org ID and API domain
- [x] `/contacts` read confirms basic data access
- [x] Write-side test — POST /bills (reverse-charge path proven; forward-charge/normal-tax path still open — see #6)
- [x] Forward-charge test with a GST-registered test vendor, to actually observe the CGST/SGST split (#8, #9)
- [x] Duplicate-posting check (BK-08) — incidental on a rerun (#7), then targeted with varied bill_number (#10)
- [x] Rate limit headers/behavior observed under repeated calls — 429 triggered live (#11)
- [x] Journals read/write/read-back cycle, compared against Bills (#12)

## Findings

<!-- Numbered like p0-02-tally's FINDINGS.md — one entry per surprise,
     bug, undocumented behavior, or decision point. -->

### #1 — Self Client grant codes expire fast; the failure mode is silent-looking

`get_tokens.py`'s first run returned `HTTP 200` with body `{"error": "invalid_code"}` —
a 200 status on an error response, easy to mis-read as success if you're not
checking the payload. Root cause: the grant code from the Generate Code tab
is single-use and short-lived (~10 min max); several minutes elapsed between
generating it and running the exchange (repo setup, `.env` editing, etc.).

Fix was mechanical — generate a fresh code, edit `.env`, run immediately,
no gap. Confirmed working on retry.

**Implication for later work:** any documentation or onboarding flow for the
real production `ZohoAdapter` (Sprint 1-2) needs to treat the authorization
code as consumed-on-generation, not something to hand off or queue. Since
production uses a proper Server-based Application (redirect-based consent),
this exact failure mode won't recur the same way, but the general lesson —
Zoho can return `HTTP 200` on an error body — is worth carrying into error
handling for `post_entry` and any other adapter call. Don't rely on status
code alone; parse the body for an `error` key.

### #2 — OAuth refresh + read round trip confirmed, org config as expected

`refresh_and_test.py` clean pass:
- Refresh grant → `HTTP 200`, new access token issued from the saved refresh token.
- `GET /organizations` → `HTTP 200`. Confirms org ID `60088150280`, India DC
  (`version: "india"`), `time_zone: "Asia/Calcutta"`, `sales_tax_type: "exclusive"`,
  `tax_group_enabled: true` — all as expected for a India-edition org.
- `GET /contacts` → `HTTP 200`, empty list (trial org, nothing seeded), well-formed
  pagination shape (`page_context` matches documented structure).

Validates: OAuth2 authorization + refresh mechanics work end-to-end, and the
read-side response shape matches what the API docs describe. No surprises here.

### #3 — "Coastal Services"-style second org: not applicable here (decision, not a bug)

Considered creating a second Zoho Books org (mirroring `p0-02-tally`'s
`Coastal Test Traders` / `Coastal Services Ltd` split) but decided against it —
that split exists in Tally because of a *specific discovered issue* (inventory-
enabled companies reject plain Purchase vouchers, finding #7). Nothing
equivalent has surfaced in Zoho Books yet. Revisit only if/when an
inventory-tracking-related rejection actually shows up — test that by
toggling inventory tracking inside the existing `Integra Agro` org first,
not by creating a new one preemptively.

### #4 — Org had zero tax rates; root cause was GST not enabled, not missing seed data

Initial `GET /settings/taxes` returned empty. `POST /settings/taxes` then
failed with code 110817 ("You have to enable Sales Tax..."). Root cause:
the trial org had no GSTIN configured. Fix was in the UI (Settings → Taxes
→ enter a GSTIN), not the API — once enabled, Zoho auto-provisioned a
`GST18` tax (id `4136804000000034297`), so the script's own tax-group-
creation fallback was never actually needed.

**Implication:** client onboarding (CB-01) needs to confirm the target
Zoho org already has GST enabled with a real GSTIN before the platform
attempts any tax-related write — this can't be done via API.

### #5 — Bills require `account_id`; not documented as prominently as other required fields

First `POST /bills` attempt (valid vendor, valid tax, no `account_id` on
the line item) failed: `HTTP 400, code 4, "Invalid value passed for
bill_number"` — misleading, since the actual first missing field was
`bill_number` (also required, easy to miss). Once that was added, the next
failure correctly named the real gap: `code 13009, "The account field
cannot be empty"`. Fixed by fetching `GET /chartofaccounts` and using an
Expense-classification account.

### #6 — Reverse Charge Mechanism: docs show an invalid combination; found the working shape live

Our test vendor has no GSTIN, so `POST /bills` failed with code 71512
until Reverse Charge was applied. Zoho's own docs example (on the
Expenses endpoint, same request shape) shows `tax_id` and
`reverse_charge_tax_id` **together** on a line item — the live Bills API
rejects that combination (`code 71510`). A top-level
`is_reverse_charge_applied: true` alone was not sufficient either (code
71512 persisted without the line-item field).

**Working shape:** line item carries `reverse_charge_tax_id` only,
`tax_id` omitted entirely. `POST /bills` → `HTTP 201`, bill created
successfully (`bill_id 4136804000000044004`).

**But this didn't answer the original question.** The created bill shows
`tax_total: 0.0` and empty `tax_id`/`tax_percentage` on the line item —
correct RCM behavior (the vendor doesn't charge GST; the buyer
self-assesses it separately), but it means the CGST/SGST split PRD
v0.2.1 claims still hasn't been observed. That requires a **GST-registered
test vendor** (`gst_treatment: business_gst`, a valid-format GSTIN) going
through the normal `tax_id` (forward-charge) path instead. Not yet done —
next step.

Full response detail (org/currency fields omitted, not relevant):
```json
{
  "source_of_supply": "TN", "destination_of_supply": "TN",
  "is_reverse_charge_applied": true,
  "tax_total": 0.0, "sub_total": 10000.0, "total": 10000.0,
  "line_item": {"tax_id": "", "tax_percentage": 0, "item_total": 10000.0}
}
```

### #7 — Duplicate-posting check (BK-08): Zoho DOES enforce vendor+bill_number uniqueness natively

Re-running `post_bill.py --send` (fixed `bill_number`, same vendor, no
`--duplicate` flag needed — this happened on an ordinary rerun) got:

```
HTTP 400 — code 13011: "A bill with this number has already been created
for this vendor. Please check and try again."
```

**This contradicts BK-08 as currently worded.** The PRD states "verified
that neither Tally's XML import nor Zoho's write API prevents duplicate
entries on its own" — but Zoho's write API just did prevent a duplicate,
unprompted, on the vendor+bill_number combination.

**Caveat — this doesn't fully settle BK-08.** What's confirmed is narrower
than what BK-08 describes: Zoho catches identical (vendor, bill_number).
BK-08's actual dedup key is (vendor GSTIN, invoice number, date) — not
tested here, and not necessarily the same check. Two things worth testing
before revising BK-04/BK-08's wording:
- Same vendor, same real invoice, but a *different* `bill_number` string
  (e.g. trailing whitespace, different formatting) — does Zoho still catch it?
- Whether this uniqueness is enforced per-organization or only within
  some other scope.

Until re-tested, treat this as "Zoho has at least one native duplicate
guard, narrower than assumed" rather than "the platform-level duplicate
check is unnecessary for the Zoho adapter."

### #8 — Forward charge: Zoho DOES compute the split, but not in the fields anyone would look for

The question #6 could not answer, now answered. A GST-registered vendor
(`gst_treatment: "business_gst"`, checksum-valid fictitious GSTIN
`33AACCP1234F1Z0`) with a normal line-item `tax_id` (the org's auto-provisioned
`GST18`, `tax_type: "tax_group"`), `source_of_supply` and
`destination_of_supply` both `TN`:

```
HTTP 201. tax_total: 1800.0, sub_total: 10000.0, total: 11800.0
taxes: [ {tax_name: "CGST9 (9%)", tax_amount: 900.0, tax_id: ...34225},
         {tax_name: "SGST9 (9%)", tax_amount: 900.0, tax_id: ...34226} ]
line_items[0].line_item_taxes: [ same two components ]
```

Inter-state (`TN` -> `KA`) with `IGST18`, same amount, for contrast:

```
taxes: [ {tax_name: "IGST18 (18%)", tax_amount: 1800.0} ]
```

So the split is real and server-side: we sent one 18% reference, Zoho returned
two named 9% components. The pair of bills is what makes this conclusive — a
single intra-state bill could not distinguish "Zoho computed the split" from
"Zoho echoed what we sent."

**The trap, and it is a real one: `cgst_total`, `sgst_total` and `igst_total`
do not exist in the response.** They were probed for explicitly and are absent
from the bill object in both the intra- and inter-state cases. The breakdown
arrives only as a **`taxes[]` array of `{tax_id, tax_name, tax_amount}`
objects** at document level, mirrored per line as `line_item_taxes[]`. The
component is identified by a **human-readable `tax_name` string**
(`"CGST9 (9%)"`) — there is no machine-readable `tax_specific_type` on those
array entries.

**Implication.** `ZohoAdapter`'s read path cannot pick CGST/SGST/IGST totals
off named scalar fields; it must iterate `taxes[]` and map each entry back to a
component, and the only key it gets for free is the org's own tax-name string,
which is org-configurable. Resolve the component by looking the `tax_id` up
against `GET /settings/taxes` (where `tax_specific_type` *is* populated:
`igst`, and `cgst`/`sgst` on the group's members) rather than by parsing
`tax_name`. Also note `line_items[].tax_amount` came back **`None`** while
`line_item_taxes[]` carried the real numbers — the obvious-looking field is
the wrong one.

Bears on: ZB-02/ZB-03 (normalizing Zoho's shape to the standard schema),
ADR 0011 Amendment 1.

### #9 — Zoho VALIDATES the CGST/SGST-vs-IGST choice; it does not derive it. Corrects our own schema reference.

This is the sharpest result of the session, and it contradicts something this
spike had already written down as established.

`zoho-bills-schema-reference.md` stated:

> the adapter doesn't need to compute CGST/SGST/IGST itself, it hands Zoho
> these two state codes and a `tax_id`, and Zoho derives the split.

**Live, that is false.** Posting the intra-state tax group (`GST18` =
CGST9+SGST9) on an inter-state supply is rejected outright:

```
HTTP 400 — code 3032: "IGST has to be applied as this is an interstate transaction"
```

And the mirror case — `IGST18` on an intra-state supply — is rejected
symmetrically:

```
HTTP 400 — code 3032: "IGST cannot be applied as this is an intrastate transaction"
```

Same error code in both directions. So `source_of_supply` /
`destination_of_supply` are not *inputs Zoho computes from*; they are the
premise Zoho **checks the caller's tax choice against**. The caller must
already have decided intra vs inter and picked the matching `tax_id`.

What Zoho does compute is the *decomposition* of an already-correctly-chosen
tax into its components (#8). Those two things were being conflated.

**Implication, and it changes adapter work, not just wording.**
`ZohoAdapter.post_entry` needs a real tax-selection step: compare supplier
state against place of supply, then resolve to an intra-state tax group or an
IGST tax from `GET /settings/taxes`. That is the same intra/inter decision
`TallyAdapter` has to make to choose its CGST/SGST vs IGST ledger lines — so
the decision is **common to both backends and belongs above the adapter
boundary**, not duplicated inside each one. ADR 0011 Amendment 1's
determinants (place of supply, supplier state) are exactly the right inputs;
what was wrong was the assumption that Zoho would consume them directly.

**This makes `PENDING:018` materially worse than recorded** — and is what promoted it to **issue #50** (2026-09-16), since it turned a schema question into an architectural one. That row notes
three unreconciled state representations failing *silently* — an intra/inter
comparison across two representations returning unequal rather than raising.
On the Zoho path that bug now has a second face: get the comparison wrong and
the adapter picks the wrong tax, and Zoho rejects the post with 3032. Loud
rather than silent, which is better — but it means a state-representation bug
surfaces as a **posting failure** for Zoho clients and as **wrong tax in the
books** for Tally clients. Settle this before either adapter is built — tracked as issue #50.

The schema reference has been corrected in place, following #7's precedent.

### #10 — BK-08: Zoho's duplicate guard is case- and whitespace-insensitive, and nothing more

#7 proved only that a byte-identical `(vendor, bill_number)` repeat is caught.
Four variants of the same bill number were posted against the same vendor,
same amount, same date:

| Variant | `bill_number` sent | Result |
|---|---|---|
| trailing space | `"P0-06-FC-INTRA-...-183055 "` | **REJECTED** 13011 |
| leading space | `" P0-06-FC-INTRA-...-183055"` | **REJECTED** 13011 |
| lowercased | `"p0-06-fc-intra-...-183055"` | **REJECTED** 13011 |
| hyphens stripped | `"P006FCINTRA20260916183055"` | **ACCEPTED** — new bill created |

So the guard **trims whitespace and folds case**, and beyond that is an exact
string match. Any difference in punctuation, internal spacing, or formatting
creates a second bill with no complaint.

**What BK-08's wording should say.** Its current claim —

> verified that neither Tally's XML import nor Zoho's write API prevents
> duplicate entries on its own

— is wrong as written for Zoho, and should not simply be inverted either.
Accurate: *Zoho's write API enforces a case-insensitive, whitespace-trimmed
uniqueness constraint on (vendor, `bill_number`) and rejects violations with
code 13011. That constraint is narrower than BK-08's dedup key (vendor GSTIN +
invoice number + date) in every dimension that matters: it is keyed on the
contact record rather than the GSTIN, it ignores the date entirely, and it
matches the invoice number literally rather than semantically. The platform's
CG7 check therefore remains necessary, and must run first — Zoho's guard is a
backstop against exact repeats, not a dedup implementation.*

Two practical consequences: (1) CG7 must normalise invoice numbers before
comparing, since `INV-001` and `INV001` are the same invoice to a human and two
different bills to Zoho; (2) the adapter must handle 13011 as an *expected*
outcome — a bill that CG7 passed but Zoho rejects as a duplicate is a genuine
conflict and belongs in a Task (CG6/CG8), not an exception.

Still untested: whether the constraint is scoped per-organization (assumed,
not proven — a single-org spike cannot show it).

### #11 — Rate limit (OQ-05): 429 / code 43, `Retry-After: 3600`, and NO budget headers at all

Triggered live, which took some doing. Four bursts of read-only
`GET /organizations`:

| Burst | Requests | Duration | Rate | Result |
|---|---|---|---|---|
| serial | 150 | 36.4s | ~247/min | all 200 |
| serial | 500 | 182.8s | ~164/min | all 200 |
| 25 threads | 300 | 5.3s | ~3,400/min | all 200 |
| 25 threads | 809 | 10.9s | ~4,450/min | **429 at request 804** |

The rejection:

```
HTTP 429
{"code": 43, "message": "For security reasons you have been blocked for some
 time as you have exceeded the maximum number of requests per minute."}
Retry-After: 3600
```

**Three things matter here, and the published figure is not one of them.**

1. **The commonly-cited "100 calls/minute per organization" is not what is
   enforced.** 500 serial requests sustained ~164/min with no rejection at all,
   and 300 concurrent requests at ~3,400/min passed clean. The trip point came
   only in the fourth burst; counting the rolling 60 seconds around it, roughly
   1,100+ requests had landed. The honest statement of the limit is **"not
   enforced below ~1,000 requests in a rolling minute for this org"** — a floor
   observed, not a documented number confirmed. Do not encode a specific
   threshold in the adapter.
2. **`Retry-After: 3600`. The penalty is an hour, not a minute.** The message
   says "per minute"; the remedy is 3,600 seconds of blocking. Tripping this in
   production would take a client's entire Zoho connection offline for an hour —
   for *all* operations, not just the offending one. This is a materially worse
   failure mode than a per-minute throttle and is the single most important
   operational fact in this finding.
3. **Zoho sends no proactive quota headers whatsoever.** Every 200 response was
   checked for any header containing rate / limit / remaining / reset / retry /
   quota / throttl. Across 1,759 requests: **none**. `Retry-After` appears *only*
   on the 429 itself. Full header set on a normal response: `Allow,
   BUILD_VERSION, CLIENT_BUILD_VERSION, Cache-Control, Connection,
   Content-Disposition, Content-Encoding, Content-Type, Date, Expires, Pragma,
   SERVER_BUILD_VERSION, Server, Strict-Transport-Security, Transfer-Encoding,
   X-Content-Type-Options, X-Frame-Options, vary`.

**Implication.** The adapter cannot do budget-aware pacing — there is no budget
to read. Combined with the hour-long penalty, that argues for **client-side
rate limiting as a hard design requirement, not a retry policy**: a conservative
self-imposed ceiling well under the observed floor, applied per-organization.
CG6's "bounded retry" must additionally treat 429 as non-retryable-in-process —
retrying against a 3,600-second block just burns the worker; it belongs in a
Task with a scheduled resume. This is closer to ADR 0002's GSP rate-limit
posture than anything currently written for Zoho.

**Sandbox state note:** the `Integra Agro` org was rate-blocked at 13:08 UTC on
2026-09-16 with a stated 3,600-second penalty. All four of this session's
task-list items had already completed, so nothing was left blocked, but any
follow-up run started within that hour will fail with code 43 — expected, not a
new bug.

### #12 — Journals are NOT a tax-capable posting path. They reject tax outright and silently drop supply states.

The first Journal work in this spike. `POST /journals` with a balanced two-leg
entry (debit `Bank Fees and Charges` 10,000, credit `Petty Cash` 10,000) works
cleanly: HTTP 201, `status: "published"`, `journal_type: "both"`, read-back
matches.

Beyond that, Journals diverge from Bills in both directions:

- **A line-item `tax_id` is rejected.** `HTTP 400 — code 110942: "Tax not
  supported."` Retried with top-level `gst_treatment: "business_gst"`,
  `journal_type: "both"` and both supply states supplied, in case tax needed GST
  context to be unlocked: **same rejection, same code.**
- **`source_of_supply` / `destination_of_supply` are accepted and then silently
  discarded.** The POST returns HTTP 201 — no error, no warning — and both
  fields are **absent from the read-back**. Only the read-back caught this. On
  Bills the same two fields round-trip intact.
- `taxes` is present on a Journal but always `[]`; `tax_total` is absent
  entirely.

**Implication, and it is a routing decision, not a detail.** PRD ZB-03 says
approved entries post "as Bills or Journal Entries" and that "Zoho's own
tax-component fields carry the CGST/SGST/IGST breakdown." That is true of Bills
and **false of Journals** — a Journal cannot carry a tax component at all. So
any `DraftEntry` with a tax determinant must route to Bills (or Invoices on the
sales side); Journals are usable only for tax-free entries such as
reclassifications, accruals and adjustments. `ZohoAdapter` cannot treat Bills
and Journals as one shape with a different URL, and the routing rule needs to be
explicit rather than left to the caller.

The silent field-drop deserves separate emphasis: it is the same class of hazard
as `p0-02-tally`'s counter findings — **a 201 that hides the fact that part of
the request was ignored**. Read-back is the only defence, and it is why this was
caught at all.

Untested, and deliberately not guessed at: whether some other Zoho document type
(Invoice, Credit Note, Vendor Credit) or a different journal flavour supports
tax. Only Bills and Journals have been exercised.

### #13 — `tokens.json` was not actually gitignored (housekeeping, but it is a live credential)

Noticed on pre-flight, before any API call. The repo-root `.gitignore` covers
`.env` at any depth, but nothing matched `spikes/p0-06-zoho/tokens.json`, which
holds this org's long-lived **refresh token**. The spike directory is still
untracked, so nothing was ever committed and no credential was exposed — but the
first `git add spikes/` would have committed it.

Fixed with a spike-local `.gitignore` (`.env`, `tokens.json`, `__pycache__/`),
kept next to the files it protects so the rule travels with the directory rather
than depending on a root-level pattern nobody re-reads.

Bears on Security Standard §3 and its Zoho amendment: a refresh token in git
history would be exactly the "treat as compromised, revoke immediately" scenario
§3 describes.

## Open questions

- [ ] Is the `(vendor, bill_number)` uniqueness constraint scoped per-organization? (#10 — assumed, unprovable in a single-org spike)
- [ ] Does any other Zoho document type (Invoice, Credit Note, Vendor Credit) support tax where Journals do not? (#12)
- [ ] Where exactly does the rate limit sit above the ~1,000/min observed floor? (#11 — deliberately not pinned down further; each attempt costs an hour of org blocking)
- [ ] Refresh token lifetime / revocation behavior on this DC (Security Standard §3, checklist OQ-06)
- [ ] Premium Trial expiry date — check Settings → Subscription before spike work spans past it

## Tooling changes made this session

- `post_bill.py`'s `TEST_BILL_NUMBER` is now timestamped per run. It was a fixed
  string, which meant every rerun failed as a duplicate once #7 had happened —
  the script was effectively single-use. `--duplicate` now reposts *this* run's
  number rather than depending on leftover state from a previous run.
- `zoho_client.py` is new: the `call()` / `get_access_token()` plumbing extracted
  out of `post_bill.py` so every script shares one request path and therefore one
  `run_logger` call site. `post_bill.py` imports it instead of defining its own.
- `run_logger.log_call()` accepts `response_headers`. Response headers are
  persisted (minus `Set-Cookie` / `Authorization`); **request** headers remain
  unlogged, since that is where the bearer token lives. This was necessary for
  #11 — the header *names* were the unknown, so an allowlist could not work.
- `zoho_client` reconfigures stdout/stderr to UTF-8. Zoho's India responses carry
  `₹` in every `*_formatted` field, which cp1252 cannot encode; this killed a
  probe run mid-flight. The `runs/` artifacts were already UTF-8, so no evidence
  was lost.
- New scripts: `forward_charge_test.py` (#8, #9, #10), `rate_limit_probe.py`
  (#11), `post_journal.py` (#12).

