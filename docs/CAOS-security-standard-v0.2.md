# Security Standard — Practice Automation Platform
### v0.2

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial standard: authentication/session rules, role-based authorization enforcement, secrets handling, encryption, audit-trail immutability, input validation, dependency scanning, and GSP-call rate limiting. |
| v0.2 | 2026-08-22 | §3 amended to add Zoho Books OAuth client credentials and per-client refresh tokens to the secrets-storage requirement, and to note that Zoho's rotation model differs fundamentally from Tally/GSP's fixed schedule. |

## 1. Authentication & session handling

Per ID-01/ID-04 (PRD): role-based login (Proprietor / Senior / Junior), with session handling appropriate for shared office devices.

- Session tokens expire after a fixed idle period (default 8 hours) — no indefinitely-lived sessions, since office devices are often shared.
- No credentials or session tokens persisted in a way that survives a browser restart on a shared machine beyond the session's own expiry.
- Failed login attempts are rate-limited per account to prevent credential-stuffing against the small, known staff user base.

## 2. Authorization is enforced server-side, not just hidden in the UI

Every API endpoint checks the caller's role against what the action requires — a junior staff member's browser simply not showing an "Approve invoice" button is not authorization; the endpoint itself must reject the request if called directly.

```python
async def approve_invoice(invoice_id: str, current_user: User = Depends(get_current_user)) -> None:
    if current_user.role not in {"proprietor"}:
        raise HTTPException(status_code=403, detail="Invoice approval requires proprietor role")
    ...
```

This matters more than usual here because the routing rules (TE-02) explicitly assign some actions — invoice approval, client communication approval — to the proprietor only; a UI-only restriction would silently violate that design the moment anyone calls the API directly.

## 3. Secrets: storage and rotation

*Amended in v0.2 — Zoho Books OAuth credentials added, per ADR 0011.*

Storage follows CG4 (Coding Guidelines) — centralized settings, never committed to git. In addition:

- Tally connector credentials, GSP client secret, **and Zoho Books OAuth client ID/secret plus every client's per-organization refresh token** are stored in a secrets manager appropriate to the hosting environment (e.g. AWS Secrets Manager for the AWS Mumbai deployment per ADR 0007/0009), not as plain environment variables in a deployment config file.
- **Credential rotation — Tally and GSP:** rotated on a defined schedule (recommend every 90 days) and immediately if any compromise is suspected — this needs an actual runbook step in the Dev Readiness Checklist (item RB-01), not just a policy statement.
- **Credential rotation — Zoho Books:** does *not* follow the same fixed-schedule model. Zoho issues short-lived access tokens (refreshed automatically, typically hourly) against a longer-lived per-client refresh token. Treat a refresh token as compromised-until-proven-otherwise if a client's OAuth consent is ever revoked outside the platform — this surfaces as a `token_expired`/`revoked` status on the Admin — Connections screen and should trigger the same incident-review posture as a suspected credential compromise, even though nothing was "rotated" on a schedule. **Confirm Zoho's current published refresh-token lifetime and revocation behavior against their own documentation before finalizing the runbook** (Dev Readiness Checklist item OQ-06) — treat this with the same "verify against the vendor's current docs, don't assume" discipline already applied to the GSP rate-limit and pricing figures.
- No credential ever appears in a log line (per the Logging Standard §6) or in an error message returned to the frontend.

## 4. Encryption

- **In transit:** TLS everywhere — the PWA to the API, the API to Tally, the API to Zoho Books, the API to the GSP, the API to Dropbox. No plaintext HTTP anywhere in the request path, including internal service-to-service calls if the deployment architecture ends up with more than one service.
- **At rest:** the database is encrypted at rest (standard for AWS RDS/managed Postgres — this is a configuration checkbox, not custom engineering, but it needs to be explicitly verified during deployment setup, not assumed).
- Client documents that transit through the platform (per ADR 0004's thin-layer principle) are not stored at rest by the platform itself beyond what's needed for active processing — they live in Dropbox as the system of record.

## 5. Audit trail is append-only and separate from application data

Per the Logging Standard §5: compliance events (approvals, overrides, reassignments, client record changes) go through `AuditTrailService`, not the logger. That service's storage must be append-only — no UPDATE or DELETE on audit records through the normal application data path. If an audit record needs correction, that's a new record referencing the original, not a mutation of history.

## 6. Input validation beyond Pydantic

CG9 requires Pydantic models for every request/response shape, which handles shape and type validation. Beyond that:

- Any value that flows into a Tally XML payload, a Zoho Books API call, or a GSP API call is validated against its expected format (GSTIN checksum, invoice number character set) before being sent — a malformed or malicious value reaching an external system is a bigger problem than one rejected at the platform's own boundary.
- File uploads (documents arriving via Dropbox/email) are validated for expected file type before OCR processing — the intake pipeline should reject an unexpected executable or script disguised with a document extension, not attempt to process it.

## 7. Dependency management

- All dependencies pinned to exact versions (mirrors the discipline in CG1, applied to the dependency file itself, not just linting).
- Automated vulnerability scanning on the dependency tree (e.g. `pip-audit` or GitHub's Dependabot alerts) runs on a schedule, not just at initial setup — new CVEs get discovered in already-shipped dependencies constantly.

## 8. External API call rate limiting — a cost-safety concern, not just a security one

WhiteBooks' (or any chosen GSP's) API is billed per call or per plan tier (per ADR 0002/RC-01b), and Zoho Books' API is subject to its own published rate limits per organization (per ADR 0011 — confirm current limits, Dev Readiness Checklist item OQ-05). A bug that causes runaway repeated calls — a retry loop without a cap, a webhook triggering duplicate fetches — isn't just a performance problem, it's a real cost/availability problem given the volume this platform is meant to reach (500 returns/month across a mixed Tally/Zoho client base). Internal rate limiting per client per period should exist independent of whatever limit the GSP or Zoho itself enforces, as a defense against the platform's own bugs, not just external abuse.

## 9. Incident response basics

- If a credential is suspected compromised — Tally, GSP, **or a client's Zoho refresh token** — rotate/revoke it immediately (per §3), and treat any data accessed with it as potentially exposed until reviewed.
- If client financial data is suspected exposed: this is a DPDP-relevant event — routes to whoever owns legal/compliance for the practice (per the PRD's still-open DPDP legal item), not just an engineering fix-and-move-on.
- A minimal incident log (what happened, when noticed, what was done) should exist even before a formal incident-response runbook is written — the Dev Readiness Checklist includes creating this runbook as an explicit task (item RB-02).
