# ADR 0009 — Deployment Model: Single-Tenant, Per-Customer Instances

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

The platform is being built for the first customer (Venture Assist / Srivatsan & Associates) but is planned to roll out to other CA practices once this deployment succeeds. The initial instinct was to design for multi-tenancy (shared infrastructure, tenant isolation via a practice-level entity above CLIENT, row-level security). The customer clarified this is explicitly not the model: each future practice gets a fully separate deployment, not a shared multi-tenant platform.

## Decision

Build and deploy as single-tenant, one full stack (app, database, connectors) per practice. No tenant/practice entity is added above CLIENT in the data model — the ER diagram (§ audit-platform-ER-*.mermaid) stays as originally designed. Each practice’s Tally connection, GSP credentials, service catalog, and branding are deployment-specific configuration, not shared or tenant-scoped data.

## Consequences

- No data-model change needed — the existing ER diagrams and PRD module list are correct as-is; the earlier suggestion to add a PRACTICE tenant layer is retracted.

- Data isolation is structural, not app-enforced — separate databases per deployment means no risk of cross-practice data leakage from an application bug, which is a stronger position than row-level security under DPDP scrutiny.
- The real engineering shift is toward repeatable deployment, not tenant isolation. Infrastructure-as-code (e.g. Terraform) should be adopted from this first deployment, even though there’s only one instance today — hand-configuring AWS Mumbai once is fine; hand-configuring it identically for a second, third,

and fourth customer is not.

- The Dev Readiness Checklist (still pending, per the Documentation Roadmap) should be written as a reusable “new practice deployment” runbook, not a one-time setup document — since it will literally be re-run for each new customer.
- An update/patch strategy across multiple live deployments needs deciding, even at small scale (2-3 customers). Options range from manual redeploy per instance to a proper CI/CD release pipeline pushing to all instances. Worth deciding this now, while only one deployment exists, rather than retrofitting a release process once several are live and drifting apart.
- Per-deployment configuration must be cleanly separated from code — Tally connection details, GSP credentials, service catalog, and any branding differences belong in environment/config, not hardcoded, so the same codebase deploys to a new environment without code changes.
- Branding/white-labeling is naturally simple under this model, since nothing is shared between deployments — no additional design work needed to support per-practice branding if that’s ever wanted.
- Infrastructure cost scales linearly per customer (each deployment needs its own hosting and OCR compute) rather than being amortized across tenants — worth factoring into how future customer pricing is structured, though that’s a business decision outside this ADR’s scope.

## Alternatives considered

- Multi-tenant shared platform — this was the initial direction explored based on an assumption about the rollout plan; explicitly rejected once the customer clarified the actual model. Retained here as a considered-and-rejected alternative since the reasoning (tenant entity, RLS, shared GSP) is real work that would have been wasted if built.
