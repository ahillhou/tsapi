from app.integrations.ringcentral.nurse_directory import (
    get_extension_by_number,
    get_extension,
    is_student_health_staff
)

from app.integrations.ringcentral.ringcentral_interaction_rules import (
    find_dayoff_rule,
    update_interaction_rule
)

from app.sms_command_parser import parse_command


class NurseDayOffService:

    def __init__(self, platform):
        self.platform = platform

    def handle(
        self,
        sender_extension,
        message
    ):
        parsed = parse_command(message)

        if not parsed:
            return "Invalid command."

        command = parsed["command"]

        if command not in ["DAYOFF", "BACK"]:
            return (
                "Invalid command. "
                "Use DAYOFF or BACK."
            )

        target_extension_number = parsed["target_extension"]

        #
        # Nurse command
        #
        if not target_extension_number:

            extension = get_extension(
                self.platform,
                sender_extension["id"]
            )

        #
        # Manager command
        #
        else:

            extension = get_extension_by_number(
                self.platform,
                target_extension_number
            )

        if not extension:
            return "Extension not found."

        rule = find_dayoff_rule(
            self.platform,
            extension["id"]
        )

        if not rule:
            return (
                "Call rule not found for "
                f"{extension['name']}."
            )

        enabled = (
            command == "DAYOFF"
        )

        update_interaction_rule(
            self.platform,
            extension["id"],
            rule["id"],
            enabled
        )

        return (
            f"Call rule "
            f"{'enabled' if enabled else 'disabled'} "
            f"for {extension['name']}."
        )

    def handle_extension_command(
        self,
        extension_id,
        command
    ):

        rule = find_dayoff_rule(
            self.platform,
            extension_id
        )

        if not rule:
            return "Rule not found."

        enabled = command == "DAYOFF"

        update_interaction_rule(
            self.platform,
            extension_id,
            rule["id"],
            enabled
        )

        return (
            f"{rule['displayName']} "
            f"{'enabled' if enabled else 'disabled'}"
        )