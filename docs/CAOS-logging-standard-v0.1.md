# Logging Standard — Practice Automation Platform
### v0.1

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial standard: structured logging with correlation fields, log-level definitions calibrated to platform events, the audit-trail boundary (compliance events don't go through the logger), and PII/masking rules given the financial data this platform handles. |
| v0.1 (extracted) | 2026-08-22 | Extracted from the consolidated internal PDF into its own standalone file, alongside the PRD, Sprint Plan, API Spec, Coding Guidelines, Security Standard, and Testing Strategy. No content changes — ADR 0011 (multi-backend bookkeeping connector) does not affect logging behavior; the `agent` correlation field already accommodates a value like `books_connector` or an adapter-specific tag without any rule here needing to change. |

## 1. Why this exists

The platform touches client GSTINs, financial amounts, and task/approval history for a compliance-regulated domain. Logging needs to be useful for debugging without becoming an accidental second, unstructured copy of sensitive data, and without being the system of record for actions that actually need a real audit trail (approvals, overrides, reassignments).

## 2. Structured logging, not print()

All logging goes through Python's `logging` module, configured to emit structured JSON (not plain text) so log lines are filterable by field once shipped to any log aggregation tool. `print()` is permitted only in one-off scripts under `scripts/`, never in `services/api/` route handlers, agents, or background workers.

```python
import logging
logger = logging.getLogger(__name__)

logger.info(
    "Voucher staged for review",
    extra={"client_id": client_id, "voucher_id": voucher.id, "confidence": confidence},
)
```

## 3. Correlation fields — bind once, not per call

Every logger instance used inside an agent or service should be bound with a consistent set of correlation fields at construction, rather than repeating them on every log call:

| Field | When present |
|---|---|
| `practice_id` | Always — even in a single-practice deployment, this keeps log format consistent for the base-product model (ADR 0010) where the same code runs across separate deployments |
| `client_id` | Any operation scoped to a specific client |
| `task_id` | Any operation that created or acted on a Task |
| `agent` | Which agent emitted the line (`bookkeeping`, `reconciliation`, `email_intake`, etc.) |
| `request_id` | Any log line originating inside an API request |

```python
def get_logger(agent: str, **bindings: str) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logging.getLogger(agent), {"agent": agent, **bindings})

logger = get_logger("reconciliation", practice_id=settings.practice_id, client_id=client.id)
logger.info("GSTR-2B fetch completed", extra={"matched": 312, "mismatched": 4})
```

## 4. Log levels

| Level | When to use | Example |
|---|---|---|
| debug | Off in production. Step-by-step tracing during development. | Raw OCR confidence scores per field before thresholding |
| info | Normal lifecycle events — the platform doing what it's supposed to do. | Voucher posted, reconciliation run completed, task created, GSP token refreshed |
| warn | Recoverable, but worth noticing. | External API retry triggered, OCR confidence below threshold (routed to task, not failed), stale Tally connection detected |
| error | An operation failed and a human or the system needs to know. | GSP call failed after retries exhausted, Tally voucher post rejected, OCR pipeline crashed on a document |

Controlled by `LOG_LEVEL`: `debug` in development, `info` in production, silent (or a no-op logger, per §6) in tests by default.

## 5. What must never go through the logger: compliance events

Per the platform's audit-trail requirement (PRD ID-05, and the DPDP accountability principle established in the PRD's architecture notes), the following are not logging events — they go through a dedicated `AuditTrailService` that writes an immutable, queryable record, not a log line that scrolls away:

- Voucher or invoice approval/rejection
- Task reassignment
- Any override of an agent's suggestion by a human
- Client record creation, edit, or deactivation
- Service catalog or pricing changes

```python
# Bad — this is a compliance event, not a log line ❌
logger.info("Invoice approved", extra={"invoice_id": inv.id, "approved_by": user.id})

# Good ✅
await audit_trail.record(
    event_type="invoice_approved",
    actor_id=user.id,
    subject_id=inv.id,
    practice_id=practice_id,
)
```

`AuditTrailService` is a separate, not-yet-built component — flagged here so route handlers are written against the right abstraction from the start rather than retrofitted later.

## 6. PII and financial data: what never appears in a log line

- **GSTIN:** log only the last 4 characters (`***********1Z5`), never the full value.
- **Bank account numbers:** never logged, masked or otherwise — if a bank reference is needed for debugging, log the internal record ID and look up the account separately.
- **Raw document content** (invoice text, extracted line items in full): never logged. Log the document ID and a summary (`"3 line items extracted, confidence 0.91"`), not the content itself.
- **Client contact details** (phone, email): avoid in log lines where an internal ID would do the same job.

This isn't about hiding information from the team — it's about not creating a second, less-controlled copy of exactly the data the platform's thin-layer architecture (ADR 0004) was designed to avoid duplicating.

## 7. Testing

Inject a no-op or in-memory logger in tests rather than asserting against real log output, unless the test is specifically about logging behavior itself.

```python
class NullLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return msg, kwargs

def test_voucher_posting_does_not_crash_on_missing_ledger() -> None:
    sut = BookkeepingAgent(logger=NullLogAdapter(logging.getLogger("test"), {}))
    ...
```

If a test needs to assert a specific log call happened (e.g. confirming a warning fires on low confidence), inject a mock logger and assert on it directly rather than capturing stdout.
