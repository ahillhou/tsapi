"""
RingCentral v1 answering rules, used for call queues.

Queues (extension type "Department") use the v1 answering-rule API; user
extensions on this account refuse it (CMN-468) and use the v2 interaction
rules in interaction_rules.py instead.
"""

RULES_PAGE_SIZE = 100


def _rules_path(extension_id) -> str:
    return f"/restapi/v1.0/account/~/extension/{extension_id}/answering-rule"


def list_custom_rules(platform, extension_id) -> list[dict]:
    """Custom rules on an extension: each has `id`, `name`, `enabled`."""

    rules = []
    page = 1

    while True:
        data = platform.get(
            _rules_path(extension_id),
            {"type": "Custom", "page": page, "perPage": RULES_PAGE_SIZE},
        ).json_dict()

        rules += data.get("records", [])

        if page >= data.get("paging", {}).get("totalPages", 1):
            return rules

        page += 1


def set_rule_enabled(platform, extension_id, rule_id, enabled: bool) -> dict:
    """Turn one answering rule on or off; nothing else about it changes."""

    return platform.put(
        f"{_rules_path(extension_id)}/{rule_id}",
        {"enabled": enabled},
    ).json_dict()
