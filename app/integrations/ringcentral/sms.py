def send_sms(
    platform,
    to_number,
    message
):
    response = platform.post(
        "/restapi/v1.0/account/~/extension/~/sms",
        {
            "to": [
                {
                    "phoneNumber": to_number
                }
            ],
            "text": message
        }
    )

    return response.json_dict()