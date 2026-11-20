---
title: 'Story 2.2: Trace every action in the audit trail'
type: 'feature'
created: '2026-11-19'
status: 'done'
baseline_commit: '87054a318c1c6b6d5db9d88c2c0289f3672508d0'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-retail-agent-2026-11-19/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Nothing the service does is recorded, so a lab participant can't trace lookups, refused returns, refunds or restocks (FR7, FR8).

**Approach:** Add an append-only `audit_entries` table (triggers block UPDATE/DELETE), a single writer `AuditRepository.record` that masks emails, audit writes in the lookup and return flows with the transaction rules of AD-5, and `GET /audit?order_id=` newest first.

## Boundaries & Constraints

**Always:** Only `AuditRepository.record` inserts into `audit_entries`. Accepted-return entries (`RETURN_REQUESTED` success, `REFUND_CALCULATED`, `RESTOCK_APPLIED`) are written inside the `ReturnService.create_return` transaction. A lookup and a refused return each commit one entry in their own transaction. Every return refusal, including `ORDER_NOT_FOUND`, is `outcome=rejected` with `details.error_code`; lookup misses are `not_found`. Emails are stored only masked (`a***@example.com`) and never logged. `created_at` comes from the `Clock`, UTC with `Z`. `details` is a JSON object with snake_case keys. Test docstrings name the FR.

**Never:** No auth on `/audit`, no pagination, no new dependencies, no commits. An unexpected (non-domain) failure in a return is not audited; it rolls back and returns 500.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Lookup hit | valid ID + email | 1 entry `ORDER_LOOKUP`/`success`, masked email | N/A |
| Lookup miss | unknown ID or wrong email | 1 entry `ORDER_LOOKUP`/`not_found`, `details.error_code=ORDER_NOT_FOUND`; still 404 | entry committed |
| Return accepted | eligible request | 3 entries: `RETURN_REQUESTED` success (`return_id`, lines), `REFUND_CALCULATED` (`refund_cents`), `RESTOCK_APPLIED` (`items[{sku, quantity}]`) | same transaction |
| Return rolled back | failure after audit writes start | no Return, no inventory change, none of the 3 entries | rollback |
| Return refused | any FR4 code or `ORDER_NOT_FOUND` | 1 entry `RETURN_REQUESTED`/`rejected`, `details.error_code`; Returns/Inventory unchanged | own transaction |
| Tamper | `UPDATE`/`DELETE` on `audit_entries` | aborted by trigger | DB error |
| List | `GET /audit` | 200 `{"entries": [...]}` newest first | N/A |
| Filter | `GET /audit?order_id=ORD-1001` | only that Order's entries, newest first; unknown ID → empty list | N/A |

</frozen-after-approval>

## Code Map

- `app/infra/schema.sql` -- append `audit_entries` (`id` AUTOINCREMENT, `created_at`, `action` CHECK 4 values, `outcome` CHECK 3 values, `order_id` TEXT no FK, `masked_email` NULL, `details` TEXT JSON) + `CREATE TRIGGER IF NOT EXISTS` for UPDATE and DELETE using `RAISE(ABORT, ...)`.
- `app/services/order_service.py` -- `OrderService.lookup`: add audit on hit and miss through an injected committed-audit writer.
- `app/services/return_service.py` -- `create_return`: record 3 entries before `commit`; on `DomainError`, rollback then record the rejection in its own transaction and re-raise.
- `app/api/orders.py`, `app/api/returns.py` -- wire `AuditRepository(conn, clock)` / `AuditService` into the services.
- `tests/unit/test_seed.py::test_schema_creates_only_story_tables`, `tests/api/test_docs_and_errors.py::test_openapi_lists_every_endpoint` -- add `audit_entries`, `/audit`.
- `tests/unit/test_order_service.py`, `tests/unit/test_return_service.py` -- existing fakes need an audit fake / new constructor arg.

## Tasks & Acceptance

**Execution:**
- [x] `app/infra/schema.sql` -- table + 2 triggers -- AD-5
- [x] `app/domain/audit.py` -- `AuditAction`, `AuditOutcome` StrEnums, frozen `AuditEntry`, pure `mask_email`, `redact_emails(details)` (masks any email found in string values) -- FR7, AD-5
- [x] `app/repositories/audit.py` -- `AuditRepository(conn, clock)`: `record(action, order_id, outcome, details, email=None)` (masks, no commit), `list(order_id=None)` newest first by `id` -- AD-5, FR8
- [x] `app/services/audit_service.py` -- `AuditService(conn, repo)`: `record_committed(...)` in its own transaction, `list_entries(order_id)` -- AD-5
- [x] `app/services/order_service.py`, `app/services/return_service.py` -- audit writes per matrix -- FR7, NFR1
- [x] `app/api/audit.py`, `app/api/schemas.py`, `app/api/orders.py`, `app/api/returns.py`, `app/main.py` -- `GET /audit` with optional `order_id` (≤64 chars); `AuditEntryResponse` -- FR8
- [x] tests: `tests/unit/test_audit.py`, `tests/unit/test_audit_repository.py`, `tests/api/test_audit.py`, plus updates to the order/return service, seed and docs tests -- every matrix row; trigger blocks UPDATE and DELETE; full email absent from DB audit rows and logs; only `app/repositories/audit.py` contains `INSERT INTO audit_entries` -- FR4, FR7, FR8, NFR1

**Acceptance Criteria:**
- Given an existing 2.1 DB file, when the service restarts, then `audit_entries` and its triggers are created and auditing works.
- Given the CI commands, when run, then ruff is clean and coverage on domain + services stays ≥90%.

## Implementation Notes

- Implemented directly (no subagent). Spec approval checkpoint taken as given by the user's explicit build instruction.
- `ReturnService` now requires an `AuditWriter` as its second argument; `OrderService` requires a committed-audit writer (`AuditService`).
- `AuditRepository.record` also masks emails found inside `details` (e.g. in a free-text `reason`).
- Unit masking tests live in `tests/unit/test_audit_masking.py`: test dirs have no `__init__.py`, so basenames must be unique across `tests/unit` and `tests/api`.
- Mutation-checked: removing the rejection entry's own transaction makes 13 tests fail.

## Spec Change Log

## Review Triage Log

- 2026-11-19: Automated review layers skipped at the user's request; the user reviews the diff manually.

## Design Notes

`AuditRepository` takes the `Clock` so `record` keeps the AD-5 signature. Accepted-return entries are written after the Return and Restock, so any failure before `commit` (including in `record`) rolls back all of them. Masking keeps the first character of the local part and the full domain: `asha@example.com` → `a***@example.com`; an empty local part or a string without `@` becomes `***`.

## Verification

**Commands:**
- `.venv/bin/ruff check .` -- expected: no errors
- `.venv/bin/pytest --cov=app/domain --cov=app/services --cov-fail-under=90` -- expected: all pass, gate met
- `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` -- expected: no known vulnerabilities
