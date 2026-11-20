---
title: 'Story 1.1: Runnable service with seeded orders, health check and CI'
type: 'feature'
created: '2026-11-19'
status: 'done'
baseline_commit: 'd4811be762e413f09b71d3f83ed3c9ee713d25b4'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-retail-agent-2026-11-19/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The repo has only planning docs. Lab participants can't run anything, and no CI checks changes.

**Approach:** Set up the layered FastAPI project from scratch: schema and seed loaded at startup, `GET /healthz`, a single error envelope, an injectable `Clock`, pinned requirements, a Dockerfile and a GitHub Actions CI. Story 1.1 only; no order lookup (story 1.2).

## Boundaries & Constraints

**Always:** Layering and the domain import ban (AD-1/AD-8). `schema.sql` creates only `products`, `inventory`, `orders`, `order_lines` with `CREATE TABLE IF NOT EXISTS`. Money is INTEGER cents. Config only from `RETAIL_DB_PATH` (default `./data/retail.db`) via `app/infra/settings.py`. SQL only in `app/repositories/` and `app/infra/` (schema/seed). Every test docstring names the FR (or NFR/AD) it covers. Python 3.12, pins from the spine's Stack table.

**Never:** No `/orders/lookup`, `/returns`, `/audit`, domain eligibility rules or returns/audit tables. No `.env` files, no secrets, no ORM, no migrations. No `datetime.now()`/`date.today()` outside `app/infra/clock.py`. No git commits (the user commits). No installs beyond the pinned requirements without asking.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| First start | empty/missing DB file | dirs created, schema applied, seed loaded | N/A |
| Restart | seeded DB | no duplicate rows | N/A |
| Health OK | DB reachable with schema | 200 `{"status":"ok","database":"ok"}` | N/A |
| Health DB down | DB file missing/unopenable or `orders` table gone | 503 `{"error":{"code":"DATABASE_UNAVAILABLE",...}}` | `sqlite3.OperationalError` → 503 |
| Bad body | malformed JSON / schema violation on any POST | 422 `VALIDATION_ERROR` envelope | single handler |
| Unknown route | `GET /nope` | 404 envelope, code `NOT_FOUND` | single handler |
| Unhandled | unexpected exception | 500 envelope `INTERNAL_ERROR`, no stack trace in body | logged |

## Decisions

- **Seed reference date:** the `Clock`'s UTC date when the DB is first seeded, so the in-window and day-30 orders work live on a fresh DB. Tests pin the `Clock`. Reset by deleting the DB file.
- **Pins:** `requirements*.txt` pin exactly the direct packages from the spine's Stack table; sub-dependencies are resolved by pip.
- **Install:** verification installs only `requirements-dev.txt` (plus pip-resolved sub-dependencies) into a project `.venv`.

</frozen-after-approval>

## Code Map

Greenfield: no application code exists yet. Reuse nothing; do not change the planning artifacts or `CLAUDE.md`. `.gitignore` already ignores `.venv/`, `.env*` and `.coverage`, but not the `data/` DB directory.

## Tasks & Acceptance

