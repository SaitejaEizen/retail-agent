# Product brief: Retail Returns Assistant

## Product
- Customers can look up an order and its status
- Request a return within a 30-day window
- System computes the refund and restocks inventory
- Every action is logged to an audit trail
- Mock data (SQLite). No real payment or warehouse

## Tech constraints
- Python 3.12, FastAPI, Pydantic, SQLite
- REST endpoints, /docs (Swagger) and /healthz
- pytest suite, 90%+ coverage on business logic
- No secrets in the repo. Dependencies scanned and pinned
- Runs locally and in Docker. CI on GitHub Actions
