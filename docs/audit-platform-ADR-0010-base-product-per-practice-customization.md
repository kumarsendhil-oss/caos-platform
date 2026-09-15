# ADR 0010 — Base Product with Per-Practice Customization and Upstream Promotion

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

ADR 0009 established single-tenant, per-practice deployments and flagged the update/patch strategy across multiple live instances as an open item. The customer clarified the model directly: build one “base product” and deploy customized versions per practice, with generalizable customizations pushed back into the base so future (and ideally existing) deployments benefit.

## Decision

Maintain a single base product codebase as the source of truth for all generic, reusable functionality — every agent, the task engine, and the PWA screens defined in the PRD. Each practice’s deployment starts from the base and layers on customization only where genuinely necessary. When a customization proves broadly useful rather than specific to one practice’s idiosyncrasy, it gets generalized — typically as a configuration option, not hardcoded logic — and merged back into the base, so future deployments inherit it and existing deployments can adopt it.

## Practical structure

- Configuration is the default and cheapest form of customization. Per ADR 0009, Tally connection, GSP credentials, service catalog, and branding already live in config, not code — this is customization that was never divergent in the first place, so it never needs “pushing back.”

- Where code-level customization is genuinely needed, isolate it behind clear extension points (e.g. a defined hook/plugin pattern, or a

practices/{practice-name}/ override directory) rather than editing core modules directly. This keeps the base/customization boundary legible and makes eventual promotion to base a clean extraction rather than an untangling exercise.

- A lightweight periodic review of practice-specific customizations for generalization candidates should be part of the ongoing process — this is what actually makes the “push to base” half of the model happen, rather than customizations quietly accumulating as one-off technical debt.

## Consequences

- Resolves the update/patch strategy open item from ADR 0009 — updates to the base flow to existing practice instances the same way any software update would, since deployments aren’t meant to diverge arbitrarily from it.

- Requires real discipline to keep the boundary clean: if practice-specific edits get made directly against core modules without going through an extension point, future base updates become risky to apply (merge conflicts, silent breakage) — this is the main way the model fails in practice.
- The extension-point pattern needs concrete definition — actual code structure, not an abstract principle — before the second deployment happens. Worth doing this during or immediately after the first deployment build, not designing it in the abstract now with no real customization yet to learn from.
- The Dev Readiness Checklist (still pending) should include defining this extension-point structure as an explicit task, since it’s foundational to every deployment after the first.

## Alternatives considered

- Per-practice long-lived forks with manual cherry-picking — simplest at 1-2 practices, but merge/rebase overhead compounds with each additional deployment and risks silent drift between instances. Rejected as the primary strategy, though it may resemble what happens informally at very small scale before proper tooling is in place. - Fully generic base with no practice-specific customization allowed — rejected as unrealistic; some practices will have genuine one-off needs (a specific report format, an unusual workflow quirk) that don’t belong in the base product for every customer. The extension-point pattern accommodates this without contaminating the base.
