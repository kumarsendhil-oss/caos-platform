# ADR 0003 — Document Intake via Dropbox Webhooks with Async Processing

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

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
