---
title: 'Story 2.1: Return items and receive a refund'
type: 'feature'
created: '2026-11-19'
status: 'done'
baseline_commit: 'a4505445b10fcb3df26aaa8f92171fed0f11d1c1'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-retail-agent-2026-11-19/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Customer can see they're eligible but can't return anything; there is no Refund or Restock (FR3–FR6), and lookup can't show past Returns (FR2).

**Approach:** Add `POST /returns`, handled by `ReturnService.create_return` in one `BEGIN IMMEDIATE` transaction that re-reads state, runs pure domain checks and refund maths, writes the Return and restocks Inventory. Lookup then lists Returns and reduces `returnable_quantity`. Story 2.1 only: no audit writes, table or endpoint (story 2.2).

## Boundaries & Constraints

**Always:** Rules (eligibility, refund) are pure functions in `app/domain/rules.py` taking `today`. `ReturnService.create_return` is the only writer of `returns`, `return_lines`, `inventory`, with one commit and full rollback on any error. Money int cents. Check order: email/ID → delivered → window → line on order → quantity; first failure wins. `created_at` from `Clock.now()`, UTC `Z`. Test docstrings name the FR.

**Never:** No audit table/writes/endpoint. No new dependencies. No commits. No migrations: existing DB files get the new tables via `CREATE TABLE IF NOT EXISTS`.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Accept | ORD-1001, MUG line ×1, reason | 201 `{return_id, order_id, created_at, reason, lines[{line_id, sku, quantity, refund_cents}], refund_cents: 1250}`; MUG inventory +1 | N/A |
| Multi-line | MUG ×2 + BAG ×1 | `refund_cents: 3399`; both SKUs restocked | N/A |
| Partial repeat | 2-unit line: return 1, then 1, then 1 | 201, 201, then 422 `INVALID_QUANTITY` | 3rd changes nothing |
| Day 30 / 31 | ORD-1003 at seed day / seed day + 1 | 201 / 422 `RETURN_WINDOW_EXPIRED` | unchanged on reject |
| Not delivered | placed/shipped/cancelled order | 422 `ORDER_NOT_DELIVERED` | unchanged |
| Bad quantity | 0, negative, > returnable | 422 `INVALID_QUANTITY` | unchanged |
| Foreign line | `line_id` from another order / unknown | 422 `LINE_NOT_ON_ORDER` | unchanged |
| Not found | unknown ID or wrong email | 404 `ORDER_NOT_FOUND`, identical bodies | unchanged |
| Malformed | empty `lines`, duplicate `line_id`, non-int quantity, missing field | 422 `VALIDATION_ERROR` | unchanged |
| Failure mid-write | error raised after Return insert | 5xx; no Return rows, inventory unchanged | rollback |
| Lookup after | Order with Returns | `returns` lists each with `refund_cents`; `returnable_quantity` reduced; fully returned → `is_returnable: false` | N/A |

</frozen-after-approval>

## Code Map

- `app/infra/schema.sql` -- append `returns` (`return_id` AUTOINCREMENT, `order_id` FK, `reason` NULL, `refund_cents` ≥0, `created_at`) and `return_lines` (`return_id` FK, `line_id` FK `order_lines`, `quantity` >0, `refund_cents` ≥0).
- `app/domain/rules.py` -- reuse `email_matches`, `returnable_quantity`, `is_returnable(order, today, returned_by_line)`, `is_within_return_window`; add `check_return_eligibility`, `refund_cents`.
- `app/domain/models.py` -- add `ReturnLine`, `Return`.
- `app/domain/errors.py`, `app/api/errors.py` -- add 4 eligibility codes → 422.
- `app/services/order_service.py` -- `OrderLookup.returns` becomes `tuple[Return, ...]`; `OrderService` takes a returns reader to fill it and returned quantities.
- `app/api/orders.py`, `app/api/schemas.py` -- extend `ReturnSummary` (`return_id`, `created_at`, `reason`, `lines`, `refund_cents`); map real Returns.
- `app/infra/db.py::connect` -- default `isolation_level` (legacy); explicit `BEGIN IMMEDIATE` works and `with conn` in seed is unaffected.
- `tests/unit/test_seed.py::test_schema_creates_only_story_tables` -- expected set gains `returns`, `return_lines`.
- `tests/api/test_docs_and_errors.py::test_openapi_lists_every_endpoint` -- add `/returns`.

## Tasks & Acceptance

**Execution:**
- [x] `app/infra/schema.sql` -- two new tables -- AD-7
- [x] `app/domain/models.py`, `app/domain/rules.py`, `app/domain/errors.py`, `app/api/errors.py` -- `Return`/`ReturnLine`; `check_return_eligibility(order, requested, returned_by_line, today)` raises the specific `DomainError`; `refund_cents(order, requested)`; codes → 422 -- FR4, FR5, AD-1
- [x] `app/repositories/returns.py`, `app/repositories/inventory.py` -- `ReturnRepository.returned_quantities/list_for_order/insert`; `InventoryRepository.restock(sku, qty)` failing if no row updated -- AD-7
- [x] `app/services/return_service.py` -- `ReturnService(conn, orders, returns, inventory).create_return(order_id, email, lines, reason, now)` -- AD-2, FR3, FR6, NFR1
- [x] `app/services/order_service.py`, `app/api/orders.py`, `app/api/schemas.py` -- lookup shows real Returns and reduced quantities -- FR2
- [x] `app/api/returns.py`, `app/main.py` -- `POST /returns` → 201, request `{order_id, email, lines[{line_id, quantity}] (≥1, unique line_id), reason ≤500}`; docs 201/404/422 -- FR3, AD-9
- [x] `tests/unit/test_rules.py`, `tests/unit/test_return_service.py`, `tests/unit/test_order_service.py`, `tests/api/test_returns.py`, `tests/api/test_orders.py`, `tests/unit/test_seed.py`, `tests/api/test_docs_and_errors.py` -- every matrix row; rollback via injected failing inventory repo -- FR2–FR6, NFR1

**Acceptance Criteria:**
- Given an existing 1.x DB file, when the service restarts, then the new tables are created and returns work.
- Given the CI commands, when run, then ruff is clean and coverage on domain + services stays ≥90%.

## Implementation Notes

- Implemented directly (no subagent). Spec approval checkpoint taken as given by the user's explicit build instruction; spec kept whole at ~2000 tokens (one cohesive return flow).
- `OrderService` now requires a returns reader; `ReturnService` takes optional repository overrides so tests can inject a failing inventory.
- `InventoryRepository.restock` raises `LookupError` when no row is updated, so a missing inventory row rolls the Return back (500) instead of silently skipping the Restock.
- Mutation-checked: removing the rollback makes 9 service tests fail.

## Spec Change Log

## Review Triage Log

- 2026-11-19: Automated review layers skipped at the user's request; the user reviews the diff manually.

## Design Notes

The service opens `BEGIN IMMEDIATE` before reading, so two concurrent requests serialise and the second sees the first's quantities. Duplicate `line_id`s are rejected at the schema boundary (`VALIDATION_ERROR`) rather than summed, so one request maps 1:1 to return lines. Quantity is a plain `int` in the schema so ≤0 reaches the domain and yields `INVALID_QUANTITY`.

## Verification

**Commands:**
- `.venv/bin/ruff check .` -- expected: no errors
- `.venv/bin/pytest --cov=app/domain --cov=app/services --cov-fail-under=90` -- expected: all pass, gate met
- `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` -- expected: no known vulnerabilities
