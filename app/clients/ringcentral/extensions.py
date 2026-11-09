"""RingCentral extension (user) lookups."""


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
