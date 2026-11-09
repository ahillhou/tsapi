"""
TS API entry point.

Routes live in app/api/routes (one module per caller), business logic in
app/services, and outside-API wrappers in app/clients.
"""

from fastapi import FastAPI

from app.api.routes import debug, health, ringcentral, tdx
from app.core.logging import configure_logging

configure_logging()

app = FastAPI(title="TS API")

app.include_router(health.router)
app.include_router(tdx.router)
app.include_router(ringcentral.router)
app.include_router(debug.router)
