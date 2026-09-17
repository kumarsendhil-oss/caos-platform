# Zoho Books — Bills API Reference Schema (P0-06)

Source: https://www.zoho.com/books/api/v3/bills/ (fetched 2026-09-16).
This is the subset of fields relevant to BK-04 / ADR 0011 Amendment 1 —
not the full schema (Bills has ~60 fields total, most UK/US/GCC-specific
and irrelevant here).

## POST /bills — top-level fields we care about

| Field | Required? | Notes |
|---|---|---|
| `vendor_id` | Yes | From Contacts API |
| `bill_number` | Yes | Vendor's own invoice number. Must be unique per org — this is exactly what BK-08's duplicate check should key on |
| `line_items` | Yes | Array, see below |
| `date` | No | Defaults if omitted; format `yyyy-mm-dd` |
| `gst_no` | No — 🇮🇳 India | Vendor's 15-digit GSTIN. Our test vendor has none set — omit for now, revisit if Zoho rejects |
| `gst_treatment` | No — 🇮🇳 India | `business_gst`, `business_none`, `overseas`, `consumer`. Determines whether GST fields are expected at all |
| `source_of_supply` | No — 🇮🇳 India | 2-letter state code where goods/services originate. **Defaults to vendor contact's state if omitted** |
| `destination_of_supply` | No — 🇮🇳 India | 2-letter state code where delivered. **Defaults to org's home state if omitted** — this is the field that determines CGST+SGST (same state) vs IGST (different state) |
| `is_reverse_charge_applied` | No — 🇮🇳 India | Not relevant for this spike |

**This confirms half of the BK-04 tax-determinant design**: `source_of_supply`
+ `destination_of_supply` are exactly the "place of supply, supplier state"
determinants ADR 0011 Amendment 1 says `DraftEntry` should carry.

> ⚠️ **Corrected by live testing — see FINDINGS.md #9.** This paragraph
> previously concluded "the adapter doesn't need to compute CGST/SGST/IGST
> itself, it hands Zoho these two state codes and a `tax_id`, and Zoho derives
> the split." **That is false.** Zoho does not derive the tax from the state
> codes — it *validates* the caller's `tax_id` against them, and rejects a
> mismatch in either direction with `code 3032`. The adapter must itself decide
> intra-state vs inter-state and select the matching tax (a CGST/SGST tax group
> vs an IGST tax). What Zoho computes is the *decomposition* of an
> already-correctly-chosen tax into its components — see §"Tax in the response"
> below.

## line_items[] — fields we care about

| Field | Required? | Notes |
|---|---|---|
| `name` | Yes (if no `item_id`) | Line description |
| `rate` | Yes | Unit price |
| `quantity` | Yes | |
| `account_id` | **Yes** | Chart-of-accounts entry — this was our HTTP 400 ("account field cannot be empty"). Must be an Expense-classification account. From Chart of Accounts API |
| `tax_id` | No | Individual tax or tax group ID, from Settings > Taxes |
| `hsn_or_sac` | No — 🇮🇳 India | Relevant later for BK-01's extraction scope, not blocking now |
| `item_total` | Read-only | Auto-calculated, don't send |

## Confirmed request shape (from Zoho's own Expenses example — same pattern applies to Bills)

```json
{
  "vendor_id": "...",
  "bill_number": "...",
  "line_items": [
    {
      "name": "...",
      "rate": 10000,
      "quantity": 1,
      "account_id": "...",
      "tax_id": "..."
    }
  ]
}
```

## Chart of Accounts — what we still need

