# Coding Guidelines — Practice Automation Platform
### Backend (Python / FastAPI) | v0.2.1

## Changelog

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-08-16 | Initial set: CG1–CG11, covering linting, typing, secrets, financial precision, external-API resilience, duplicate prevention, the Task Engine contract, testing, and the base/customization boundary from ADR 0010. |
| v0.2 | 2026-08-22 | CG7 generalized from "Tally-specific" to "any books-system write," per ADR 0011 — the duplicate-prevention check and code example no longer name Tally exclusively, so the guideline applies correctly to a Zoho-only reading as well. |
| v0.2.1 | 2026-09-19 | **CG1 amended to cover `scripts/` alongside `services/api/`.** This **records a change already made in PR #72 rather than mandating a new one**: that PR added `scripts/check_md_tables.py` and a root `.ruff.toml` governing it, which left CG1 — stating ruff was the sole linter *for `services/api/`* — misreporting what the repo actually does. That is the same defect class the 2026-09-19 documentation-currency audit exists to fix, so it is corrected here rather than left as drift. CG1 now states both configurations, that they share one rule set with **one deliberate difference** (`services/api/` ignores `B008` for FastAPI's `Depends()` idiom, which does not arise in `scripts/`), that the two files nest their keys differently because a `pyproject.toml` section and a standalone `.ruff.toml` require it, and that **ruff is pinned identically in both at `0.6.9`**. It also records that a new top-level Python directory inherits the root config rather than going unlinted by default — the reasoning for adding `.ruff.toml` at all. **CG1 is now the only rule reaching outside `services/api/`**, stated explicitly so the document's "Backend (Python / FastAPI)" subtitle stays honest; whether CG2–CG11 should also apply to `scripts/` is a scoping question tracked as `PENDING:023`, not settled here. |

Rules are numbered CG1–CG11. All are non-negotiable unless a rule explicitly says otherwise. Frontend (React/TypeScript) conventions are a separate document, not covered here.

## CG1 — Linting & formatting: ruff, zero warnings before commit

`ruff` is the sole linter and formatter for **all Python in this repo**, under
two configurations. This is the only CG rule that reaches outside
`services/api/`; CG2–CG11 are backend rules and are scoped to it.

**`services/api/`** — configured in its own `pyproject.toml`:

```toml
# services/api/pyproject.toml
[tool.ruff]
line-length = 100
target-version = "py311"
[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = ["B008"]
```

**Repo-level Python outside it** — today `scripts/` — configured in the root
`.ruff.toml`:

```toml
# .ruff.toml
line-length = 100
target-version = "py311"

[lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

**Same rule set, one deliberate difference.** `services/api/` additionally
ignores `B008`, because FastAPI's `Depends()`-in-a-default-argument is the
framework's own dependency-injection idiom rather than the mutable-default bug
that rule exists to catch. That idiom does not arise in `scripts/`, so the
ignore is correctly absent there — do not add it to bring the files into
line.

The two files also nest their keys differently: a `pyproject.toml` needs the
`[tool.ruff]` / `[tool.ruff.lint]` prefix, a standalone `.ruff.toml` uses
top-level keys and `[lint]`. Both express the same settings. Aligning one to
the other's shape breaks it.

**Pin the version, identically in both.** `ruff==0.6.9` as of PR #72 —
declared in `services/api/pyproject.toml`'s `dev` extra and installed as
`pip install ruff==0.6.9` in the workflow. A linter that floats to latest
turns an unrelated PR red months later with no visible cause.

**A new top-level Python directory inherits the root `.ruff.toml` rather than
going unlinted by default.** That is why the root config exists at all: a new
directory left outside any ruff scope becomes an unlinted dumping ground
silently, and the cheapest moment to prevent it is before the directory has
contents. New Python *under* `services/` follows that service's own config
instead.

CI gates — both must exit 0 before merge:

| Scope | Command | Workflow |
|---|---|---|
| `services/api/` | `ruff check . --no-fix` (from that directory) | `ci.yml` |
| `scripts/` | `ruff check scripts/ --no-fix` | `md-tables.yml` |

## CG2 — Type hints required on every function signature

Every parameter and return type must be annotated. Use `from __future__ import annotations` at the top of every file.

❌ Bad:
```python
def match_vendor(name, client_id):
    ...
```

✅ Good:
```python
from __future__ import annotations

def match_vendor(name: str, client_id: str) -> VendorMatchResult | None:
    ...
```

## CG3 — Function length: 50 lines maximum

Extract helpers before hitting the limit. This applies especially to agent logic (Bookkeeping, Reconciliation) where "one function does extraction, matching, and posting" is the most common way this gets violated — those are three functions, not one.

## CG4 — Secrets and configuration: centralized settings, never raw os.environ

All configuration — database URL, Redis URL, Tally connector credentials, Zoho OAuth client ID/secret, GSP client ID/secret, OCR engine config — goes through a single `pydantic-settings`-based `Settings` object. Never call `os.environ[...]` or `os.environ.get(...)` outside `config.py`.

```python
# services/api/config.py
from __future__ import annotations
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    redis_url: str
    gsp_client_id: str
    gsp_client_secret: str
    tally_connector_host: str
    zoho_oauth_client_id: str
    zoho_oauth_client_secret: str
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

