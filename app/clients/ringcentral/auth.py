import logging
import threading

from ringcentral import SDK

from app.core.config import get_settings

logger = logging.getLogger(__name__)

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
        s = get_settings()

        if _platform is None:
            sdk = SDK(s.rc_client_id, s.rc_client_secret, s.rc_server_url)
            _platform = sdk.platform()

        if not _platform.logged_in():
            logger.info("Logging in to RingCentral")
            _platform.login(jwt=s.rc_jwt_token)

        return _platform
