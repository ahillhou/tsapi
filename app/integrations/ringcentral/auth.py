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


def get_platform():
    return platform