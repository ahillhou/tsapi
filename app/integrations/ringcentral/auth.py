import logging
import os
import threading

from ringcentral import SDK

logger = logging.getLogger(__name__)

SERVER_URL = "https://platform.ringcentral.com"

_platform = None
_lock = threading.Lock()


def get_platform():
    """
    Return a logged-in RingCentral platform.

    Login happens on first use instead of at import time, so a RingCentral
    outage or bad credentials can't stop the app (and the TDX webhooks)
    from starting. If the session has expired (e.g. the refresh token aged
    out on a long-running container), log in again with the JWT.
    """
    global _platform

    with _lock:
        if _platform is None:
            sdk = SDK(
                os.getenv("RC_CLIENT_ID"),
                os.getenv("RC_CLIENT_SECRET"),
                SERVER_URL,
            )
            _platform = sdk.platform()

        if not _platform.logged_in():
            logger.info("Logging in to RingCentral")
            _platform.login(jwt=os.getenv("RC_JWT_TOKEN"))

        return _platform
