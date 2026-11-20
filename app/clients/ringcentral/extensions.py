"""RingCentral extension (user) lookups."""

import re
from urllib.parse import quote


def to_e164(number: str) -> str | None:
    """'8655550100', '+1 (865) 555-0100', '18655550100' -> '+18655550100'."""

    digits = re.sub(r"\D", "", number or "")

    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def get_extension_by_phone_number(platform, phone_number: str) -> dict | None:
    """
    The extension a phone number belongs to ({"id", "extensionNumber"}), or
    None if it isn't on an extension (or isn't a RingCentral number at all).

    v2 phone-number list filtered to one exact number: one request, rate
    group Heavy, ReadAccounts. The "+" must be sent as %2B (the SDK leaves
    it bare and RingCentral answers CMN-101), so it goes in the path.
    """

    e164 = to_e164(phone_number)
    if not e164:
        return None

    data = platform.get(
        "/restapi/v2/accounts/~/phone-numbers?phoneNumber=" + quote(e164, safe="")
    ).json_dict()

    for record in data.get("records", []):
        if record.get("extension"):
            return record["extension"]

    return None


def get_extension_by_number(platform, extension_number):
    page = 1

    while True:
        response = platform.get(
            "/restapi/v1.0/account/~/extension",
            {
                "page": page,
                "perPage": 1000,
            },
        )

        records = response.json_dict().get("records", [])

        if not records:
            return None

        for ext in records:
            if str(ext.get("extensionNumber")) == str(extension_number):
                return ext

        page += 1


def get_extension(platform, extension_id):
    response = platform.get(
        f"/restapi/v1.0/account/~/extension/{extension_id}"
    )

    return response.json_dict()


def is_student_health_staff(extension):
    department = (
        extension.get("contact", {})
        .get("department", "")
        .lower()
    )

    return "student health staff" in department
