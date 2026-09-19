# API Specification — Practice Automation Platform
### v0.2

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial spec: ~58 endpoints across 12 domains, traced to PRD requirement IDs and the ER diagram entities. Auth/error/pagination conventions defined once, not repeated per endpoint. |
| v0.2 | 2026-08-22 | §5 retitled from "Tally Connections (TC)" to "Books Connections (BC)" per ADR 0011. Sync/restore endpoints generalized to dispatch to whichever adapter a client is configured for. Two new endpoints added for Zoho's OAuth2 flow (`/auth/zoho/authorize`, `/auth/zoho/callback`) plus a re-authorization endpoint. §2 Conventions updated to note the OAuth callback as a second exception to the bearer-token rule. |

## 1. How this spec is meant to be used

This is a design-time reference, not the final machine-readable artifact. Per CG9 (Coding Guidelines): every request/response shape is a Pydantic model in the actual codebase, and FastAPI auto-generates the real OpenAPI 3.0 JSON from those models at runtime. This document exists so the API surface can be reviewed and the Sprint Plan sequenced against it before that code exists, not as a permanent parallel spec to keep manually in sync afterward. Once built, `docs/api/openapi.json` (FastAPI-generated) becomes the actual source of truth.

## 2. Conventions (defined once)

**Base path:** `/api/v1`

**Auth:** JWT bearer token, obtained via `POST /auth/login`. Per the Security Standard §1, tokens expire after a fixed idle period (8 hours default). Every endpoint below other than `/auth/login` requires a valid token, **with two exceptions**: `POST /webhooks/dropbox` (§7), authenticated by Dropbox's own signature verification, and `GET /auth/zoho/callback` (§5), authenticated by the OAuth `state` parameter matching a value the platform generated when initiating the flow — not a user bearer token, since Zoho itself redirects the browser to this endpoint. Role requirements are noted per endpoint per the routing/authorization model in Security Standard §2.

**Roles:** `proprietor` | `senior` | `junior` (per ID-01). "Any staff" means all three.

**Standard error shape:**
```json
{ "error_code": "voucher_not_found", "message": "Voucher does not exist or you don't have access.", "detail": null }
```

**Pagination (list endpoints):** `?page=1&page_size=25`, response wraps results as `{ "items": [...], "total": 142, "page": 1, "page_size": 25 }`.

**Money fields:** always Decimal-serialized as strings (e.g. `"18400.00"`), never JSON floats — per CG5.

## 3. Auth & Identity (ID)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| POST | `/auth/login` | — | `{email, password}` | `{access_token, expires_at, user}` | ID-01 |
| POST | `/auth/logout` | Any staff | — | 204 | ID-04 |
| GET | `/users/me` | Any staff | — | `User` | ID-01 |
| GET | `/users` | Proprietor | — | `User[]` | ID-01 |
| GET | `/audit-log` | Proprietor | `?actor_id=&event_type=&from=&to=` | `AuditEvent[]` (paginated) | ID-05, Security §5 |

## 4. Task Engine (TE)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/tasks` | Any staff | `?assignee_id=&client_id=&status=&type=` | `Task[]` (paginated) | TE-07 |
| GET | `/tasks/{id}` | Any staff | — | `Task` | TE-01 |
| PATCH | `/tasks/{id}` | Any staff (own) / Senior+ (reassign) | `{status?, assignee_id?, outcome?}` | `Task` | TE-03, TE-06 |
| POST | `/tasks/{id}/complete` | Assignee | `{outcome}` | `Task` | TE-06 |
| GET | `/dashboard/summary` | Any staff | — | `DashboardSummary` (KPIs, staff workload) | PM-01, PM-02 |
| GET | `/admin/routing-rules` | Proprietor | — | `RoutingRule[]` | TE-02 |
| PUT | `/admin/routing-rules/{task_type}` | Proprietor | `{default_role, escalate_after_hours}` | `RoutingRule` | TE-02 |

`Task` includes: `id, type, client_id, linked_record_type, linked_record_id, assignee_id, due_at, status, outcome, created_by_agent`.

## 5. Books Connections (BC) — mostly internal, admin-facing subset

