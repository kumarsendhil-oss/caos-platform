# ADR 0015 — Amendment 1: Blocked State and `blocked_reason`

**Status:** Proposed
**Amends:** ADR 0015 (Engagement and Task Model Redesign)
**Date:** 2026-09-21
**Raised by:** `PENDING:032` — the customer-facing documentation describes task waiting states that no ADR proposes
**Resolves:** ADR 0015's Follow-up deferral of the blocked state and `blocked_reason`

> This fills a gap ADR 0015 marked as its own. Its Follow-up section, under
> *Deferred out of this pass, from Decision 4*, says: **"Add a blocked state and
> `blocked_reason` to `TASK`. Decision 4's blocked clock presupposes both; neither exists
> in `STATUSES` or on the model, and no Decision in this ADR adds them. Not proposed
> here."** Nothing in 0015's Decision text changes. This amendment adds what Decision 4
> already assumed.

## Context

ADR 0015 Decision 4 specifies two clocks, and the second one has no state to measure:

> | **Blocked duration**, segmented by `blocked_reason` | time between the transition into a blocked state and the transition out | **task time** | cycle time, and where the time went — client bottleneck vs. internal |

`STATUSES` is `("open", "in_progress", "completed", "escalated")` (`services/api/app/models/task.py:22`). There is no blocked member, no `blocked_reason` column, and 0015's own revised `TASK` fragment still lists `status` as `open | in_progress | completed | escalated`. The metric is defined over a state that does not exist.

**The pressing reason to settle it now is not internal consistency.** `CAOS_Feature_Documentation_v0_6.docx` — "Task Management & Practice Measurement" — **has been shared with the practice**, and it describes this behaviour to the customer:

- Time is derived from "when someone starts a task, **when they pause it and why**, when they finish it."
- "Time the task was waiting — The stretch where nobody could act on it."
- "When a task cannot move forward, the reason will be recorded — **principally** whether it is waiting on the client or waiting on a system."

So the customer is reading a description of task states that no accepted ADR covers. That inverts this project's normal direction, where an ADR settles a thing and the customer-facing documents follow. `PENDING:032` records it.

**ADR 0015 being Accepted does not resolve this.** An accepted ADR that defers a decision has deferred it just as firmly as a proposed one did.

## Options considered

**Option A — `blocked` becomes a fifth member of `STATUSES`.**
`open | in_progress | blocked | completed | escalated`. Entering blocked is a status transition like any other, and the blocked clock reads the same transition history the in-progress clock reads.

**Option B — a flag or interval orthogonal to `status`.**
The task keeps its status and gains a separate blocked marker, so a task could be `in_progress` and blocked simultaneously. Blocked duration would come from its own event stream rather than from status transitions.

**Option C — a dedicated `TASK_BLOCK` interval entity.**
One row per blocking episode, with `started_at`, `ended_at` and `reason`. Explicit, and queryable without reconstructing state from transitions.

## Decision

**Option A.** `blocked` is a fifth member of `STATUSES`:

```
open | in_progress | blocked | completed | escalated
```

### 1. Why a status member and not an orthogonal flag

**It is what makes the two-clock split computable.** Decision 4 derives both clocks from status transitions and decided those transitions get one dedicated table. Option B needs a second event stream for the second clock, so the two clocks would no longer be two readings of one history — they would be two mechanisms that have to be kept consistent with each other.

**It protects the one-in-progress-per-user invariant, which Decision 4 calls load-bearing.** Under Option B a task could be `in_progress` and blocked at once, accruing effort time while nobody can act on it. That is precisely the arithmetic Decision 4 rejects: "each accrues full wall-clock over the same interval, their sum exceeds the elapsed period, and measured utilisation exceeds 100%." As a status member, entering blocked necessarily leaves `in_progress`, so the effort clock stops. **This is the decisive argument**, and it is the one that also makes the effort clock comparable to `standard_minutes`, per Decision 4's own correction.

**It matches the model the customer has already been given.** v0.6 describes pausing a task and saying why. A pause is a change of state, not an annotation on an ongoing one.

**ADR 0015 already does this at the sibling grain.** `ENGAGEMENT.status` is `planned | active | blocked | complete | cancelled`. Making `TASK`'s blocked a flag while `ENGAGEMENT`'s is a status would be an unexplained asymmetry inside one ADR.

