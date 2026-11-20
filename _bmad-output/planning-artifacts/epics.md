---
status: final
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-retail-agent-2026-11-19/prd.md
  - _bmad-output/planning-artifacts/prds/prd-retail-agent-2026-11-19/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-retail-agent-2026-11-19/ARCHITECTURE-SPINE.md
---

# retail-agent - Epic Breakdown

## Overview

This document breaks the retail-agent PRD and architecture spine into stories that can be built one at a time. There is no UX document, because the product has no UI.

## Requirements Inventory

### Functional Requirements

- FR1: A Customer can retrieve an Order by order ID and email. A match returns the Order Status, Order Lines, delivery date and total. An unknown ID or a mismatched email gets the same "not found". Email matching ignores letter case.
- FR2: The lookup response shows the Return Window end date, whether the Order can be returned, the Returnable Quantity of each line, and any existing Returns with their Refunds.
- FR3: A Customer can submit a return request with the order ID, email, lines and quantities, plus an optional reason. An eligible request creates exactly one Return and its Refund. Repeated partial Returns are allowed up to the Returnable Quantity.
- FR4: A request is rejected with a specific reason if the Order isn't `delivered`, if it is past day 30 (day 30 is accepted, day 31 is not), if a quantity is ≤0 or more than the Returnable Quantity, if a line isn't on the Order, or if the ID and email don't match. A rejection changes nothing except the audit trail.
- FR5: Refund = sum over lines of unit price paid × quantity returned, exact to the cent. No fees, no shipping refund, prices tax-inclusive. The Refund is recorded, never paid out.
- FR6: An accepted Return adds the returned quantities back to Inventory. A rejected one leaves Inventory unchanged.
- FR7: Every lookup, return request (accepted or rejected, with its reason), Refund calculation and Restock writes an Audit Entry. Audit Entries are append-only and store a masked email.
- FR8: A caller can list Audit Entries newest first, optionally filtered by order ID.
- FR9: A health endpoint reports that the service is up and the DB is reachable. Interactive API docs cover every endpoint.
- FR10: On first start, a fixed set of seed Orders is loaded. It covers every Order Status, an Order inside the window, one past it, and one exactly on day 30.

### NonFunctional Requirements

- NFR1 (Consistency): Return creation, Refund, Restock and their Audit Entries all succeed together or all fail together.
- NFR2 (Testability): The date used for Return Window checks can be controlled in tests. Business logic has at least 90% test coverage.
- NFR3 (Errors): Errors use one consistent shape, with a machine-readable code and a message a person can read.
- NFR4 (Hygiene): No secrets in the repo. Dependencies pinned and scanned. Runs the same locally, in Docker and in CI.

### Additional Requirements

