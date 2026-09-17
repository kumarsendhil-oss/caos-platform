# ADRs 0001–0010 — Open Items

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

These were recorded as still-undecided at the time the original ADR set
was written. Check them against later ADRs (0011, 0012) and the Dev
Readiness Checklist before treating any as still open.

---

- DPDP Act specific obligations for the platform’s own metadata layer — needs legal/compliance input.
- PaddleOCR accuracy validation against a representative sample of real practice documents (20-50 invoices across vendor formats) — needed before ADR 0008 can be considered fully proven in practice, not just sound in theory.
- ~~Infrastructure-as-code tooling choice (Terraform vs. alternatives) for repeatable per-practice deployment, per ADR 0009.~~ **CLOSED 2026-09-17 — ADR 0014:** lightweight Terraform, scoped to ADR 0007's existing infrastructure; Fargate remains rejected.

ER Diagram — Practice Automation Platform Prepared for Venture Assist / Srivatsan & Associates | Draft v0.1

Changelog Version                          Date                             Summary v0.1                             2026-08-16                       Initial entity model, split into two diagrams (core platform, compliance & billing) per the PRD’s 14 modules. Sources: audit-platform-ER- core.mermaid, audit-
