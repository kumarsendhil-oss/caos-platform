# ADR 0013: HRMS Integration for Internal Staff Management (Frappe HR)

## Status
Proposed

## Context

CAOS's Practice Management Agent tracks staff workload, capacity, and billing, but has no attendance, payroll, or performance-management capability of its own. The practice needs to manage its own internal staff (~10 people: 4 article clerks, 6 paid assistants) — this is internal-only scope, not a client-facing or multi-tenant requirement.

Indian payroll compliance is a large, continuously-changing statutory surface: Provident Fund, ESI, state-wise Professional Tax (different slabs and filing frequencies per state), state-wise Labour Welfare Fund, old/new-regime income tax with marginal relief, and Form 24Q (salary TDS) filing. Unlike GST, which is centrally administered, this compliance layer is federated across 28+ states and changes with each Union Budget.

The same reasoning that shaped ADR 0012 applies here, and applies more strongly: AI-accelerated development compresses implementation time, not the multi-year burden of getting statutory logic right and keeping it current. Building this from scratch means the CAOS team becomes the permanent owner of that maintenance surface.

## Decision

Integrate **Frappe HR** (with its India Payroll extension) as the system of record for HR and payroll compliance, rather than building in-house. Within that integration, ownership splits by component rather than treating this as one blanket build-vs-integrate call:

1. **Payroll & statutory compliance** (PF, ESI, PT, LWF, TDS, Form 24Q, Form 16) — owned entirely by Frappe HR / India Payroll.
2. **Attendance capture** — built natively in CAOS, pushed to Frappe HR's `Employee Checkin` entity via API.
3. **Performance management** — the quantitative signal (task completion, billable utilization) is computed in CAOS from data it already owns and pushed as progress against a Frappe HR Goal/KRA. The qualitative appraisal itself (peer feedback, self-assessment, judgment-based KRAs, appraisal cycles) stays native to Frappe HR.

## Alternatives Considered

**OrangeHRM (Community edition)** — rejected. No India-specific statutory compliance layer; API access and payroll integration are gated behind a paid, proprietary "Advanced" tier.

**Build the full HRMS in-house, AI-accelerated** — rejected for payroll/compliance. Statutory correctness across PF/ESI/PT/LWF/TDS, and the annual maintenance burden as rules change, is not a coding-speed problem — the same class of bottleneck identified for GST/TDS in ADR 0012.

**Build attendance and performance management in-house too** — rejected for performance management, accepted for attendance. Frappe HR's KRA/appraisal/360°-feedback engine is mature and carries no compliance burden to justify rebuilding. Attendance is different: it's a bounded, no-compliance-risk feature with daily-use UX value in keeping staff on one app.

**Use Frappe HR's own mobile PWA for attendance instead of building in CAOS** — rejected. Forces staff into a second app for a daily action, and Frappe's native geolocation capture lacks geofencing (location enforcement) — a gap CAOS can close by building this piece itself.

## Integration Architecture

- Frappe HR runs as a **separate service** (Python/Frappe Framework, MariaDB — not CAOS's Supabase/Postgres stack), self-hosted via Docker or on Frappe Cloud (~₹800/month).
- CAOS integrates via Frappe's auto-generated REST API (API key/OAuth2), following the same adapter pattern established in ADR 0011 for Tally/Zoho.
- **Attendance**: CAOS captures check-in/out and GPS coordinates from its own interface, applies geofencing validation itself, then posts to Frappe HR's `Employee Checkin` entity. Frappe's existing shift rules, auto-attendance, and payroll linkage consume this unchanged.
- **Performance**: CAOS computes utilization/billing metrics per employee from task-engine data it already owns, and pushes progress updates against a designated Goal (e.g., "Billable Utilization") via Frappe HR's `Goal` entity, which auto-feeds the linked KRA score. Qualitative KRAs remain manually scored inside Frappe HR's appraisal cycle.
- **Form 24Q** (salary TDS) is owned end-to-end by Frappe HR / India Payroll. CAOS's existing TDS/TCS Return Automation Agent narrows to 26Q/27EQ (non-salary TDS) and reflects 24Q filing status for dashboard visibility only — avoiding duplicate logic between the two systems.

## Consequences

**Positive**
- Avoids taking on permanent ownership of India's federated payroll compliance surface.
- Real-world cost is low relative to any in-house build: self-hosted is free, or ~₹800/month on Frappe Cloud; implementation partners quote ~₹50,000 fixed-price with a 3-week go-live for full statutory setup.
- Staff use one app (CAOS) for daily attendance rather than switching to a second mobile PWA.
- Performance appraisal gets an objective, task-derived quantitative signal without losing the qualitative judgment a metrics-only system would strip out.
- CAOS ends up with a genuinely better attendance feature than Frappe ships natively, since geofencing is CAOS's to build.

**Negative / Risks**
- New infrastructure dependency: a separate MariaDB-backed service to host and back up, outside the existing Supabase/Postgres/Railway stack — not yet reflected in the Section 9 recurring cost model.
- Employee ID mapping between CAOS and Frappe HR must stay in sync; drift breaks attendance posting.
- CAOS must be enforced as the sole check-in surface — a dual path (CAOS + Frappe's own app) would produce duplicate or conflicting attendance logs.
- Licensing: Frappe HR/ERPNext is GPL-3.0 (the underlying framework is MIT). Consuming it as a separate service over its REST API should not obligate CAOS's own codebase, since it's GPL rather than AGPL — but this needs confirmation from counsel before production use, not assumption.
- Frappe's native geolocation has reported mobile GPS accuracy variance and lacks per-employee toggle granularity as of last check — largely moot given CAOS owns its own capture path, but worth a quick Phase 0 sanity check.

## Scope Note

This decision assumes internal-only usage (~10 staff at the practice). If CAOS is later offered to other CA practices as a multi-tenant product, HRMS integration becomes a per-tenant Frappe HR instance or a tenant-isolated design — out of scope here, flagged for future revisit.

## Open Items for Phase 0

- Confirm Frappe HR hosting choice (self-hosted Docker vs. Frappe Cloud) and add the line to the Section 9 recurring cost model.
- Confirm the GPL-3.0/AGPL distinction with counsel before production use.
- Define the exact Goal/KRA name(s) CAOS will feed automatically (e.g., "Billable Utilization", "Task Turnaround Time"), in coordination with the practice's appraisal template design.
- Test mobile GPS accuracy for CAOS's own geofenced check-in during Phase 0/1.
