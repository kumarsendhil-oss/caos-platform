# ADR 0003 — Amendment 1: Self-Trigger Loop and Correlating Dropbox Deletions

**Status:** Accepted
**Amends:** ADR 0003 (Document Intake via Dropbox Webhooks with Async Processing)
**Date:** 2026-09-17
**Raised by:** the P0-07 Dropbox spike, live — finding #6 (`spikes/p0-07-dropbox/FINDINGS.md`)
**Blocks:** Sprint 3's Document Intake Agent

> ADR 0003's core decision **stands unchanged**. P0-07 confirmed all three of the claims its Status flag listed as doc-verified-only: the webhook → `/files/list_folder/continue` cursor pattern, the 10-second response window, and "App folder" scope behaviour. This amendment adds two implementation-level gaps the original ADR does not cover, both observed live. It is the same shape as ADR 0011 Amendment 2 — a spike surfacing a real gap in an already-Accepted design, not a reopening of the decision.

## Context

### Problem 1 — the app's own writes trigger its own webhook

ADR 0003 describes a one-directional flow: documents arrive in Dropbox, the webhook fires, the agent processes them. It does not consider what happens when the agent **writes back** into the same watched folder — and the Document Intake Agent is expected to, whether that is a processed-document marker, a rename, or a generated working paper.

P0-07 answered this without being asked to. All three triggers in that run were writes made by the spike's **own access token**, against the app's own folder:

| Trigger | Call | Notification delivered? |
|---|---|---|
| 1 | `POST /files/upload` (`add`) | Yes |
| 2 | `POST /files/upload` (`overwrite`) | Yes |
| 3 | `POST /files/delete_v2` | Yes |

Three for three. Dropbox does **not** exempt changes made by the app that owns the webhook. The notification body carries no actor information to distinguish them by, either — the complete payload of every notification is account-level only (`runs/20260917T134329_136_webhook_notify.json`):

```json
{"delta": {"users": [2437473139]}, "list_folder": {"accounts": ["dbid:AAA8TTodwsdEPsIboXYCmA-o2EihjvfnW8U"]}}
```

There is no `changed_by`, no source, no change type. An agent cannot tell "a client uploaded a bill" from "I wrote my own marker file" at notification time. It must call `list_folder/continue` and reason about the *entries* — by which point it has already woken its queue.

Left unhandled, this is a feedback loop: the agent writes, wakes itself, processes its own output, possibly writes again. Whether it terminates depends entirely on whether the processing path happens to be idempotent — which is not a property anyone has designed for here, and not one to rely on by accident.

### Problem 2 — a deletion cannot be correlated by ID

`list_folder/continue` returns rich metadata for a file that was added or modified (`runs/20260917T134406_836_list_folder_continue.json`):

```json
{
  "entries": [
    {
      ".tag": "file",
      "name": "p0-07-test.txt",
      "path_display": "/p0-07-test.txt",
      "path_lower": "/p0-07-test.txt",
      "id": "id:HmlHGAcb3c8AAAAAAAAABQ",
      "rev": "0165ba95df84d02000000038740bda3",
      "content_hash": "dcfbd0a27381b821aadbf2f6cf046d8c112d0fd9a98621ff634bbc8d549f9e85",
      "size": 35,
      "server_modified": "2026-09-17T08:14:04Z"
    }
  ],
  "has_more": false
}
```

A deletion of **the same file** returns this instead (`runs/20260917T134429_879_list_folder_continue.json`):

```json
{
  "entries": [
    {
      ".tag": "deleted",
      "name": "p0-07-test.txt",
      "path_display": "/p0-07-test.txt",
      "path_lower": "/p0-07-test.txt"
    }
  ],
  "has_more": false
}
```

No `id`. No `rev`. No `content_hash`. Path and name only.

This matters because `id:HmlHGAcb3c8AAAAAAAAABQ` is the one identifier that is *stable* under a rename or a move — which is exactly why a document-tracking table would naturally key on it. But the delete notification, the moment at which that key is most needed, is the one place Dropbox does not supply it. A component that stored only the Dropbox ID has nothing to match a deletion against.

## Decision

### 1. Processed output is written outside the watched App folder

Any file the intake pipeline produces — processed-document markers, working papers, renamed or archived copies — is written to a location that is **not** inside the App folder the webhook watches.

The alternative was considered and is described below; this one is chosen because the correctness argument is structural rather than behavioural. A write-back location outside the watched tree cannot cause a self-trigger, because the webhook is scoped to the tree. There is no state to maintain and no way for a later change to quietly reintroduce the loop.

**This is a recommendation Sprint 3 should follow, not a mandate to re-litigate.** If Sprint 3 finds a concrete reason the output must live inside the watched folder — a client-visible workflow that depends on it, say — then option (b) below is the fallback, and the reasoning for preferring (a) is recorded here so that choice is made deliberately rather than by default.

### 2. The rejected alternative, and why it is the fallback rather than the choice

