"""
Student Health nurse "day off" via SMS.

A RingCentral workflow forwards a text like "DAYOFF" or "BACK" (optionally
followed by an extension number, for managers). We turn the nurse's
"Nurses Out of Office Custom Rule" on or off and text back the result.

A plain DAYOFF/BACK acts on the extension that owns the number the text
came from. (The workflow's own extension, sent as extensionId, is the
number everyone texts, ext 41100, so it says nothing about the sender.)
"""

import logging

from app.clients.ringcentral.auth import get_platform
from app.clients.ringcentral.extensions import (
    get_extension,
    get_extension_by_number,
    get_extension_by_phone_number,
)
from app.clients.ringcentral.interaction_rules import (
    find_dayoff_rule,
    update_interaction_rule,
)
from app.clients.ringcentral.sms import send_reply

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

    def handle(self, sender: str, message: str) -> str:
        """`sender` is the phone number the text came from."""

        parsed = parse_command(message)

        if not parsed:
            return "Invalid command."

        command = parsed["command"]

        if command not in COMMANDS:
            return "Invalid command. Use DAYOFF or BACK."

        target_extension_number = parsed["target_extension"]

        if not target_extension_number:
            # Nurse texting about themselves: the extension that owns the
            # number they texted from.
            owner = get_extension_by_phone_number(self.platform, sender)

            if not owner:
                return (
                    f"{command} needs your extension: this phone isn't on a RingCentral "
                    f"extension. Text {command} followed by your extension number."
                )

            extension = get_extension(self.platform, owner["id"])
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
    """
    Apply the command, then text the result back to the sender.

    `extension_id` is the workflow's own extension (ext 41100); it is only
    logged, never acted on.
    """

    platform = get_platform()

    result = NurseDayOffService(platform).handle(sender, command)

    logger.info("Day-off %r from %s (workflow ext %s): %s", command, sender, extension_id, result)

    send_reply(platform, sender, result)

    return result
