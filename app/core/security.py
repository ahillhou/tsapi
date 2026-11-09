"""
Shared-secret check for incoming webhooks.

Each caller (TDX, RingCentral) gets its own secret, set in app/.env:

    TDX_WEBHOOK_SECRET=...
    RINGCENTRAL_WEBHOOK_SECRET=...

The caller sends it in the `X-Webhook-Secret` header. If a platform can't
send custom headers, `?key=<secret>` on the URL also works, but the header
is preferred because URLs end up in access logs.

If a secret is not set, that caller's routes stay open (main.py logs a
warning at startup). This lets the code be deployed first and the secret turned on
once the caller has been configured to send it.
"""

import hmac
import logging
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

HEADER_NAME = "X-Webhook-Secret"
QUERY_NAME = "key"


def require_webhook_secret(
    caller: str,
    get_secret: Callable[[Settings], str | None],
):
    """Build a FastAPI dependency that checks `caller`'s webhook secret."""

    def check(request: Request) -> None:
        expected = get_secret(get_settings())

        if not expected:
            # Not configured yet; main.py logs a warning at startup.
            return

        provided = (
            request.headers.get(HEADER_NAME)
            or request.query_params.get(QUERY_NAME)
            or ""
        )

        if not hmac.compare_digest(provided.encode(), expected.encode()):
            logger.warning(
                "Rejected %s webhook %s from %s: bad or missing secret",
                caller,
                request.url.path,
                request.client.host if request.client else "unknown",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook secret",
            )

    return check


tdx_webhook = require_webhook_secret("TDX", lambda s: s.tdx_webhook_secret)

ringcentral_webhook = require_webhook_secret(
    "RingCentral", lambda s: s.ringcentral_webhook_secret
)
