# Epic 1 Context: Runnable service with order lookup

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Give lab participants a service they can clone and start with one command, locally or in Docker, with CI checking every push. It ships with a fixed set of seeded mock Orders, and a Customer can look one up by order ID and email to see its status and whether it can still be returned. This epic lays the foundation (project layout, schema, seed, error model, clock, CI) that the returns and audit epic builds on.

## Stories

- Story 1.1: Runnable service with seeded orders, health check and CI
- Story 1.2: Look up an order and see return eligibility

## Requirements & Constraints

- Lookup by order ID + email. An unknown ID and a wrong email both give the same "not found". Email matching ignores case.
- Lookup shows Order Status, Order Lines, delivery date, total, Return Window end date, whether the Order is returnable, the Returnable Quantity of each line, and existing Returns (empty until epic 2).
- Return Window: 30 days after delivery, day 30 included. Only `delivered` Orders can be returned.
- Health endpoint reports the service is up and the DB is reachable. Interactive API docs cover every endpoint.
- On first start a fixed seed set loads: every Order Status, one delivered Order inside the window, one past it, one exactly on day 30 relative to a fixed seed reference date. Never duplicated on restart.
- Errors use one shape with a machine-readable code and a human-readable message.
- The date used for window checks must be controllable in tests. Business logic (domain + services) has ≥90% coverage. Every test docstring names the FR it covers.
- No secrets, no `.env` files. Dependencies pinned and scanned. Same behaviour locally, in Docker and in CI.

## Technical Decisions

- Layers: `app/api` → `app/services` → `app/domain` / `app/repositories` → `app/infra`; dependencies point downward only. `app/domain` imports nothing from `fastapi`, `pydantic`, `sqlite3` or other `app` packages.
- Domain uses frozen dataclasses; Pydantic models live only in `app/api/schemas.py`.
- Money is integer cents everywhere; API fields end in `_cents`. No float/Decimal.
- Time comes only from `Clock` in `app/infra/clock.py`, overridden in tests via FastAPI `dependency_overrides`. Window rule: `today <= delivered_on + timedelta(days=30)`, `today` as UTC date.
- `DomainError(code)` is mapped to HTTP by one handler with the envelope `{"error": {"code", "message"}}`. `ORDER_NOT_FOUND` → 404; eligibility codes and `VALIDATION_ERROR` → 422.
- Stdlib `sqlite3`, no ORM, no migrations. `app/infra/schema.sql` is the only schema, applied with `CREATE TABLE IF NOT EXISTS` at startup; tables are added only by the story that needs them (epic 1: `products`, `inventory`, `orders`, `order_lines`). Seed loads only when `orders` is empty. One connection per request via a FastAPI dependency. SQL only in `app/repositories/` (seed loader excepted).
- Email only in POST bodies: `POST /orders/lookup`, `GET /healthz`, `/docs`.
- Config from environment variables read once in `app/infra/settings.py` (`RETAIL_DB_PATH`, default `./data/retail.db`). Logging via stdlib `logging` to stdout, never a full email.
- IDs: Order IDs are seeded strings (`ORD-1001`); Order Line IDs are INTEGER autoincrement. Dates `YYYY-MM-DD`; timestamps UTC with `Z`.
- Naming: snake_case, plural tables, `<Noun>Service`, `<Noun>Repository`, PRD glossary terms only.
- Pinned stack: Python 3.12, FastAPI 0.165.0, Pydantic 2.14.3, Uvicorn 0.54.0, pytest 9.2.0, pytest-cov 7.1.0, httpx 0.28.1, Ruff 0.17.5, pip-audit 2.10.1; `requirements.txt` (runtime) and `requirements-dev.txt` (tooling), installed with pip. Docker base `python:3.12-slim`.
- CI (GitHub Actions on push/PR): `ruff check` → `pytest --cov` with `--cov-fail-under=90` on `app/domain` + `app/services` → `pip-audit`.
- Tests: `tests/unit/` for pure domain, `tests/api/` with `TestClient`, a temp SQLite file and a fixed `Clock`.

## Cross-Story Dependencies

- Story 1.2 depends on 1.1's schema, seed, error handler, clock and DB dependency.
- Epic 2 extends the schema (`returns`, `return_lines`, `audit_entries`) and fills in `returns` / `returnable_quantity` on lookup.
