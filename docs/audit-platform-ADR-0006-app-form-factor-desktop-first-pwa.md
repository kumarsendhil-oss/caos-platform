# ADR 0006 — App Form Factor: Desktop-First PWA

> Extracted verbatim from the consolidated *CAOS Internal Development
> Readiness Package* (v0.1.1, 2026-08-16) into an individual file, so
> that cross-references from the codebase and `CLAUDE.md` resolve to a
> readable document. Content is unchanged from the source PDF; only
> layout has been reflowed to markdown.

---

## Status

Accepted

## Context

Staff primarily work at a desktop with a monitor, not on mobile. PWAs are often built mobile-first by default, which would be the wrong assumption here.

## Decision

Build as a PWA accessible both through a regular browser tab and as an installed application, with a desktop-first responsive design. Wide, multi-column layouts (dashboard, task queue, client workspace) are the primary target; mobile is a secondary, fully-functional but reflowed layout, not the primary design constraint.

## Consequences

- Frontend component and layout decisions (in the eventual frontend/design work) should be evaluated at desktop breakpoints first, with mobile treated as a reflow rather than the base case.

- PWA capabilities (offline task queue, push notifications) remain available for any staff member who does install it or checks tasks on mobile, without constraining the primary desktop experience.

## Alternatives considered

- Mobile-first PWA design — rejected; would fit the COCA reference project’s field-worker context, but not this practice’s desk-based staff.
