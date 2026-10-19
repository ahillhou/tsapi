import os
from ringcentral import SDK

CLIENT_ID = os.getenv("RC_CLIENT_ID")
CLIENT_SECRET = os.getenv("RC_CLIENT_SECRET")
JWT_TOKEN = os.getenv("RC_JWT_TOKEN")
SERVER_URL = "https://platform.ringcentral.com"


sdk = SDK(
    CLIENT_ID,
    CLIENT_SECRET,
    SERVER_URL
)

platform = sdk.platform()
platform.login(jwt=JWT_TOKEN)

def set_dnd(extension_id: str, enabled: bool):

    status = (
        "DoNotAcceptAnyCalls"
        if enabled
        else "TakeAllCalls"
    )

    print(f"Changing extension {extension_id} to {status}")

    response = platform.put(
        f"/restapi/v1.0/account/~/extension/{extension_id}/presence",
        {
            "dndStatus": status
        }
    )

    print("RingCentral API call completed")

    return response

# def test_disable_pam_dayoff():

#     extension_id = "1017318040"
#     rule_id = "459804040"

#     # Get the rule
#     response = platform.get(
#         f"/restapi/v2/accounts/~/extensions/{extension_id}/comm-handling/voice/interaction-rules/{rule_id}"
#     )

#     rule = response.json_dict()

#     print("Current Enabled State:")
#     print(rule["enabled"])

#     # Disable it
#     rule["enabled"] = True

#     response = platform.patch(
#         f"/restapi/v2/accounts/~/extensions/{extension_id}/comm-handling/voice/interaction-rules/{rule_id}",
#         rule
#     )

#     print(response.json_dict())


# if __name__ == "__main__":
#     test_disable_pam_dayoff()