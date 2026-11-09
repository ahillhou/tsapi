from app.integrations.ringcentral.auth import get_platform


def set_dnd(extension_id: str, enabled: bool):

    status = (
        "DoNotAcceptAnyCalls"
        if enabled
        else "TakeAllCalls"
    )

    print(f"Changing extension {extension_id} to {status}")

    response = get_platform().put(
        f"/restapi/v1.0/account/~/extension/{extension_id}/presence",
        {
            "dndStatus": status
        }
    )

    print("RingCentral API call completed")

    return response
