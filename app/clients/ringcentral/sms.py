import logging

from app.clients.ringcentral.errors import RingCentralError
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_sms(platform, to_number, message):
    payload = {
        "from": {
            "phoneNumber": get_settings().rc_sms_from_number,
        },
        "to": [
            {
                "phoneNumber": to_number,
            }
        ],
        "text": message,
    }

    logger.info("Sending SMS: %s", payload)

    response = platform.post(
        "/restapi/v1.0/account/~/extension/~/sms",
        payload,
    )

    return response.json_dict()


def send_reply(platform, to_number, message) -> bool:
    """
    Text a reply, logging (not raising) on failure, so a failed reply never
    undoes or hides the change that was already made. Returns True if sent.
    """

    try:
        send_sms(platform, to_number, message)
        return True
    except RingCentralError as exc:
        logger.error("SMS reply to %s failed: %s", to_number, exc)
        if exc.code == "MSG-304":
            logger.error(
                "The SMS sender %s is not an SMS-enabled number of the RingCentral "
                "user whose JWT is in app/.env",
                get_settings().rc_sms_from_number,
            )
    except Exception as exc:
        logger.error("SMS reply to %s failed: %s", to_number, type(exc).__name__)

    return False