**Execution:**
- [x] `requirements.txt`, `requirements-dev.txt` -- pinned per Stack table (dev includes `-r requirements.txt`) -- NFR4
- [x] `pyproject.toml` -- ruff config (py312), pytest config (`testpaths`, `pythonpath`), coverage config -- one tooling source
- [x] `app/__init__.py`, `app/{api,services,domain,repositories,infra}/__init__.py` -- package tree -- AD layering
- [x] `app/infra/settings.py` -- frozen `Settings(db_path)`, `load_settings()` reads env once -- config convention
- [x] `app/infra/clock.py` -- `Clock` protocol, `SystemClock` (UTC), `FixedClock` -- AD-4
- [x] `app/infra/schema.sql` -- the 4 tables with CHECKs (status in 4 values, qty > 0, cents ≥ 0, on_hand ≥ 0), FKs -- AD-7
- [x] `app/infra/db.py` -- `connect(path, create=False)` (`mode=rw` URI unless creating, `foreign_keys=ON`, `Row` factory), `init_db(path, today)` creates parent dir, applies schema, seeds -- AD-7
- [x] `app/infra/seed.py` -- fixed seed (products, inventory, ≥6 orders `ORD-1001`… covering all statuses; delivered at ref−12, ref−41, ref−30 days), inserted in one transaction only when `orders` is empty -- FR10
- [x] `app/domain/errors.py` -- `ErrorCode` StrEnum (`DATABASE_UNAVAILABLE`, `VALIDATION_ERROR`, `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTERNAL_ERROR`), `DomainError(code, message)` -- AD-6
- [x] `app/repositories/health.py` -- `HealthRepository.ping()` runs `SELECT 1 FROM orders LIMIT 1` -- SQL stays in repositories
- [x] `app/services/health_service.py` -- `HealthService.check()` converts `sqlite3.Error` to `DomainError(DATABASE_UNAVAILABLE)` -- FR9
- [x] `app/api/deps.py` -- `get_settings`, `get_clock`, `get_connection` (per-request, closed after) from `app.state` -- AD-4, AD-7
- [x] `app/api/errors.py` -- code→status map and handlers for `DomainError`, `RequestValidationError`, Starlette `HTTPException`, `sqlite3.OperationalError` (503), `Exception` (500) -- AD-6, NFR3
- [x] `app/api/schemas.py`, `app/api/health.py` -- `HealthResponse`, `ErrorResponse`; `GET /healthz` documents 200/503 -- FR9
- [x] `app/main.py` -- `create_app(settings=None, clock=None)` with lifespan `init_db`, logging to stdout, routers and handlers; `app = create_app()` -- FR9, FR10
- [x] `tests/conftest.py`, `tests/unit/`, `tests/api/` -- tests for every matrix row, settings default/env, clock, seed coverage and idempotency, schema has exactly 4 tables, `/docs` and `/openapi.json` list `/healthz`, domain import ban (AST), no `.env` files in repo -- FR9, FR10, NFR2–4, AD-1
- [x] `Dockerfile`, `.dockerignore` -- `python:3.12-slim`, non-root user, `RETAIL_DB_PATH=/data/retail.db`, `VOLUME /data`, uvicorn on 0.0.0.0:8000 -- NFR4
- [x] `.github/workflows/ci.yml` -- push/PR: setup Python 3.12, install dev reqs, `ruff check .`, `pytest --cov=app/domain --cov=app/services --cov-fail-under=90`, `pip-audit -r requirements.txt -r requirements-dev.txt` -- NFR2, NFR4
- [x] `.gitignore`, `README.md` -- ignore `data/`; short run instructions (local, Docker, tests) -- SM-1

**Acceptance Criteria:**
- Given pinned requirements installed, when `uvicorn app.main:app` runs, then the service starts and the seed is loaded into `./data/retail.db`.
- Given the Docker image, when run with a volume on `/data`, then `/healthz` returns 200 and the DB is at `/data/retail.db`.
- Given the CI commands run locally, when executed in order, then all pass with ≥90% coverage on domain and services.

## Implementation Notes

## Spec Change Log

## Review Triage Log

- 2026-11-19: Automated review layers (blind hunter, edge-case hunter, verification gap) skipped at the user's request; the user reviewed the change manually and approved it.

## Design Notes

A request connection opens with `mode=rw`, so a deleted DB file fails loudly as `DATABASE_UNAVAILABLE` rather than being silently recreated empty. Probing `orders` also catches a DB without the schema. The seed lives in infra as plain tuples: infra sits below domain and can't import it.

## Verification

**Commands:**
- `.venv/bin/ruff check .` -- expected: no errors
- `.venv/bin/pytest --cov=app/domain --cov=app/services --cov-fail-under=90` -- expected: all pass, gate met
- `.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt` -- expected: no known vulnerabilities
- `docker build -t retail-agent . && docker run --rm -d -p 8000:8000 -v retail-data:/data retail-agent; curl localhost:8000/healthz` -- expected: 200 ok
