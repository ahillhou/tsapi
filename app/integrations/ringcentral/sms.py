def send_sms(
    platform,
    to_number,
    message
):
    payload = {
        "from": {
            "phoneNumber": "+18659740716"
        },
        "to": [
            {
                "phoneNumber": to_number
            }
        ],
        "text": message
    }

    print("SMS PAYLOAD:")
    print(payload)

    response = platform.post(
        "/restapi/v1.0/account/~/extension/~/sms",
        payload
    )

    return response.json_dict()