"""
Student Health nurse "day off" via SMS.

A RingCentral workflow forwards a text like "DAYOFF" or "BACK" (optionally
followed by an extension number, for managers). We turn the nurse's
"Nurses Out of Office Custom Rule" on or off and text back the result.
"""

import logging

from app.clients.ringcentral.auth import get_platform
from app.clients.ringcentral.errors import RingCentralError
from app.core.config import get_settings
from app.clients.ringcentral.extensions import (
    get_extension,
    get_extension_by_number,
)
from app.clients.ringcentral.interaction_rules import (
    find_dayoff_rule,
    update_interaction_rule,
)
from app.clients.ringcentral.sms import send_sms

logger = logging.getLogger(__name__)

COMMANDS = ("DAYOFF", "BACK")


def parse_command(message: str) -> dict | None:
    """'dayoff 1234' -> {'command': 'DAYOFF', 'target_extension': '1234'}"""

    parts = message.strip().upper().split()

    if not parts:
        return None

    return {
        "command": parts[0],
        "target_extension": parts[1] if len(parts) > 1 else None,
    }


class NurseDayOffService:

    def __init__(self, platform):
        self.platform = platform

    def handle(self, sender_extension: dict, message: str) -> str:
        parsed = parse_command(message)

        if not parsed:
            return "Invalid command."

        command = parsed["command"]

        if command not in COMMANDS:
            return "Invalid command. Use DAYOFF or BACK."

        target_extension_number = parsed["target_extension"]

        if not target_extension_number:
            # Nurse texting about themselves
            extension = get_extension(self.platform, sender_extension["id"])
        else:
            # Manager texting about someone else's extension number
            extension = get_extension_by_number(self.platform, target_extension_number)

        if not extension:
            return "Extension not found."

        rule = find_dayoff_rule(self.platform, extension["id"])

        if not rule:
            return f"Call rule not found for {extension['name']}."

        enabled = command == "DAYOFF"

        update_interaction_rule(self.platform, extension["id"], rule["id"], enabled)

        return (
            f"Call rule {'enabled' if enabled else 'disabled'} "
            f"for {extension['name']}."
        )


def handle_sms_command(extension_id: str, command: str, sender: str) -> str:
    """Apply the command, then text the result back to the sender."""

    platform = get_platform()

    result = NurseDayOffService(platform).handle({"id": extension_id}, command)

    logger.info("Day-off result for extension %s: %s", extension_id, result)

    try:
        send_sms(platform, sender, result)
    except RingCentralError as exc:
        logger.error("SMS reply to %s failed: %s", sender, exc)
        if exc.code == "MSG-304":
            logger.error(
                "The SMS sender %s is not an SMS-enabled number of the RingCentral "
                "user whose JWT is in app/.env",
                get_settings().rc_sms_from_number,
            )
    except Exception as exc:
        logger.error("SMS reply to %s failed: %s", sender, type(exc).__name__)

    return result
