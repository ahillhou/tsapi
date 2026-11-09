"""RingCentral call-handling (interaction) rules."""

DAYOFF_RULE_NAME = "nurses out of office custom rule"


def _rules_path(extension_id):
    return (
        f"/restapi/v2/accounts/~/extensions/{extension_id}"
        "/comm-handling/voice/interaction-rules"
    )


def get_interaction_rules(platform, extension_id):
    return platform.get(_rules_path(extension_id)).json_dict()


def get_interaction_rule(platform, extension_id, rule_id):
    return platform.get(f"{_rules_path(extension_id)}/{rule_id}").json_dict()


def find_dayoff_rule(platform, extension_id):
    """Find the Student Health "Nurses Out of Office Custom Rule"."""

    rules = get_interaction_rules(platform, extension_id)

    for rule in rules.get("records", []):
        if rule.get("displayName", "").lower() == DAYOFF_RULE_NAME:
            return rule

    return None


def update_interaction_rule(platform, extension_id, rule_id, enabled):
    rule = get_interaction_rule(platform, extension_id, rule_id)

    rule["enabled"] = enabled

    response = platform.patch(
        f"{_rules_path(extension_id)}/{rule_id}",
        rule,
    )

    return response.json_dict()
