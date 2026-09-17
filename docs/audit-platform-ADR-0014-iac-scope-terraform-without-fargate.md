# ADR 0014 — Infrastructure-as-Code Scope: Terraform Without Fargate

**Status:** Accepted
**Date:** 2026-09-17
**Reconciles:** ADR 0007 (Technology Stack) and ADR 0009 (Deployment Model — Single-Tenant, Per-Customer Instances)
**Relates to:** ADR 0010 (Base Product + Per-Practice Customization)
**Resolves:** the open IaC-tooling item in the Phase 0 list of `CAOS-sprint-plan-v0.2.md` and in `audit-platform-ADR-0001-0010-open-items.md`

## Context

Three earlier ADRs are individually sound and collectively ambiguous about whether this project uses infrastructure-as-code.

**ADR 0009 committed the project to one deployment per customer.** Its own consequences say infrastructure-as-code "should be adopted from this first deployment, even though there's only one instance today," on the reasoning that hand-configuring AWS Mumbai once is fine but hand-configuring it identically for a second and third is not.

**ADR 0010 committed the project to multiple such deployments over time**, as new practices onboard onto a shared base product with per-practice customization.

**ADR 0007 appeared to reject the tooling for exactly that**, listing as a rejected alternative the "Full COCA-equivalent stack (AWS ECS Fargate + Terraform + Turborepo) — still rejected as disproportionate to this project's scale and budget," and describing AWS Mumbai as allowing "a lightweight setup (a single EC2 instance or small ECS setup) without Fargate/Terraform-level complexity."

So one ADR says adopt IaC from day one, and another appears to reject it. That contradiction is why the IaC decision has sat open on the Phase 0 list rather than being made.

### The actual go-to-market plan, which settles it

Confirmed directly: **one practice goes live first, then the product is pitched to multiple audit firms, each hosted individually.** Each firm is modest internally — roughly 10–50 staff and 500–600 clients. What grows with each signed customer is not the load inside any one deployment; it is **the number of separate deployments to keep consistent.**

### The bundling error

ADR 0007's phrase "Fargate/Terraform-level complexity" treats two genuinely separate things as one:

| | What it is | Cost it carries |
|---|---|---|
| **Fargate** | A specific, more complex container-orchestration service | Real operational and cognitive overhead: task definitions, service discovery, scaling policies, a networking model to learn |
| **Terraform / IaC** | The general practice of describing infrastructure in version-controlled config rather than clicking through a console | Mostly up-front authoring; near-zero per-deployment thereafter |

They do not have to be adopted or rejected together, and the reasons for rejecting one do not apply to the other. ADR 0007's rejected alternative was the **COCA-equivalent bundle** — Fargate *and* Terraform *and* Turborepo, together — and the parenthetical in the hosting row generalised that into an apparent rejection of Terraform on its own. That generalisation is what this ADR corrects.

## Decision

### 1. Adopt lightweight Terraform, scoped exactly to the infrastructure ADR 0007 already specified

A single EC2 instance (or a small non-Fargate ECS setup), RDS or self-hosted Postgres, security groups, and DNS. **Nothing here changes what is provisioned.** It changes only how: described in code and version-controlled, rather than configured by hand in a console.

### 2. Do NOT adopt Fargate

ADR 0007's reasoning — that Fargate-level orchestration is disproportionate to one practice's actual load of 10–50 staff and 500–600 clients — **stands unchanged and is explicitly reaffirmed here, not revisited.** This ADR narrows ADR 0007's rejection to what it was actually arguing against; it does not overturn any part of it.

### 3. Why IaC despite modest per-instance scale

This is the part worth stating carefully, because "we're small, we don't need Terraform" is the intuitive objection and it answers the wrong question.

**The risk IaC addresses here is not scale within one deployment. It is consistency across repeated deployments.** Hand-configuring firm #1's environment carefully is genuinely fine. By firm #5, manual setup drift — a security-group rule, an environment variable, a Postgres parameter — becomes a real and *undocumented* liability, with no record of what differs between instances or why. The failure mode is not an outage under load; it is a bug that reproduces on one customer's instance and not another's, with nothing to diff.

That is the textbook case IaC exists to solve, and per the go-to-market plan above it is **this project's actual business model, not a hypothetical future scale concern.** ADR 0009 reached the same conclusion from the same premise; this ADR simply removes the tooling objection that appeared to block it.

Note also that single-tenancy (ADR 0009) *increases* this need rather than reducing it. A multi-tenant product has one production environment to get right. This one has as many as it has customers.

## Consequences

- **A `terraform/` module needs to exist before the second practice's deployment, and ideally before the first.** Doing it first means day-one setup establishes the pattern; doing it later means retrofitting a description onto an environment that was built by hand — which requires first discovering what was actually built, the exact problem this is meant to avoid.
- **The "lighter than COCA" principle from ADR 0007 is preserved**, not weakened. This is Terraform provisioning a small, simple setup — not Fargate, not Turborepo, not the full COCA-scale stack. If the Terraform grows to resemble COCA's, that is a signal to re-examine, not a goal.
- **Per-practice customization (ADR 0010) becomes easier to reason about** once the base environment is code rather than tribal knowledge. The difference between two practices' infrastructure becomes a readable diff, which is also what makes per-practice customization auditable rather than accidental.
- **Terraform state needs a home and a locking story** before more than one person or process runs it. Remote state in S3 with DynamoDB locking is the conventional answer at this scale; it is a small decision, but it is one that gets painful if deferred until two deployments already exist.
- **Someone has to learn enough Terraform**, which is a real if modest cost and lands on a team with no dedicated DevOps line item (per ADR 0007's own budget framing). Scoped to a handful of resources, this is days, not weeks — and it is bounded precisely because Fargate is out of scope.
- **Secrets stay out of Terraform state.** Per CG4 and Security Standard §3, credentials live in Secrets Manager; Terraform provisions the *reference*, never the value.

## Alternatives considered

**No IaC — hand-configure each new practice.** Rejected. It offers no drift protection and no record of what differs between environments, and it degrades precisely as the multi-firm pitch plan succeeds. It is also the option that looks cheapest at firm #1 and costs the most at firm #5, which is the shape of decision worth making early rather than late.

**Full Fargate + Terraform + Turborepo (COCA-equivalent).** Rejected, for the same reason ADR 0007 already gave and which this ADR reaffirms rather than re-litigates: disproportionate to per-practice scale (10–50 staff, 500–600 clients per instance), on a cost-sensitive budget with no dedicated DevOps.

## References

- ADR 0007 — Technology Stack (`audit-platform-ADR-0007-technology-stack.md`): the hosting decision and the rejected COCA-equivalent bundle
- ADR 0009 — Deployment Model, Single-Tenant Per-Customer Instances (`audit-platform-ADR-0009-deployment-model-single-tenant.md`): the "adopt IaC from the first deployment" consequence
- ADR 0010 — Base Product + Per-Practice Customization (`audit-platform-ADR-0010-base-product-per-practice-customization.md`): why there is more than one deployment
- `audit-platform-ADR-0001-0010-open-items.md` — where the IaC tooling choice was recorded as open
- `CAOS-sprint-plan-v0.2.md` — Phase 0, where it gated Sprint 1