**(b) A `rev`/`content_hash`-based ignore-list.** The handler records the `rev` (or `content_hash`) of every file it writes, and skips notification entries matching a recorded value.

This works — both fields are present on write responses and on `list_folder/continue` entries for added and modified files, so the correlation is available. It is rejected as the primary approach for three reasons:

- **It is a permanent maintenance obligation.** Every future write path into the watched folder must remember to register its `rev`. A write added later by someone who does not know about this amendment silently reintroduces the loop, and the symptom — an agent processing its own output — is not obviously a missing-registration bug.
- **It needs an eviction policy nobody has specified.** The list cannot grow forever, so entries expire; an entry expiring before its notification arrives reintroduces exactly the loop it exists to prevent. That is a race, and races in an intake pipeline surface as intermittent duplicate processing.
- **It does not cover deletions.** Per Problem 2, deleted entries carry no `rev` at all. An agent that deletes a file inside the watched folder cannot suppress its own deletion notification this way. Option (a) has no such hole.

The asymmetry is worth stating plainly: **a separate write-back location has to exist once; an ignore-list has to be maintained correctly forever.**

### 3. Dropbox-sourced document tracking maintains its own path → ID mapping

Whatever component tracks documents sourced from Dropbox — the `DraftEntry`-equivalent document tracking, or a dedicated document-intake table if Sprint 3 introduces one — **persists the mapping from path to Dropbox file ID itself**, populated when the file is first seen (added or modified, where the `id` *is* supplied).

On a deletion, the handler resolves `path_lower` through that mapping to recover the ID, and correlates against its own records by ID from there. `path_lower` is the correct key for the lookup rather than `path_display`, since it is the case-normalised form and Dropbox paths are case-insensitive.

The mapping must be updated on every add/modify notification, not only the first — a file that is deleted and re-uploaded at the same path receives a **new** Dropbox ID, and a stale mapping would correlate the new file to the old document record.

## Consequences

- **Sprint 3's Document Intake Agent gains a required design constraint, not just a caution.** Its output location is now decided rather than left to whoever writes it first.
- **The intake pipeline needs a persisted path→ID store**, maintained as a side effect of processing rather than derived on demand. Dropbox cannot be queried for the ID of a path that no longer exists, so the mapping must be written *before* it is needed.
- **A move out of the App folder may be indistinguishable from a deletion.** P0-07 explicitly did not test this, and flags it as inconclusive. Combined with the missing `id` on deleted entries, the intake agent should not treat a `deleted` entry as proof a document was destroyed — it may have been moved. What the agent does on a deletion (mark inactive vs. delete a record) should be chosen with that ambiguity in mind. This remains open.
- **Nothing to migrate.** No document-intake table exists yet; the Document Intake Agent is Sprint 3. The same timing argument ADR 0011's amendments made applies — this is free now and expensive after the agent is written.
- **ADR 0003's Status flag is updated, not removed.** The three doc-verified-only claims are now live-verified; the flag becomes a record of that verification rather than a pending item.

## What is decided vs. what is deferred

**Decided by this amendment:** that processed output goes outside the watched folder, that the ignore-list is the fallback rather than the default, and that path→ID mapping is the intake component's own responsibility.

**Deferred to Sprint 3:** where exactly the write-back location lives (a sibling folder, a separate Dropbox app folder, or object storage entirely), and which table owns the path→ID mapping. Both depend on the Document Intake Agent's shape, which is not designed yet.

## Open

- **Move-out-of-folder semantics are unverified.** See Consequences. P0-07 did not test it.
- **Retry and back-off behaviour on a slow or failed webhook response is unverified**, and is the larger open question from P0-07 — if Dropbox does not retry, webhook-only intake needs a periodic reconciling `list_folder` sweep as a backstop, which would be a change to ADR 0003's Decision rather than an amendment to it. Worth resolving before Sprint 3 commits.
- **Whether rapid successive changes coalesce into one notification** is unverified; P0-07's triggers were 30+ seconds apart. This affects whether the queue needs de-duplication.

## References

- ADR 0003 — Document Intake via Dropbox Webhooks with Async Processing (`audit-platform-ADR-0003-document-intake-dropbox-webhooks.md`)
- P0-07 finding #6 — Dropbox delivers notifications for changes the app itself made (`spikes/p0-07-dropbox/FINDINGS.md`)
- P0-07 finding #4 — deleted entries carry no `id` or `rev`
- `spikes/p0-07-dropbox/runs/20260917T134329_136_webhook_notify.json` — the account-level notification payload, in full
- `spikes/p0-07-dropbox/runs/20260917T134406_836_list_folder_continue.json` — an added/modified entry, with `id`, `rev` and `content_hash`
- `spikes/p0-07-dropbox/runs/20260917T134429_879_list_folder_continue.json` — the corresponding `deleted` entry, with none of them
- ADR 0011 Amendment 2 (`audit-platform-ADR-0011-amendment-2-state-representation.md`) — the precedent this amendment follows in form and posture
