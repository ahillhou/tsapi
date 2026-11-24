"""
TS API entry point.

Routes live in app/api/routes (one module per caller), business logic in
app/services, and outside-API wrappers in app/clients.
"""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.routes import debug, health, jobs, reports, ringcentral, tdx
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services import access_request_close

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the access request close-out timer if it is switched on."""

    task = None

    if get_settings().access_request_autoclose != "off":
        task = asyncio.create_task(access_request_close.run_forever())

    yield

    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="TS API", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(tdx.router)
    app.include_router(ringcentral.router)
    app.include_router(reports.router)
    app.include_router(jobs.router)

    if settings.enable_debug_routes:
        logger.warning("Debug routes are enabled (ENABLE_DEBUG_ROUTES=true)")
        app.include_router(debug.router)

    for name, secret in (
        ("TDX_WEBHOOK_SECRET", settings.tdx_webhook_secret),
        ("RINGCENTRAL_WEBHOOK_SECRET", settings.ringcentral_webhook_secret),
    ):
        if not secret:
            logger.warning("%s is not set; those webhooks are unauthenticated", name)

    return app


configure_logging()

app = create_app()