**Option C rejected** for the reason 0015 rejected a separate `SUBTASK` entity, and for one more: a `TASK_BLOCK` table is a second, partial record of state transitions alongside the transition table Decision 4 already decided on, so the two could disagree about whether a task is currently blocked. Decision 4's table is the single history; blocked intervals are a projection of it, not a parallel record.

### 2. `blocked_reason` — two places, one authoritative

**On `TASK`:** `blocked_reason`, nullable, the **current** reason, for display in the queue.

**Invariant:** `blocked_reason` is non-null if and only if `status = 'blocked'`. Leaving blocked clears it.

**On the into-blocked transition row:** the same reason, recorded at the moment of the transition. **This is the authoritative record and the one Decision 4's "segmented by `blocked_reason`" reads.**

The split matters and is easy to get wrong. A task can block twice for different reasons — waiting on a client document, then later on a system. The current column holds only the most recent, so attributing intervals from it would charge every interval to the last reason the task happened to carry. **Segmentation must read the transition rows.** The column on `TASK` is a denormalised convenience for the queue view, and nothing that computes a metric should read it.

### 3. The vocabulary is exactly two values

```
waiting_on_client | waiting_on_system
```

These are the two the customer documentation names, and **no third value is proposed here.** Whether these two are the complete vocabulary or the first two of a longer list is a **customer decision, not one to infer** — the vocabulary came from the 2026-09 customer review, as did the v0.6 wording it appears in. Two questions go to the proprietor; see **Questions for the practice** below.

### 4. Setting the reason: manual now, and manual permanently

**The reason is set by a person at the moment of blocking.** v0.6 says the reason "will be set by hand to begin with — someone pauses the task and says why. It becomes automatic later, once the client communication module is tracking outstanding requests directly (Sprint 6); the manual version is the starting state, not a fallback."

**Decided: manual setting remains supported permanently, and automation never becomes the only path.** That is what "not a fallback" means, and it is CG8 applied — deciding why a task cannot move forward is a judgement, and a judgement the platform cannot make belongs to a person.

**What automation would look like is not decided here.** See Open questions; four distinct things are unsettled and none of them should be inferred from the sentence above.

### 5. What this does not change

- **`due_at` does not pause while a task is blocked.** Decision 4 decided this and v0.6 states it to the customer ("a statutory due date does not move because a client is slow"). Unchanged.
- **The status-transition table stays unspecified.** Decision 4 decided in principle that it is a dedicated table and not `AuditEvent`; its columns, write path and the `open -> in_progress` transition method remain 0015 Follow-up items. This amendment adds a status and a reason, and takes no position on the table's design beyond requiring that it carry the reason on an into-blocked transition.
- **No ER diagram edit is made here.** The diagram updates are already listed in 0015's Follow-up; `blocked` and `blocked_reason` join that list.

## Consequences

- **`STATUSES` gains a member, and every consumer that enumerates statuses must handle it.** Today that is `services/api/app/models/task.py:22` and the queue and API-spec surfaces that mirror it. Cheap now: no code sets `in_progress` either, so the status machine has no implementation to migrate.
- **A blocked task is not in anyone's active workload, but it is still somebody's responsibility.** The queue view has to show blocked tasks distinctly rather than hiding them — a task waiting on a client that nobody ever looks at again is the failure mode this whole measurement exists to surface.
- **The blocked clock cannot be computed until the transition table exists.** This amendment makes the metric well-defined; it does not make it available. Both depend on 0015's deferred transition-table design.
- **`blocked_reason` is a new required input at block time**, so the UI needs a reason prompt on the pause action. v0.6 already commits to this ("someone pauses the task and says why").
- **The escalation interaction is an implementation gate.** See Open questions — the blocked status must not be implemented before it is settled.
- **This is the first Proposed ADR in the index since 0015 and 0016 were accepted on 2026-09-21**, so the statement that no ADR in the index is Proposed no longer holds.

## What is decided vs. what is deferred

**Decided:** that `blocked` is a status member rather than an orthogonal flag; that the reason is authoritative on the into-blocked transition and denormalised on `TASK`; the non-null-iff-blocked invariant; that the vocabulary is `waiting_on_client` and `waiting_on_system` today; that reasons are set manually and that manual setting is permanent.

**Deferred:** whether the vocabulary is extensible and what the answer implies; the entire automation design; the escalation interaction; the transition table's shape; the ER diagram edits.

