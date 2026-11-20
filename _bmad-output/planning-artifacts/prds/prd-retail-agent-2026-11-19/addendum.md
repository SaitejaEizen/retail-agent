# Addendum: Retail Returns Assistant

This holds technology and delivery constraints from `docs/brief.md` and `CLAUDE.md`. They belong to architecture, not to the PRD's capability requirements.

## Stack (given)
- Python 3.12, FastAPI, Pydantic, SQLite.
- REST endpoints. Swagger UI at `/docs`. Health check at `/healthz` (covers PRD FR-9).
- pytest. At least 90% coverage on business logic.

## Delivery (given)
- Runs locally and in Docker.
- CI on GitHub Actions, running tests and coverage and scanning dependencies.
- Dependencies pinned. No secrets in the repo; `.env` files are never committed.
- Method: BMAD, with one commit per story (`feat(us-<id>): ...`).

## Implementation hints for architecture (not requirements)
- Store money as integer cents, or as `Decimal` handled through Pydantic. Never as float (PRD FR-5).
- Inject a clock so tests can check the Return Window boundaries on days 29, 30 and 31 (PRD §5 Testability).
- Write the Return, Refund, Restock and Audit Entries inside one SQLite transaction (PRD §5 Consistency).
