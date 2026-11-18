"""
Parking & Transportation event messages, switched by text.

OIT sets up one custom rule per event on the Parking Customer Service queue
in the RingCentral admin portal, named "Event - <name>" (for example
"Event - Football"). Each one has the event recording as its welcome
greeting, the queue's business hours as its schedule, the same agents and
wait settings as the queue, and starts turned off.

Approved staff then text the workflow number:

    FOOTBALL ON    turn on that event's message (any other one goes off)
    FOOTBALL OFF   turn it off
    EVENT OFF      turn every event message off
    STATUS         say which message is on
    anything else  list the commands and events

The only thing this changes is whether a rule is on. Recordings, agents and
wait settings are whatever OIT set in the portal, so when the queue's
routing changes, the event rules need the same change there.
"""

import logging
import re

from app.clients.ringcentral.answering_rules import list_custom_rules, set_rule_enabled
from app.clients.ringcentral.auth import get_platform
from app.clients.ringcentral.errors import RingCentralError
from app.clients.ringcentral.sms import send_reply
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Fixed on purpose: production texts only ever touch Parking's real queue,
# test texts only the OIT Design test queue.
PARKING_QUEUE_ID = "1420646040"  # ext 46031, Parking Services
TEST_PARKING_QUEUE_ID = "560994041"  # ext 98765, OIT Design SMS Custom Rule Testing Queue

# "Event - Football", "event: Football", "Event – Home Football" -> the name.
EVENT_RULE_NAME = re.compile(r"^\s*event\s*[-–—:]\s*(\S.*?)\s*$", re.IGNORECASE)

ALL_OFF = {"EVENT OFF", "EVENTS OFF", "ALL OFF", "OFF"}

FAILED = "Sorry, that didn't work and nothing may have changed. Text STATUS to check, or contact OIT Telecom."


def event_name(rule_name: str | None) -> str | None:
    """'Event - Football' -> 'Football'; any other rule name -> None."""

    match = EVENT_RULE_NAME.match(rule_name or "")
    return match.group(1) if match else None


def _key(text: str) -> str:
    return " ".join(text.upper().split())


def parse_command(message: str) -> tuple[str, str | None]:
    """
    'football on' -> ('ON', 'FOOTBALL'); 'event off' -> ('ALL_OFF', None);
    'status' -> ('STATUS', None); anything else -> ('HELP', None).
    """

    text = _key(message or "")
    words = text.split()

    if text == "STATUS":
        return ("STATUS", None)

    if text in ALL_OFF:
        return ("ALL_OFF", None)

    if len(words) > 1 and words[-1] in ("ON", "OFF"):
        name = words[:-1]
        if len(name) > 1 and name[0] == "EVENT":  # "EVENT FOOTBALL ON"
            name = name[1:]
        return (words[-1], " ".join(name))

    return ("HELP", None)


def _digits(number: str) -> str:
    """Last 10 digits, so +1 (865) 555-0100 and 8655550100 match."""

    return re.sub(r"\D", "", number or "")[-10:]


def is_allowed_sender(sender: str) -> bool:
    allowed = {_digits(n) for n in get_settings().parking_event_senders}
    return bool(_digits(sender)) and _digits(sender) in allowed


def _names(events: dict) -> str:
    return ", ".join(name for name, _ in events.values()) or "none set up yet"


def _help(events: dict) -> str:
    return (
        "Text <EVENT> ON or <EVENT> OFF, EVENT OFF, or STATUS. "
        f"Events: {_names(events)}."
    )


def switch_event(platform, queue_id: str, message: str) -> str:
    """Apply one texted command to the queue's event rules; return the reply."""

    events = {}  # key -> (display name, rule)
    for rule in list_custom_rules(platform, queue_id):
        name = event_name(rule.get("name"))
        if name:
            events[_key(name)] = (name, rule)

    action, target = parse_command(message)
    on = [(name, rule) for name, rule in events.values() if rule.get("enabled")]

    if action == "STATUS":
        if not on:
            return "No event message is on."
        return f"Event message on: {', '.join(name for name, _ in on)}."

    if action == "HELP":
        return _help(events)

    if action == "ALL_OFF":
        for _, rule in on:
            set_rule_enabled(platform, queue_id, rule["id"], False)
        return "All event messages are off."

    if target not in events:
        return f"No event called {target}. {_help(events)}"

    name, rule = events[target]

    if action == "OFF":
        if rule.get("enabled"):
            set_rule_enabled(platform, queue_id, rule["id"], False)
        return f"{name} message is off."

    # ON: switch the others off first, so a failure part-way through never
    # leaves two messages playing.
    for _, other in on:
        if other["id"] != rule["id"]:
            set_rule_enabled(platform, queue_id, other["id"], False)

    if not rule.get("enabled"):
        set_rule_enabled(platform, queue_id, rule["id"], True)

    return (
        f"{name} message is on. Callers hear it during business hours "
        f"until you text {target} OFF."
    )


def handle_event_sms(queue_id: str, message: str, sender: str) -> dict:
    """
    Check the sender, apply the command, text back the result.

    Returns {"status": "ignored"} for numbers not in PARKING_EVENT_SENDERS
    (no reply is sent to them), otherwise {"status": "success"|"failed",
    "message": <the reply>}.
    """

    if not is_allowed_sender(sender):
        logger.warning("Parking event text from %s ignored: not an approved number", sender)
        return {"status": "ignored"}

    platform = get_platform()

    try:
        reply = switch_event(platform, queue_id, message)
        status = "success"
    except RingCentralError as exc:
        logger.error("Parking event command %r on queue %s failed: %s", message, queue_id, exc)
        reply = FAILED
        status = "failed"

    logger.info("Parking event %r from %s on queue %s: %s", message, sender, queue_id, reply)

    send_reply(platform, sender, reply)

    return {"status": status, "message": reply}