## Open questions

**1. Blocked versus escalated — must be settled before the blocked status is implemented.**

`TaskEngine.escalate_overdue()` sets `task.status = "escalated"` unconditionally on any overdue task (`services/api/app/task_engine/service.py:131`). Because `due_at` does not pause while a task is blocked, a blocked task that passes its due date would be moved out of blocked. Under the invariant in Decision 2 above, leaving blocked clears `blocked_reason`, and under Decision 4's definition — "time between the transition into a blocked state and the transition out" — the transition to `escalated` **is** an out-transition, so the blocked interval ends there. The recorded wait would be shorter than the real one, and a task escalated while still waiting on a client would read as no longer waiting.

**This amendment does not decide how escalation interacts with blocked.** Three options, none chosen:

| Option | What it does | Cost |
|---|---|---|
| (a) `blocked -> escalated` ends the blocked interval | Consistent with the invariant and with Decision 4 as written; no change to TE-04 | **Understates the wait.** The interval that matters most — a task overdue *because* it is still waiting — is the one truncated |
| (b) Escalation becomes a flag orthogonal to `status` | Cleanest model: accountability and workflow state stop competing for one column, and a task can be both blocked and escalated, which is what is actually true | Changes what `escalated` means in **ADR 0005 / TE-04**, and touches the escalation ladder and every consumer that reads `status = 'escalated'` |
| (c) `escalate_overdue()` raises the escalation without a status change for blocked tasks | Preserves the blocked clock with a narrower change than (b) | Still a **TE-04 change**, and leaves TE-04 with two different behaviours depending on the task's status |

**This is an implementation gate, not a live defect.** No blocked status exists in code today, so `escalate_overdue()` is correct for the statuses that do exist and needs no change now. It becomes wrong the moment `blocked` is added. Tracked as **`PENDING:035`**; settling it needs a decision reaching into ADR 0005 and TE-04, which is why it is not made here.

**2. Automation of the reason** — four things v0.6's Sprint 6 sentence does not settle:
- Which client-communication event would set `waiting_on_client`. An outstanding-request record being created is the obvious candidate, but CC-01/CC-02 are not specified to that grain.
- Whether that event **blocks the task automatically** or only pre-fills the reason on a human-initiated block. These grant very different amounts of authority.
- Whether the inverse holds — does a client reply **auto-unblock**? This is the riskier half: auto-unblocking a task nobody has looked at silently restarts the effort clock against whoever holds it.
- What could ever set `waiting_on_system` automatically. v0.6 names a mechanism for the client case only.

**3. The vocabulary questions**, below — customer input, not an engineering decision.

## Questions for the practice

Both are for the proprietor. Neither is answered here, and neither should be inferred.

1. **Are `waiting_on_client` and `waiting_on_system` the complete list, or the first two of a longer one?** The customer documentation says the reason will be recorded "**principally**" as one of these two, which does not claim they are exhaustive — so the document is compatible with either answer, and the question is genuinely open rather than already settled by what the practice has been sent.
2. **Is the absence of an internal waiting reason deliberate?** The two values partition by who can fix the problem — the v0.6 text says "only one of them is anyone at the practice's to fix." Waiting on a colleague, on a review, or on the proprietor's sign-off falls into neither: it is not the client, and it is not a system. If that kind of wait should be measurable, the vocabulary needs to cover it; if it should be counted as active work rather than waiting, it should not. **This amendment does not propose a value for it** — the answer determines whether one is needed.

## References

- ADR 0015, Decision 4 (the two clocks and the blocked clock's definition) and Follow-up (the deferral this amendment resolves)
- ADR 0005 (Task Engine as the Shared Backbone) — TE-04, the escalation behaviour Open question 1 would touch
- `PENDING:032` — the customer-documentation-ahead-of-decision gap this amendment addresses; stays Open until this is Accepted and the vocabulary question is answered
- `PENDING:035` — the blocked-versus-escalated collision
- `PENDING:027` — sequencing of the time-measurement area; related, and deliberately untouched here
- `CAOS_Feature_Documentation_v0_6.docx`, "Task Management & Practice Measurement" — the customer-facing wording this reconciles against
- `services/api/app/models/task.py:22` (`STATUSES`), `services/api/app/task_engine/service.py:131` (`escalate_overdue`)