settings = Settings()  # type: ignore[call-arg]
```

Every new setting requires a corresponding placeholder in `.env.example`, committed in the same PR. No credential — GSP secret, Tally auth token, Zoho OAuth secret, database password — is ever committed to git in any form, including in test fixtures or comments.

## CG5 — Money is Decimal, never float

Every monetary amount — invoice totals, GST variance figures, TDS deduction amounts, billing line items — is a `Decimal`, sourced from strings or integers, never from a float literal or float arithmetic. This is not a style preference: float arithmetic on currency produces silent rounding errors that surface as real reconciliation mismatches.

❌ Bad:
```python
variance = book_amount - gstr_amount  # both floats
```

✅ Good:
```python
from decimal import Decimal

variance: Decimal = Decimal(str(book_amount)) - Decimal(str(gstr_amount))
```

Pydantic models representing money use `Decimal` as the field type, not `float`.

## CG6 — External API calls must have explicit timeout, retry, and failure isolation

Every call to Tally, Zoho Books, the GSP (WhiteBooks or equivalent), or the OCR pipeline must specify an explicit timeout, use a bounded retry with backoff, and fail into a Task (per CG8) rather than raising an unhandled exception into the request path.

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8))
async def fetch_gstr2b(gstin: str, period: str) -> Gstr2bResponse:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{settings.gsp_base_url}/gstr2b/all",
            json={"gstin": gstin, "period": period},
        )
        response.raise_for_status()
        return Gstr2bResponse.model_validate(response.json())
```

A failed external call after retries exhausted creates a task (e.g. "GSP fetch failed — retry manually") rather than silently dropping the operation or crashing a background worker. This applies equally to Tally and Zoho Books calls.

## CG7 — Duplicate-prevention check before any books-system write

*Amended in v0.2 — was written Tally-specific ("posts a voucher to Tally"); generalized per ADR 0011 to cover both adapters, since the original wording left a Zoho-only reading with no applicable rule.*

Verified in ADR 0001 (Tally) and confirmed to apply equally to the Zoho adapter: neither backend prevents duplicate entries on its own. Any code path that posts an entry to the client's bookkeeping system — Tally or Zoho Books — must check for an existing match (vendor GSTIN + invoice number + date) before posting, and this check is not optional or deferrable — it ships in the same PR as the posting logic, not as a follow-up.

```python
async def post_entry(entry: DraftEntry) -> PostedEntry:
    existing = await find_existing_entry(
        gstin=entry.vendor_gstin,
        invoice_number=entry.invoice_number,
        date=entry.invoice_date,
    )
    if existing is not None:
        raise DuplicateEntryError(existing_id=existing.id)
    return await books_connector.post(entry)  # dispatches to TallyAdapter or ZohoAdapter
```

The check itself runs once, against the platform's own `VOUCHER` table, before either adapter is invoked — this is unchanged from v0.1. What changed is only the guideline's wording and the example's naming, so it no longer reads as Tally-only.

## CG8 — Human-judgment paths go through the Task Engine, never ad hoc

Per ADR 0005: any agent exception or judgment call creates a Task via the shared Task Engine service. No agent module sends its own notification, writes its own "pending review" flag, or otherwise routes around the Task Engine — this is the platform's core enforcement mechanism, and bypassing it in one module defeats the purpose for the whole system.

❌ Bad:
```python
if confidence < 0.7:
    send_email_to_staff("Please review this voucher")
```

✅ Good:
```python
if confidence < CONFIDENCE_THRESHOLD:
    await task_engine.create_task(
        task_type="low_confidence_voucher_review",
        client_id=voucher.client_id,
        linked_record=voucher.id,
        due_at=in_hours(12),
    )
```

## CG9 — Pydantic models for every request/response shape

No route handler accepts or returns a raw dict. Every request body and response shape is a Pydantic model, defined once and reused, not redefined per endpoint.

```python
class VoucherApprovalRequest(BaseModel):
    voucher_id: str
    approved_by: str

    @field_validator("voucher_id")
    @classmethod
    def must_be_valid_uuid(cls, v: str) -> str:
        UUID(v)  # raises ValueError if invalid
        return v
```

## CG10 — Testing: pytest, ≥85% coverage, all external services mocked

```bash
pytest tests/ --cov=. --cov-report=term-missing --cov-fail-under=85
```

Tally, Zoho Books, the GSP, and OCR calls are mocked at the client boundary in every test — CI never calls a real external service. The WhiteBooks, Tally, and Zoho Books sandboxes (per ADR 0002, ADR 0001, ADR 0011) are for manual integration testing only, run separately from the automated suite, not wired into CI.

## CG11 — Base product vs. practice customization (ADR 0010 extension-point pattern)

This resolves the open extension-point definition flagged in ADR 0010.

- Core modules (`services/api/agents/`, `services/api/task_engine/`, `services/api/books_connector/`, etc.) contain only generic, configuration-driven logic. They must never import from, or contain conditional logic branching on, a specific practice.
- Practice-specific customization lives under `services/api/practices/{practice_slug}/` and registers itself against defined extension points (a plugin-style registry, not direct monkey-patching of core modules).
- A core module may expose an extension point (e.g. `WorkingPaperTemplateProvider`), but never reaches into `practices/` directly — the dependency direction is one-way, practices depend on core, never the reverse.
- Before adding anything to `practices/{practice_slug}/`, check whether it's actually configuration (belongs in that practice's settings/service-catalog data, per CG4) rather than code — most "customizations" turn out to be config once examined properly. Note: which books system (Tally vs. Zoho) a client uses is exactly this kind of case — it's a `books_system` config value on the client record (CB-01), not a practice-level code customization, since both adapters live in core per ADR 0011.
- Code that starts in `practices/` and proves broadly useful gets promoted into core in its own PR, with the practice-specific version removed — not left duplicated indefinitely.
