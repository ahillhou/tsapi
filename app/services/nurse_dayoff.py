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
import re

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

# Words that mean each command, so people can text it the way they'd say it:
# "Day off", "day-off", "I'm out today", "OOO", "Back!", "I'm back"...
# The first of these words in the text wins, so "Off today, back tomorrow"
# is DAYOFF and "Back from my day off" is BACK.
DAYOFF_WORDS = {"dayoff", "dayoffs", "off", "out", "ooo", "sick", "pto", "vacation"}
BACK_WORDS = {"back", "return", "returning", "returned"}

# A token that is an extension number: "1234", "x1234", "ext1234", "#1234".
_EXTENSION = re.compile(r"^(?:ext|x|#)?(\d{3,8})$")


def parse_command(message: str) -> dict | None:
    """
    'dayoff 1234' -> {'command': 'DAYOFF', 'target_extension': '1234'}

    Case, punctuation and extra words don't matter ("Day off ext. 1234",
    "I'm back!"). A text with neither command gets its first word as the
    command, which handle() then rejects.
    """

    # "Day-off" / "day off" -> "dayoff"; "ext. 1234" -> "ext 1234".
    text = re.sub(r"\bdays?[\s\-_]*offs?\b", "dayoff", message.lower())
    words = re.findall(r"[a-z0-9#]+", text)

    if not words:
        return None

    command = None
    target_extension = None

    for word in words:
        number = _EXTENSION.match(word)
        if number and target_extension is None:
            target_extension = number.group(1)
        elif command is None and word in DAYOFF_WORDS:
            command = "DAYOFF"
        elif command is None and word in BACK_WORDS:
            command = "BACK"

    return {
        "command": command or words[0].upper(),
        "target_extension": target_extension,
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
