"""App factory: settings, clock, startup schema/seed, routers and error handlers."""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import audit, health, orders, returns
from app.api.errors import register_error_handlers
from app.infra.clock import Clock, SystemClock
from app.infra.db import init_db
from app.infra.settings import Settings, load_settings


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            stream=sys.stdout,
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or load_settings()
    clock = clock or SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(settings.db_path, clock.today())
        yield

    app = FastAPI(
        title="Retail Returns Assistant",
        version="0.1.0",
        description="Look up orders, return items within 30 days, and trace every action.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.clock = clock
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(orders.router)
    app.include_router(returns.router)
    app.include_router(audit.router)
    return app


configure_logging()
app = create_app()
