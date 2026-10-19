from app.integrations.ringcentral.nurse_directory import (
    get_extension_by_number,
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

        target_extension_number = parsed["target_extension"]

        #
        # Nurse command
        #
        if not target_extension_number:
            extension = sender_extension

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

        if not is_student_health_staff(extension):
            return (
                "Extension is not assigned to "
                "Student Health Staff."
            )

        rule = find_dayoff_rule(
            self.platform,
            extension["id"]
        )

        if not rule:
            return (
                "No Day Off rule found."
            )

        if command == "DAYOFF":

            update_interaction_rule(
                self.platform,
                extension["id"],
                rule["id"],
                True
            )

            return (
                f"Day Off enabled for "
                f"{extension['name']}"
            )

        if command == "BACK":

            update_interaction_rule(
                self.platform,
                extension["id"],
                rule["id"],
                False
            )

            return (
                f"Day Off disabled for "
                f"{extension['name']}"
            )

        return (
            "Unknown command. "
            "Use DAYOFF or BACK."
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