From the architecture spine (AD-n):
- No starter template. The first story sets up the project from scratch, using the source tree from the architecture spine.
- Layered packages `app/api`, `app/services`, `app/domain`, `app/repositories` and `app/infra`, with dependencies pointing downward only. The domain is pure: no fastapi, pydantic or sqlite3 imports (AD-1, AD-8).
- `ReturnService.create_return` is the only writer of returns and inventory, in a single `BEGIN IMMEDIATE` transaction (AD-2).
- Money is integer cents everywhere, and API fields end in `_cents` (AD-3).
- An injected `Clock` is the only source of time. The window rule is `today <= delivered_on + 30 days`, using the UTC date (AD-4).
- `AuditRepository.record` is the only audit writer. It masks emails. SQLite triggers block UPDATE and DELETE. Audit Entries follow a fixed action/outcome/details shape (AD-5).
- `DomainError(code)` is mapped to HTTP in one handler, with the envelope `{"error":{"code","message"}}`. 404 means `ORDER_NOT_FOUND`; 422 covers eligibility failures and `VALIDATION_ERROR` (AD-6).
- Stdlib `sqlite3`. `schema.sql` is applied at startup, and seed data loads only into an empty DB. No ORM and no migrations (AD-7).
- Email goes only in POST bodies. Endpoints: `POST /orders/lookup`, `POST /returns`, `GET /audit`, `GET /healthz`, `/docs` (AD-9).
- Config comes from environment variables (`RETAIL_DB_PATH`), never from `.env` files. Logging uses stdlib `logging` to stdout, with no full emails.
- Pinned `requirements.txt` and `requirements-dev.txt` (versions in the architecture spine's Stack table). The Dockerfile uses `python:3.12-slim`. GitHub Actions CI runs `ruff`, then `pytest --cov` with a 90% gate on domain and services, then `pip-audit`.

### UX Design Requirements

None. The product has no UI, and the API docs are the only interface.

### FR Coverage Map

- FR1: Epic 1 - Look up an Order by ID and email
- FR2: Epic 1 - Show return eligibility on lookup
- FR3: Epic 2 - Request a Return
- FR4: Epic 2 - Enforce eligibility rules
- FR5: Epic 2 - Calculate the Refund
- FR6: Epic 2 - Restock returned items
- FR7: Epic 2 - Record every action in the audit trail
- FR8: Epic 2 - Read the audit trail
- FR9: Epic 1 - Health endpoint and API docs
- FR10: Epic 1 - Seeded mock data

## Epic List

### Epic 1: Runnable service with order lookup
A lab participant can start the service locally or in Docker, with CI checking it on every push. A Customer can look up a seeded Order and see whether it can be returned.
**FRs covered:** FR1, FR2, FR9, FR10 (plus NFR2, NFR3, NFR4)

### Epic 2: Returns with refund, restock and audit trail
A Customer can return items within the window and get a correct Refund, and Inventory is restocked. Every action can be traced in the audit trail.
**FRs covered:** FR3, FR4, FR5, FR6, FR7, FR8 (plus NFR1, NFR2, NFR3)

## Epic 1: Runnable service with order lookup

A lab participant can start the service locally or in Docker, with CI checking it on every push. A Customer can look up a seeded Order and see whether it can be returned.

### Story 1.1: Runnable service with seeded orders, health check and CI

As a lab participant,
I want to clone the repo and start a working service with sample orders in one command, locally or in Docker,
So that I can explore the API straight away and every change I push is checked automatically.

**Acceptance Criteria:**

**Given** a fresh clone with pinned `requirements.txt` and `requirements-dev.txt`
**When** I install them and run `uvicorn app.main:app`
**Then** the service starts with the layered package tree from the architecture spine (`app/api`, `services`, `domain`, `repositories`, `infra`)
**And** `app/infra/schema.sql` creates only the `products`, `inventory`, `orders` and `order_lines` tables, with `CREATE TABLE IF NOT EXISTS` (AD-7)

**Given** an empty database
**When** the service starts
**Then** the fixed seed set is loaded: at least one Order in each Order Status, one delivered Order inside the window, one past it, and one delivered exactly 30 days before the seed reference date (FR10)
**And** restarting the service doesn't duplicate the seed rows
**And** the DB path comes from `RETAIL_DB_PATH`, with the default `./data/retail.db` and no `.env` file

**Given** the service is running
**When** I call `GET /healthz`
**Then** it returns 200 with `{"status": "ok", "database": "ok"}` after successfully running a query against the DB (FR9)
**And** it returns 503 with the standard error envelope and the code `DATABASE_UNAVAILABLE` if the DB can't be reached

**Given** the service is running
**When** I open `/docs`
**Then** interactive API docs list every endpoint (FR9)

**Given** the app is running
**When** any error is raised, including an invalid request body
**Then** one exception handler returns `{"error": {"code", "message"}}`, with `VALIDATION_ERROR` → 422 for malformed bodies (AD-6, NFR3)

**Given** the repo
**When** I build and run the `Dockerfile`, which is based on `python:3.12-slim`, with a volume mounted at `/data`
**Then** the container serves the same API with its DB at `/data/retail.db` (NFR4)

**Given** a push or pull request
**When** the GitHub Actions workflow runs
**Then** it runs `ruff check`, then `pytest --cov` with `--cov-fail-under=90` measured on `app/domain` and `app/services`, then `pip-audit`, and fails on any error (NFR2, NFR4)
**And** a test checks that `app/domain` imports nothing from `fastapi`, `pydantic`, `sqlite3` or other `app` packages (AD-1)
**And** the repo contains no secrets and no `.env` files

### Story 1.2: Look up an order and see return eligibility

As a Customer,
I want to look up my order with its order ID and my email,
So that I can see its status and whether I can still return items.

**Acceptance Criteria:**

**Given** a seeded delivered Order
**When** I `POST /orders/lookup` with its `order_id` and matching `email`
**Then** I get 200 with the Order Status, delivery date, Order Lines (`line_id`, SKU, quantity, `unit_price_cents`) and `total_cents` (FR1, AD-3, AD-9)
**And** the email matches regardless of letter case

**Given** an unknown `order_id`, or a known `order_id` with the wrong email
**When** I look it up
**Then** I get 404 with the code `ORDER_NOT_FOUND`, and both cases produce identical response bodies (FR1, AD-6)

**Given** a delivered Order and a `Clock` fixed by the test
**When** I look it up
**Then** the response includes `return_window_ends_on` (delivery date + 30 days), `is_returnable` and a `returnable_quantity` for each line (FR2)
**And** `is_returnable` is true on day 30 and false on day 31, as checked by unit tests against the pure domain rule `today <= delivered_on + 30 days` (AD-1, AD-4)

**Given** an Order in status `placed`, `shipped` or `cancelled`
**When** I look it up
**Then** `return_window_ends_on` is null and `is_returnable` is false

**Given** this story comes before Returns exist
**When** an Order is looked up
**Then** `returns` is an empty list and `returnable_quantity` equals the purchased quantity. Story 2.1 fills both in from real Returns.
**And** the current time comes only from the injected `Clock`. Nothing calls `date.today()` or `datetime.now()` outside it (AD-4)

## Epic 2: Returns with refund, restock and audit trail

A Customer can return items within the window and get a correct Refund, and Inventory is restocked. Every action can be traced in the audit trail.

### Story 2.1: Return items and receive a refund

As a Customer,
I want to return some or all items from a delivered order within 30 days,
So that I get a correct refund and the items go back into stock.

**Acceptance Criteria:**

**Given** a delivered Order inside the Return Window
**When** I `POST /returns` with `order_id`, `email`, `lines: [{line_id, quantity}]` and an optional `reason`
**Then** I get 201 with the Return and `refund_cents`, equal to the sum of `unit_price_cents × quantity` for each line, as integers (FR3, FR5, AD-3)
**And** `schema.sql` adds the `returns` and `return_lines` tables in this story

**Given** an accepted Return
**When** it is saved
**Then** each returned quantity is added to that Product's Inventory (FR6)
**And** the Return, its lines and the Restock are written by `ReturnService.create_return` in one `BEGIN IMMEDIATE` transaction that re-reads the quantities already returned before checking. If any write fails, everything rolls back (AD-2, NFR1)
**And** a test that forces a failure after the Return insert shows that neither the Return nor the Inventory changed

**Given** a line with 2 units, 1 of which was already returned
**When** I request 1 more
**Then** it is accepted, and a third request for that line is rejected with `INVALID_QUANTITY` (FR3, FR4)

**Given** any of these conditions
**When** I submit a return
**Then** I get 422 with the specific code, and Returns and Inventory are unchanged (FR4, AD-6):
- Order not `delivered` → `ORDER_NOT_DELIVERED`
- `today` is day 31 or later → `RETURN_WINDOW_EXPIRED` (day 30 is accepted)
- quantity ≤ 0 or more than `returnable_quantity` → `INVALID_QUANTITY`
- a `line_id` that isn't on the Order → `LINE_NOT_ON_ORDER`

**And** an unknown order or a wrong email gives 404 `ORDER_NOT_FOUND`

**Given** an Order with Returns
**When** I look it up with `POST /orders/lookup`
**Then** `returns` lists each Return with its `refund_cents`, and `returnable_quantity` reflects the units already returned (FR2)

**Given** the refund and eligibility rules
**When** they are unit tested
**Then** they are pure functions in `app/domain/rules.py`, with no DB, that take `today` as an argument (AD-1, AD-4)

### Story 2.2: Trace every action in the audit trail

As a lab participant,
I want every lookup and return attempt recorded in an append-only audit trail I can read,
So that I can trace exactly what the service did and why.

**Acceptance Criteria:**

**Given** this story
**When** the schema is applied
**Then** `schema.sql` adds the `audit_entries` table, plus triggers that abort any `UPDATE` or `DELETE` on it (AD-5)
**And** a test shows that an `UPDATE` and a `DELETE` on `audit_entries` both fail

**Given** a lookup that is found or not found
**When** it completes
**Then** one Audit Entry with `action=ORDER_LOOKUP` is written, with `outcome` set to `success` or `not_found` (FR7)

**Given** an accepted Return
**When** `ReturnService.create_return` commits
**Then** Audit Entries `RETURN_REQUESTED` (success), `REFUND_CALCULATED` (with `refund_cents` in details) and `RESTOCK_APPLIED` (with SKUs and quantities) are written in the same transaction as the Return (FR7, AD-2, NFR1)
**And** if that transaction rolls back, none of those entries remain

**Given** a rejected return request
**When** it is refused
**Then** one `RETURN_REQUESTED` entry with `outcome=rejected` and `details.error_code` is committed in its own transaction, while Returns and Inventory stay unchanged (FR4, FR7, AD-5)

**Given** any Audit Entry
**When** it is stored
**Then** it is written only through `AuditRepository.record`, its email is masked (for example `a***@example.com`), and the full email is never written to the DB or to logs (FR7, AD-5)
**And** the entry has an `id`, a UTC `created_at` with a `Z` suffix taken from the `Clock`, an `action`, an `outcome`, an `order_id`, and a snake_case JSON `details` field

**Given** existing Audit Entries
**When** I call `GET /audit`, with or without `?order_id=`
**Then** I get the entries newest first, filtered to that Order when one is given (FR8)

## Assumptions

1. Two epics with four stories, at the user's request, for a small learning project.
2. Story 1.1 sets up the project from scratch, because there is no starter template. It includes Docker and CI, so every later story runs through CI.
3. Tables are created only when a story needs them: catalogue and order tables in 1.1, `returns` and `return_lines` in 2.1, `audit_entries` in 2.2.
4. Story 1.2 shows `returns: []` and the full purchased quantity until story 2.1 adds real Returns, which keeps 1.2 independent of later stories.
5. All auditing (FR7, FR8) is consolidated in story 2.2. That story adds audit writes to the lookup and return code from earlier stories. Before 2.2 lands, no actions are audited.
6. The seed data is relative to a fixed seed reference date, so the "exactly day 30" Order is defined relative to that date. Tests pin the `Clock` instead of relying on the real date.
7. `GET /healthz` returns 503 with `DATABASE_UNAVAILABLE` when the DB can't be reached. The PRD only says "reports reachable", so this detail is my choice.
8. `POST /returns` returns 201 on success.
