import logging

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