*Retitled from "Tally Connections (TC)" per ADR 0011. Covers both the Tally and Zoho adapters behind the platform's `BooksConnector` interface.*

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/admin/books-connections` | Proprietor | `?client_id=&books_system=` | `BooksConnection[]` | TC-05, ZB-05, ADR 0011 |
| POST | `/admin/books-connections/{client_id}/sync` | Proprietor | — | 202 (async — dispatches to the client's configured adapter, Tally or Zoho) | TC-01–TC-03, ZB-02 |
| POST | `/admin/books-connections/{client_id}/restore-backup` | Proprietor | multipart file | 202 (async — Tally adapter only, secondary path) | TC-06, TC-07 |
| GET | `/auth/zoho/authorize` | Proprietor | `?client_id=` | 302 redirect to Zoho's OAuth2 consent screen | ZB-01, ADR 0011 |
| GET | `/auth/zoho/callback` | — (authenticated via OAuth `state` param, not a bearer token) | `?code=&state=` | 302 redirect to Admin — Connections, with connection status set | ZB-01, ADR 0011 |
| POST | `/admin/books-connections/{client_id}/zoho/reauthorize` | Proprietor | — | 302 redirect to `/auth/zoho/authorize` | ZB-05 |

`BooksConnection` includes: `id, client_id, books_system (tally|zoho_books), tally_company_name?, tally_connection_path?, zoho_organization_id?, zoho_oauth_status?, last_sync_at, sync_health`.

## 6. Email Intake (EI)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/admin/sender-mappings` | Senior+ | — | `SenderMapping[]` | EI-02, EI-06 |
| POST | `/admin/sender-mappings` | Senior+ | `{sender_domain, client_id}` | `SenderMapping` | EI-06 |
| PATCH | `/admin/sender-mappings/{id}` | Senior+ | `{client_id}` | `SenderMapping` | EI-06 |

## 7. Document Intake (DI)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| POST | `/webhooks/dropbox` | — (Dropbox signature verified, not user auth) | Dropbox notification payload | 200 immediately, per the 10s constraint | DI-01, DI-01a |
| GET | `/clients/{id}/documents` | Any staff | `?period=&doc_type=` | `Document[]` | DI-02, DI-03 |
| GET | `/documents/{id}` | Any staff | — | `Document` (incl. extracted_data) | DI-02 |
| GET | `/clients/{id}/documents/checklist` | Any staff | `?period=` | `DocumentChecklist` | DI-04 |

## 8. Bookkeeping (BK)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/vouchers` | Any staff | `?client_id=&status=&confidence_lt=&books_system=` | `Voucher[]` (paginated) | BK-05 |
| GET | `/vouchers/{id}` | Any staff | — | `Voucher` (incl. source document ref, `posting_system`) | BK-04 |
| POST | `/vouchers/{id}/approve` | Any staff | — | `Voucher` → posts via the Books Connector to the client's configured adapter (runs CG7 dup-check) | BK-06, BK-07, BK-08 |
| POST | `/vouchers/{id}/reject` | Any staff | `{reason}` | `Voucher` | BK-06 |
| POST | `/vouchers/{id}/create-ledger` | Senior+ | `{ledger_name}` | `Voucher` | BK-03 |

## 9. Client Communication (CC)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/communications` | Any staff | `?client_id=&status=` | `Communication[]` | CC-04 |
| GET | `/communications/pending-approval` | Proprietor | — | `Communication[]` | CC-03 |
| POST | `/communications/{id}/approve` | Proprietor | `{edited_body?}` | `Communication` → sends | CC-03 |

## 10. Reconciliation (RC)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| POST | `/clients/{id}/reconciliation/run` | Senior+ | `{period}` | 202 (async — calls GSP per ADR 0002, pulls purchase register via the Books Connector) | RC-01, RC-02 |
| GET | `/reconciliation/mismatches` | Any staff | `?client_id=&reason=` | `MismatchItem[]` (paginated) | RC-04 |
| GET | `/reconciliation/mismatches/{id}` | Any staff | — | `MismatchItem` | RC-04 |
| POST | `/reconciliation/mismatches/{id}/resolve` | Senior+ | `{resolution_note}` | `MismatchItem` | RC-04 |
| GET | `/clients/{id}/reconciliation/summary` | Any staff | `?period=` | `ReconciliationSummary` (auto-confirmed ITC total) | RC-03, RC-05 |

## 11. Validation / Compliance (VC)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| POST | `/clients/{id}/validation/run` | Senior+ | `{period}` | 202 (async) | VC-01–VC-04 |
| GET | `/validation/checks` | Any staff | `?client_id=&result=` | `ValidationCheck[]` | VC-05 |
| GET | `/clients/{id}/filing-readiness` | Any staff | `?period=` | `{status: "cleared"\|"blocked", blocking_checks: []}` | VC-06 |

## 12. TDS/TCS (TDS)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| POST | `/clients/{id}/tds/run` | Senior+ | `{quarter}` | 202 (async) | TDS-01, TDS-02 |
| GET | `/tds/records` | Any staff | `?client_id=&status=` | `TdsRecord[]` | TDS-03 |
| POST | `/tds/records/{id}/resolve` | Senior+ | `{resolution_note}` | `TdsRecord` | TDS-03 |
| GET | `/clients/{id}/tds/draft-return` | Any staff | `?quarter=` | `TdsDraftReturn` | TDS-04 |

