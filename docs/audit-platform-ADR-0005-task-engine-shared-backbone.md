# ADR 0005 — Task Engine as the Shared Backbone

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

Customer feedback was explicit: any human-touch step across any agent must become a task assigned to a specific person with a due date — not a generic notification or flag. Internal deadlines are currently missed due to inconsistent follow-through (a discipline gap), not tool resistance.

## Decision

Every agent-raised exception or judgment call writes to a shared Task Engine, not to its own notification channel. The Task Engine owns: task type, linked record/context, client, due date, assignee (via a configurable routing rule table), status lifecycle (Open → In Progress → Completed/Escalated), and auto-escalation when a task passes its due date. All other modules (dashboard, per-user queues, client workspace) read from this same engine rather than maintaining their own task state.

## Consequences

- This is a dependency every other module has on the Task Engine being built early — it should be in Phase 1, not a later add-on.

- The routing rule table (task type → default assignee/role) is a real design artifact that needs to be built deliberately, ideally in collaboration with the proprietor, so that routine tasks land on junior/senior staff rather than

defaulting to the proprietor and defeating the purpose.

- Escalation logic directly addresses the discovery finding about inconsistent follow-through — this is a deliberate enforcement mechanism, not just a convenience feature.

## Alternatives considered

- Per-agent notification systems — rejected; this is what the customer explicitly asked to move away from, and it would fragment task visibility across modules instead of giving the proprietor one place to see practice-wide load.
