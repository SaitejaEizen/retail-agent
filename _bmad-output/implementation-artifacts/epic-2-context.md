# Epic 2 Context: Returns with refund, restock and audit trail

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Let a Customer return some or all items from a delivered Order within 30 days and get a correct Refund, with the returned stock added back to Inventory, and make every action traceable in an append-only audit trail. This is the core business behaviour of the lab app: a time window, quantity limits, exact money maths and an atomic multi-table write.

## Stories

- Story 2.1: Return items and receive a refund
- Story 2.2: Trace every action in the audit trail

## Requirements & Constraints

- A return request carries order ID, email, lines with quantities, and an optional reason. An eligible request creates exactly one Return with its Refund. Repeated partial Returns are allowed up to each line's Returnable Quantity (purchased minus already returned).
- Rejections, each with a specific reason: Order not `delivered`; request after day 30 of the window (day 30 accepted, day 31 rejected); quantity ≤ 0 or above Returnable Quantity; line not on the Order; ID/email mismatch (same "not found" as lookup). A rejection changes nothing except the audit trail.
- Refund = Σ unit price paid × quantity returned, exact to the cent. No fees, no shipping refund, prices tax-inclusive. Recorded, never paid out.
- An accepted Return adds returned quantities to Inventory; a rejection leaves Inventory unchanged. Inventory changes only through accepted Returns or seed data.
- Lookup lists existing Returns with their Refunds, and Returnable Quantity reflects units already returned.
- Every lookup, return request (accepted or rejected, with reason), Refund calculation and Restock writes an Audit Entry. Entries are append-only, store a masked email, and can be listed newest first, optionally filtered by order ID.
- Return creation, Refund, Restock and their Audit Entries succeed or fail together. Window checks use a controllable date in tests. ≥90% coverage on business logic. Each test docstring names the FR it covers.

## Technical Decisions

- Eligibility, Returnable Quantity and Refund are pure functions in `app/domain/rules.py` taking every input, including `today`, as arguments. Routes and repositories never decide eligibility or compute money.
- `ReturnService.create_return` is the only writer of `returns`, `return_lines` and `inventory`. It opens `BEGIN IMMEDIATE`, re-reads the Order and quantities already returned, runs the domain checks, writes Return, lines, Restock (and, from story 2.2, Audit Entries), then commits once; any error rolls everything back. Single Uvicorn worker; `BEGIN IMMEDIATE` is the only concurrency control.
- Money is integer cents (`INTEGER` in SQLite, `int` in code, `_cents` in the API).
- Time only from the injected `Clock`; window rule `today <= delivered_on + timedelta(days=30)` on the UTC date. Timestamps are UTC ISO 8601 with a `Z` suffix.
- Errors: `DomainError(code)` mapped by the single handler to `{"error": {"code","message"}}`. `ORDER_NOT_FOUND` → 404; `ORDER_NOT_DELIVERED`, `RETURN_WINDOW_EXPIRED`, `INVALID_QUANTITY`, `LINE_NOT_ON_ORDER`, `VALIDATION_ERROR` → 422. `POST /returns` returns 201.
- Schema lives only in `app/infra/schema.sql` (`CREATE TABLE IF NOT EXISTS`); story 2.1 adds `returns` and `return_lines`, story 2.2 adds `audit_entries` plus triggers aborting UPDATE/DELETE. No migrations: a schema change means deleting the DB file. SQL only in `app/repositories/`. Return IDs are INTEGER autoincrement.
- Audit (story 2.2): only `AuditRepository.record(action, order_id, outcome, details)` writes entries; it masks emails (`a***@example.com`). Actions `ORDER_LOOKUP`, `RETURN_REQUESTED`, `REFUND_CALCULATED`, `RESTOCK_APPLIED`; outcomes `success`, `rejected`, `not_found`; `details` is a snake_case JSON object, rejections include `error_code`. Accepted-Return entries go in the return transaction; rejections and lookups commit their entry in a separate transaction. `GET /audit?order_id=` lists newest first. Never log or store a full email.
- Email only in POST bodies (`POST /returns`, `POST /orders/lookup`). Pydantic only in `app/api/schemas.py`; domain uses frozen dataclasses and imports no framework, DB or other app package.

## Cross-Story Dependencies

- Builds on epic 1: schema/seed, `Clock`, error handler, per-request connection, `OrderRepository`, `OrderService.lookup`, and the 1.2 rules (`returnable_quantity`, `is_returnable(..., returned_by_line)`, `email_matches`).
- Story 2.2 adds audit writes into the lookup and `ReturnService.create_return` code from 1.2 and 2.1; before 2.2 nothing is audited.