## 13. Bank Reconciliation (BR)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/clients/{id}/bank-accounts` | Any staff | — | `BankAccount[]` | BR-01 |
| POST | `/clients/{id}/bank-accounts` | Senior+ | `{bank_name, account_ref}` | `BankAccount` | BR-01 |
| GET | `/bank-transactions` | Any staff | `?account_id=&status=unmatched` | `BankTransaction[]` | BR-02 |
| POST | `/bank-transactions/{id}/resolve` | Any staff | `{resolution_note}` | `BankTransaction` | BR-03 |
| GET | `/bank-accounts/{id}/statement` | Any staff | `?period=` | `BankReconciliationStatement` | BR-04 |

## 14. Working Paper (WP)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/working-papers` | Any staff | `?client_id=&status=` | `WorkingPaper[]` | WP-01 |
| GET | `/working-papers/{id}` | Any staff | — | `WorkingPaper` | WP-02 |
| PATCH | `/working-papers/{id}` | Proprietor | `{judgment_notes}` | `WorkingPaper` | WP-03 |
| POST | `/working-papers/{id}/finalize` | Proprietor | — | `WorkingPaper` (status → finalized, filed to Dropbox) | WP-04 |

## 15. Practice Management (PM)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/staff/workload` | Any staff | — | `StaffWorkload[]` | PM-02 |
| GET | `/capacity` | Any staff | — | `{available_staff: int, at_risk_clients: []}` | PM-03 |
| GET | `/deadlines/calendar` | Any staff | `?from=&to=&client_id=` | `Deadline[]` | PM-04 |

## 16. Client Profiling & Billing (CB)

| Method | Path | Role | Request | Response | Traces to |
|---|---|---|---|---|---|
| GET | `/clients` | Any staff | `?status=&search=&books_system=` | `Client[]` (paginated) | CB-01 |
| POST | `/clients` | Senior+ | `ClientCreateRequest` (incl. `books_system`) | `Client` | CB-01 |
| GET | `/clients/{id}` | Any staff | — | `Client` (incl. services subscribed, books_system) | CB-01 |
| PATCH | `/clients/{id}` | Senior+ | `ClientUpdateRequest` | `Client` | CB-01 |
| POST | `/clients/{id}/deactivate` | Proprietor | — | `Client` | CB-01 |
| GET | `/service-categories` | Any staff | — | `ServiceCategory[]` | CB-02 |
| POST | `/service-categories` | Proprietor | `{name}` | `ServiceCategory` | CB-02 |
| GET | `/service-catalog` | Any staff | `?category_id=` | `ServiceCatalogItem[]` | CB-02 |
| POST | `/service-catalog` | Proprietor | `ServiceCatalogItemCreateRequest` | `ServiceCatalogItem` | CB-02 |
| PATCH | `/service-catalog/{id}` | Proprietor | `{price?, active?}` | `ServiceCatalogItem` | CB-02, CB-08 |
| GET | `/clients/{id}/service-overrides` | Any staff | — | `ServiceOverride[]` | CB-03 |
| POST | `/clients/{id}/service-overrides` | Proprietor | `{catalog_item_id, override_price, reason}` | `ServiceOverride` | CB-03 |
| GET | `/invoices` | Any staff | `?client_id=&status=` | `Invoice[]` (paginated) | CB-07 |
| GET | `/invoices/{id}` | Any staff | — | `Invoice` (incl. billable events, GST breakup) | CB-05, CB-09 |
| POST | `/invoices/{id}/approve` | Proprietor | — | `Invoice` → sends | CB-06 |
| GET | `/invoices/draft` | Proprietor | `?period=` | `Invoice[]` (current cycle drafts) | CB-05 |

## 17. What's deliberately not in this spec

- Endpoints for Notice/Scrutiny Tracker — deferred scope, per the Feature Backlog's "Future" phase.
- Webhook/callback endpoints for the GSP itself — not yet designed, since the GSP vendor selection (RC-01d) hasn't run its sandbox spike yet.
- Bulk import/export endpoints — not requested in the PRD; add only if a real need surfaces during Phase 0/1.
- A Zoho-equivalent webhook (Zoho does support outbound webhooks for some events) — not included in v0.2, since the current design polls/syncs on demand via `/admin/books-connections/{client_id}/sync` rather than relying on Zoho pushing changes. Revisit if sync latency becomes a real problem post-launch.
