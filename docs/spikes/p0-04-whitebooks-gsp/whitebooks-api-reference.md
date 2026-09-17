# WhiteBooks GSP — API Reference (distilled)

Source: 5 documents supplied by WhiteBooks (ASP integration doc, GST API
error codes, released-API list, return-filing-through-API guide, TLS
cert), reviewed 2026-09-17. Full source files kept alongside this doc
under `reference/` — this file extracts only what CAOS's design needs;
go to the originals for anything not covered here.

## #51 — Confirmed: OTP goes to the client, not the practice

From WhiteBooks' own ASP documentation (`whitebooks-gst-api-documentation.docx`),
describing the `/authentication/otprequest` call:

> OTP will be sent to registered email and mobile number of your Client
> from GST Portal.

This is first-party, WhiteBooks-specific confirmation — not inferred from
generic GSP docs. The GST Portal sends the OTP directly to the client;
WhiteBooks (the GSP) is not in that delivery path at all. This closes the
open question in issue #51: the OTP-to-client behavior is real and
independent of GSP choice, since WhiteBooks is a thin pass-through to
`devapi.gst.gov.in` (confirmed by the released API list — every endpoint
resolves to that domain directly).

**Session mechanics** (also from the ASP doc): the `TXN` token from
`authtoken` is valid 6 hours. Call `/authentication/refreshtoken` before
expiry to sustain it — this refresh does NOT require a new OTP. A fresh
client-delivered OTP is only needed once the underlying GST-Portal-side
"Enable API Access" duration (set by the client on gst.gov.in, options
up to 30 days) lapses — that portal-side step is outside WhiteBooks'
documentation entirely, confirmed instead via independent GSP docs
(Vayana, IndiaFilings/LEDGERS) describing the same GSTN-wide mechanism.

## New finding — practice-level onboarding is NOT self-serve, contrary to marketing

WhiteBooks' marketing page (whitebooks.in/apis/) advertises "free sandbox
without a contact-form gate." The actual ASP onboarding doc contradicts
this directly — Step 2 of account setup is:

> Enable Account - Call the customer support ask them to enable the
> account.

And after creating credentials, a second support call is needed to
enable the sandbox itself. So onboarding a *new practice* (one-time, not
per-client) requires at least one manual support interaction, despite
the marketing claim of a gate-free signup. This is a one-time practice-
level cost, not a recurring per-client one — much lower stakes than the
#51 finding — but worth not assuming pure API self-service when scoping
onboarding for a new customer firm later.

## Auth flow — request parameters (for whoever implements the adapter)

Base URL: `https://api.whitebooks.in`. Key parameters across calls:
`email` (your WhiteBooks-registered email), `gst_username` (client's
gst.gov.in username), `state_cd` (first 2 digits of client's GSTIN —
same numeric state code ADR 0011 Amendment 2 already made canonical),
`client_id`/`client_secret` (WhiteBooks credentials), `gstin`, `txn`
(from the OTP request response), `ret_period` (MMYYYY).

Endpoint sequence: `otprequest` → `authtoken` (needs OTP + txn) →
`refreshtoken` (every ~6h) → `logout`. Return-specific calls
(`gstr1/retsave`, `retstatus`, `retsubmit`, `retfile`, etc.) all follow
the same save → status → submit → file pattern.

## Error codes worth knowing (from `GST-API-Error-Codes.docx`)

- `RET13509` — "OTP is either expired or incorrect" — a real, documented
  error state; the platform needs to handle this explicitly (e.g.
  surface to the client-communication flow) rather than treat OTP
  failure as exceptional.
- `AUTH151` — "You are not authorized to access GSTR1 for this return
  period" — relevant if a client's consent/access window has lapsed for
  a specific period; likely correlates with the #51 renewal-burden
  finding in practice.
- `RTN_FIL_28` / `29` — certificate expired / not valid — relevant given
  the TLS cert note below.

## TLS certificate

`whitebooks.crt` — `*.whitebooks.in`, issued by GoDaddy Secure
Certificate Authority G2, **valid Oct 23 2025 – Nov 11 2026**. Worth a
calendar note: this expires within CAOS's likely build/launch window —
whoever owns ops should track WhiteBooks' cert rotation rather than
assume a static pinned cert stays valid indefinitely.

## ⚠️ `Return-Filing-through-API_v1_1.docx` — STALE, do not use as a design reference

This document describes the **original 2017 GST return-filing regime**:
GSTR-1, an interactive GSTR-2 (accept/reject/modify against counterparty-
uploaded invoices), and a consolidated GSTR-3. **This regime was
suspended almost immediately after GST's 2017 rollout and was never
operationalized in production.** What actually exists today — and what
CAOS's PRD (RC-01) already correctly assumes — is GSTR-1, the simplified
GSTR-3B summary return, and GSTR-2B (a static ITC statement, not an
interactive workflow). If this document or the endpoints it describes
(`saveGSTR2`, `fileGSTR3`, etc.) are ever pulled up as a reference during
actual GSP integration work, they describe a filing model that no longer
exists. Kept only as a historical artifact — flagged here so it isn't
mistaken for current guidance.