`GET /chartofaccounts?organization_id={id}` — need an account with
`account_type`/classification of **Expense** (e.g. a default "Cost of Goods
Sold" or similar purchase-expense account most orgs get auto-provisioned).
Resolved: `Integra Agro` auto-provisioned several, and every bill in this
spike posted against `Purchase Discounts` (`account_type: "expense"`).

## Reverse Charge Mechanism — live-tested correction to the docs

Zoho's own published example (on the Expenses endpoint, same request shape)
sends `tax_id` and `reverse_charge_tax_id` **together** on a line item. The
live Bills API rejects that combination outright:

```
HTTP 400 — code 71510: "You cant apply both reverse charge and tax to the
same transaction."
```

**The documented example is not a valid live request.** Confirmed working
shape: when RCM applies (our test vendor had no GSTIN, triggering it —
code 71512 without this), send `reverse_charge_tax_id` on the line item
and omit `tax_id` entirely — they're mutually exclusive, not additive.
Top-level `is_reverse_charge_applied: true` did not by itself satisfy the
requirement (code 71512 persisted) — the line-item-level
`reverse_charge_tax_id` is what actually mattered.

This is exactly `p0-02-tally`'s FINDINGS.md #11 pattern again: don't trust
a documented shape or an assumption about behavior — the live API's actual
response is the only reliable source of truth here.



**Resolved live:** `line_items.tax_id` does accept a **tax group id** the same
way it accepts a plain tax id. The intra-state bill in FINDINGS.md #8 passed
`GST18` (`tax_type: "tax_group"`) and Zoho accepted it, expanding it into its
CGST9 + SGST9 members in the response. For India GST this is not merely
supported but *required* on intra-state supplies — the plain (non-group) 18%
taxes in this org are the `IGST18` ones, which are rejected intra-state
(code 3032, see below).

## Tax in the response — live-confirmed shape (forward charge)

Established by `forward_charge_test.py`; see FINDINGS.md #8 and #9.

**There are no `cgst_total` / `sgst_total` / `igst_total` fields.** They were
probed for explicitly on both an intra-state and an inter-state bill and are
absent from the response in both cases. The breakdown is carried as arrays:

| Field | Level | Shape |
|---|---|---|
| `taxes[]` | document | `[{tax_id, tax_name, tax_amount, tax_amount_formatted}]` |
| `line_items[].line_item_taxes[]` | line | `[{tax_id, tax_name, tax_amount}]` |
| `tax_total` | document | scalar, the sum — **no** component detail |
| `line_items[].tax_amount` | line | returned as `null` — do not read it |

Intra-state (`TN` -> `TN`) with the `GST18` tax group on a 10,000 line:

```json
"tax_total": 1800.0,
"taxes": [
  {"tax_id": "...34225", "tax_name": "CGST9 (9%)", "tax_amount": 900.0},
  {"tax_id": "...34226", "tax_name": "SGST9 (9%)", "tax_amount": 900.0}
]
```

Inter-state (`TN` -> `KA`) with `IGST18`, same line:

```json
"tax_total": 1800.0,
"taxes": [ {"tax_id": "...34217", "tax_name": "IGST18 (18%)", "tax_amount": 1800.0} ]
```

**Reading the components back:** the array entries carry no
`tax_specific_type` — only an org-configurable display string
(`"CGST9 (9%)"`). Resolve each `tax_id` against `GET /settings/taxes`, where
`tax_specific_type` *is* populated, rather than parsing `tax_name`.

## Choosing the tax: the caller's job, not Zoho's

Zoho enforces the intra/inter rule but does not apply it for you. Both
directions were tested and both are rejected with the same code:

| Supply | `tax_id` sent | Result |
|---|---|---|
| `TN` -> `TN` | `GST18` (CGST9+SGST9 group) | HTTP 201 ✅ |
| `TN` -> `KA` | `GST18` (CGST9+SGST9 group) | HTTP 400, `3032` — "IGST has to be applied as this is an interstate transaction" |
| `TN` -> `KA` | `IGST18` | HTTP 201 ✅ |
| `TN` -> `TN` | `IGST18` | HTTP 400, `3032` — "IGST cannot be applied as this is an intrastate transaction" |

The org's taxes divide cleanly along this line — `GST0/5/12/18/28/40` are
`tax_type: "tax_group"` (the CGST+SGST pairs), and `IGST0/5/12/18/28/40` are
`tax_type: "tax"` with `tax_specific_type: "igst"`.

## Duplicate guard on `bill_number`

Live behaviour (FINDINGS.md #7, #10): `(vendor, bill_number)` uniqueness is
enforced with `code 13011`, **case-folded and whitespace-trimmed**, and is
otherwise an exact string match. `"INV-001 "`, `" INV-001"` and `"inv-001"`
all collide with `"INV-001"`; `"INV001"` does not.

Correction to the table above: `bill_number`'s note "Must be unique per org"
is unproven — the constraint was only ever observed per *vendor*, and
per-organization scoping has not been tested.

## Journals are a different shape — do not assume Bills parity

See FINDINGS.md #12. `POST /journals` accepts a balanced two-leg entry and
returns `status: "published"`, but:

- a line-item `tax_id` is **rejected** with `code 110942: "Tax not supported."`,
  including when top-level `gst_treatment` and both supply states are supplied;
- `source_of_supply` / `destination_of_supply` are **accepted and silently
  dropped** — HTTP 201, then absent from the read-back;
- `taxes` is always `[]` and `tax_total` is absent.

Any tax-bearing entry must route to Bills, not Journals.
