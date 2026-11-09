import logging

from app.clients.ringcentral.auth import get_platform

logger = logging.getLogger(__name__)


def set_dnd(extension_id: str, enabled: bool):
    """Turn Do Not Disturb on or off for an extension."""

    status = "DoNotAcceptAnyCalls" if enabled else "TakeAllCalls"

    logger.info("Changing extension %s to %s", extension_id, status)

    response = get_platform().put(
        f"/restapi/v1.0/account/~/extension/{extension_id}/presence",
        {
            "dndStatus": status,
        },
    )

    logger.info("RingCentral presence update completed")

    return response
