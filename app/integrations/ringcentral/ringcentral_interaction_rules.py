import json


def get_interaction_rules(platform, extension_id):
    response = platform.get(
        f"/restapi/v2/accounts/~/extensions/{extension_id}/comm-handling/voice/interaction-rules"
    )

    return response.json_dict()


def get_interaction_rule(platform, extension_id, rule_id):
    response = platform.get(
        f"/restapi/v2/accounts/~/extensions/{extension_id}/comm-handling/voice/interaction-rules/{rule_id}"
    )

    return response.json_dict()


def find_dayoff_rule(platform, extension_id):
    rules = get_interaction_rules(platform, extension_id)

    for rule in rules.get("records", []):
        rule_name = rule.get("displayName", "").lower()

        if rule_name == "student health staff admin closing template":
            return rule

    return None


def update_interaction_rule(
    platform,
    extension_id,
    rule_id,
    enabled
):
    rule = get_interaction_rule(
        platform,
        extension_id,
        rule_id
    )

    rule["enabled"] = enabled

    response = platform.patch(
        f"/restapi/v2/accounts/~/extensions/{extension_id}/comm-handling/voice/interaction-rules/{rule_id}",
        rule
    )

    return response.json_dict()