# ADR 0003 — Document Intake via Dropbox Webhooks with Async Processing

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

> **⚠ Doc-verified only — live verification pending via P0-07.**
>
> This is a flag, **not a reversal**: the decision stands, and nothing below is known to be wrong. The Context section records that Dropbox's webhook model "was verified against their own API documentation" — which is real verification, but on this project it has twice proved insufficient on its own. **P0-06 finding #6** found Zoho's own published example contradicting its live API, and **P0-04** found WhiteBooks' marketing contradicting their own onboarding documentation.
>
> Three specifics here are taken from documentation and have never been observed: the **webhook → `/files/list_folder/continue` cursor pattern** (the notification carries no file detail, so the whole intake design rests on this loop), the **10-second response window** (which drives the queue/worker requirement in Consequences — an architectural commitment, not a tuning parameter), and **"App folder" scope behaviour** (chosen deliberately over Full Dropbox, but what a cursor reports under it is unobserved).
>
> **P0-07** (`spikes/p0-07-dropbox/`) exists to check all three against a real Dropbox app, before Sprint 3 builds the Document Intake Agent against them as given. Scaffolded 2026-09-17; **not yet run** — it needs a Dropbox dev app and a publicly reachable URL. If it finds a gap, the correction belongs in an amendment, in the shape of ADR 0011 Amendment 1.

## Context

Client documents arrive by email, are (currently manually) filed into Dropbox, and need to trigger downstream processing (OCR, classification, bookkeeping). Dropbox’s webhook model was verified against their own API documentation.

## Decision

Use Dropbox webhooks to detect account-level changes, followed by /files/list_folder/continue with a stored cursor to identify the specific changed files. The webhook handler acknowledges within Dropbox’s 10-second response window and hands off actual processing (fetch, download, OCR trigger) to a background queue — never processed inline. Request “App folder” scope for the platform’s Dropbox API app, rather than “Full Dropbox” access, scoping the platform to its own designated folder tree given the practice’s Dropbox holds the entire company’s client data.

## Consequences

- Requires a queue/worker architecture from the start, not just a webhook endpoint — this is a concrete infrastructure requirement, not an optional enhancement.

- App folder scoping is a meaningful, low-cost step toward the data-minimization principle established in ADR 0005.
- The Email Intake Agent (which files documents into Dropbox in the first place) and the Document Intake Agent (which watches Dropbox for changes) are two distinct agents with a clean handoff point — worth keeping that separation clear in the eventual ER diagram and API spec.

## Alternatives considered

- Polling /files/list_folder on a schedule — rejected as inefficient and higher-latency compared to webhooks; Dropbox’s own guidance discourages rapid polling for server-side apps.

- Processing synchronously inside the webhook handler — rejected; violates the 10-second response constraint for anything beyond trivial payloads.
