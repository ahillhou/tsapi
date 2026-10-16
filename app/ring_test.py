import os
from ringcentral import SDK

CLIENT_ID = os.getenv("RC_CLIENT_ID")
CLIENT_SECRET = os.getenv("RC_CLIENT_SECRET")
SERVER_URL = "https://platform.ringcentral.com"
JWT_TOKEN = os.getenv("RC_JWT_TOKEN")

sdk = SDK(
    CLIENT_ID,
    CLIENT_SECRET,
    SERVER_URL
)

print("CLIENT_ID:", os.getenv("RC_CLIENT_ID"))
print("CLIENT_SECRET:", os.getenv("RC_CLIENT_SECRET"))
print("JWT_TOKEN:", os.getenv("RC_JWT_TOKEN"))

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