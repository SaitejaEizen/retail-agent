# Retail Returns Assistant (`retail-agent`)

A small REST service for a developer lab: look up mock orders and (in later stories) return items within 30 days. Built with Python 3.12, FastAPI and SQLite.

## Run locally

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app
```

Then open <http://localhost:8000/docs> for the interactive API docs, or check <http://localhost:8000/healthz>.

On first start the service creates `./data/retail.db` and loads a fixed set of seed orders (`ORD-1001` to `ORD-1006`). Delivery dates are relative to the day the database is first created, so `ORD-1001` is inside the 30-day return window, `ORD-1002` is past it, and `ORD-1003` is exactly on day 30. To reset the data, stop the service and delete `data/retail.db`.

Configuration is through environment variables only (no `.env` files):

| Variable | Default | Meaning |
| --- | --- | --- |
| `RETAIL_DB_PATH` | `./data/retail.db` | SQLite database file |

## Run in Docker

```bash
docker build -t retail-agent .
docker run --rm -p 8000:8000 -v retail-data:/data retail-agent
```

The container keeps its database at `/data/retail.db` on the mounted volume.

## Test and lint

These are the same checks CI runs on every push and pull request:

```bash
.venv/bin/ruff check .
.venv/bin/pytest --cov=app/domain --cov=app/services --cov-fail-under=90
.venv/bin/pip-audit -r requirements.txt -r requirements-dev.txt
```
