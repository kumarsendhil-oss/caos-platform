# ADR 0003 — Document Intake via Dropbox Webhooks with Async Processing

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

> **✅ Live-verified by P0-07 on 2026-09-17. Amended by Amendment 1.**
>
> This block previously flagged the decision as doc-verified only. **P0-07** (`spikes/p0-07-dropbox/`) has now run against a real App-folder-scoped Dropbox app, and all three specifics it listed as unobserved are confirmed:
>
> - **The webhook → `/files/list_folder/continue` cursor pattern works as documented.** The notification carries no file detail whatsoever, and `continue` returns exactly the delta. The cursor genuinely advances — a second notification returned only its own change, not a re-listing.
> - **The 10-second response window is real, and acknowledgement is effectively free** — measured at 0.378–1.067 ms across three notifications, 0.004%–0.011% of the window. The queue/worker requirement in Consequences stands: the limit constrains inline *work*, not acknowledgement.
> - **"App folder" scope returns app-relative paths** (`/p0-07-test.txt`); the `/Apps/<name>/` prefix never appears.
>
> The spike also surfaced two gaps this ADR does not cover — Dropbox notifies on the app's **own** writes, and `deleted` entries carry no `id` or `rev`. Both are resolved in **[Amendment 1](audit-platform-ADR-0003-amendment-1-webhook-loop-and-deletes.md)**, which refines implementation-level design without reopening the decision.
>
> Two questions remain unverified and are tracked in Amendment 1's Open section: **retry/back-off behaviour on a slow or failed response** (the more consequential — if Dropbox does not retry, webhook-only intake needs a reconciling sweep as a backstop), and **move-out-of-folder semantics**.

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
