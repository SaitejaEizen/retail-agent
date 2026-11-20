---
title: 'Story 1.2: Look up an order and see return eligibility'
type: 'feature'
created: '2026-11-19'
status: 'done'
baseline_commit: '4bae53176da9a62805b4006f7727060d35f0ad5b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-retail-agent-2026-11-19/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Customer can't yet see an Order's status or whether they can still return items (FR1, FR2).

**Approach:** Add `POST /orders/lookup` (order ID + email in the body). It returns the Order, its lines and total, and return eligibility computed by pure domain rules with `today` from the injected `Clock`. Story 1.2 only: `returns` is always `[]` and `returnable_quantity` equals the purchased quantity until story 2.1.

## Boundaries & Constraints

**Always:** Eligibility, Returnable Quantity, window end, total and email matching are pure functions in `app/domain/rules.py` that take every input (incl. `today`) as arguments. Domain entities are frozen dataclasses in `app/domain/models.py`. SQL only in `app/repositories/orders.py`. Money is int `_cents`. Not found → `DomainError(ORDER_NOT_FOUND)` → 404 via the existing handler; unknown ID and wrong email give byte-identical bodies. Email never in URLs or logs. Test docstrings name the FR.

**Never:** No `/returns`, `/audit`, returns/audit tables, eligibility rejection codes, or audit writes (stories 2.1/2.2). No `date.today()`/`datetime.now()` outside `app/infra/clock.py`. No new dependencies (no `email-validator`/`EmailStr`). No commits.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Match | `ORD-1001` + seeded email | 200: `order_id`, `status`, `delivered_on`, `lines[{line_id, sku, quantity, unit_price_cents, returnable_quantity}]`, `total_cents`, `return_window_ends_on`, `is_returnable`, `returns: []` | N/A |
| Email case | same email in mixed case / surrounding spaces | 200, same as Match | N/A |
| Unknown ID | `ORD-9999` | 404 `ORDER_NOT_FOUND` | body identical to wrong-email case |
| Wrong email | `ORD-1001` + other email | 404 `ORDER_NOT_FOUND` | body identical to unknown-ID case |
| Day 30 | delivered_on + 30 == today | `is_returnable: true`, `return_window_ends_on` = delivered_on + 30 | N/A |
| Day 31 | delivered_on + 31 == today | `is_returnable: false`, window end unchanged | N/A |
| Not delivered | `placed`/`shipped`/`cancelled` | `return_window_ends_on: null`, `is_returnable: false`, `returnable_quantity` = quantity | N/A |
| Bad body | missing field, empty string, wrong type | 422 `VALIDATION_ERROR` envelope | existing handler |

</frozen-after-approval>

## Code Map

- `app/domain/errors.py` -- add `ORDER_NOT_FOUND` + default message "Order not found."; keep existing codes.
- `app/api/errors.py` -- add `ORDER_NOT_FOUND: 404` to `STATUS_BY_CODE`; no other change.
- `app/api/deps.py` -- reuse `get_connection`, `get_clock` (tests override `get_clock` with `dependency_overrides`).
- `app/main.py` -- include the new orders router next to `health.router`.
- `app/infra/seed.py` -- read-only reference: `ORD-1001` (12 days, `asha@example.com`, MUG-001×2@1250 + BAG-003×1@899 → 3399), `ORD-1002` (41 days), `ORD-1003` (30 days), `ORD-1004..1006` placed/shipped/cancelled. Do not change.
- `tests/conftest.py` -- reuse `client`, `fixed_clock` (2026-11-19 09:30Z, also the seed reference date).
- `tests/api/test_docs_and_errors.py::test_openapi_lists_every_endpoint` -- expected path set must gain `/orders/lookup`.
- `tests/unit/test_architecture.py` -- extend with the clock-only-time AST check.

## Tasks & Acceptance

**Execution:**
- [x] `app/domain/models.py` -- `OrderStatus` StrEnum, frozen `OrderLine(line_id, sku, quantity, unit_price_cents)`, `Order(order_id, customer_email, status, placed_on, delivered_on, lines)` -- AD-8
- [x] `app/domain/rules.py` -- `RETURN_WINDOW_DAYS = 30`, `email_matches`, `order_total_cents`, `return_window_ends_on`, `is_within_return_window(delivered_on, today)`, `returnable_quantity(line, already_returned=0)`, `is_returnable(order, today, returned_by_line=None)` -- AD-1, AD-4
- [x] `app/domain/errors.py`, `app/api/errors.py` -- `ORDER_NOT_FOUND` → 404 -- AD-6
- [x] `app/repositories/orders.py` -- `OrderRepository.get(order_id) -> Order | None` (order + lines by `line_id`) -- AD-7
- [x] `app/services/order_service.py` -- `OrderService.lookup(order_id, email, today)` returns a frozen `OrderLookup` view; raises `ORDER_NOT_FOUND` for unknown ID or mismatched email -- FR1, FR2
- [x] `app/api/schemas.py`, `app/api/orders.py`, `app/main.py` -- `LookupRequest` (non-empty `order_id`, `email`), `OrderLookupResponse`, `ReturnSummary` (`return_id`, `refund_cents`; list empty for now); `POST /orders/lookup` documents 200/404/422 -- FR1, FR2, AD-9
- [x] `tests/unit/test_rules.py`, `tests/unit/test_order_service.py`, `tests/api/test_orders.py`, `tests/unit/test_architecture.py`, `tests/api/test_docs_and_errors.py` -- every matrix row; days 29/30/31; no `datetime.now`/`date.today`/`utcnow` call outside `app/infra/clock.py` (AST) -- FR1, FR2, AD-4

**Acceptance Criteria:**
- Given the running service, when `/docs` loads, then `POST /orders/lookup` is listed with its request and response schemas.
- Given the CI commands, when run, then ruff is clean and coverage on domain + services stays ≥90%.

## Implementation Notes

- Implemented directly (no subagent). Spec approval checkpoint taken as given by the user's explicit build instruction.
- FastAPI 0.165 wraps included routers, so the OpenAPI test asserts the documented path set rather than walking `app.routes`.

## Spec Change Log

## Review Triage Log

- 2026-11-19: Automated review layers skipped at the user's request; the user reviews the diff manually.

## Design Notes

`is_returnable` = delivered AND within window AND some line has `returnable_quantity > 0`. The last clause is a no-op until story 2.1 passes real returned quantities through `returned_by_line`. Email match: `stored.strip().casefold() == given.strip().casefold()`.

## Verification

**Commands:**
- `.venv/bin/ruff check .` -- expected: no errors
- `.venv/bin/pytest --cov=app/domain --cov=app/services --cov-fail-under=90` -- expected: all pass, gate met
- `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` -- expected: no known vulnerabilities
