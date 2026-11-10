"""
Safe RingCentral errors.

The SDK's ApiException message includes the full request, headers and all:
the bearer token on API calls, and the client ID/secret (Basic auth) on
login. Anything that logs or prints that exception leaks them. Every SDK
call goes through SafePlatform, which turns those exceptions into
RingCentralError carrying only the status and RingCentral's error body.
"""

import json

from ringcentral.http.api_exception import ApiException


class RingCentralError(Exception):
    """A failed RingCentral call. Holds no credentials or tokens."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def describe(exc: ApiException) -> RingCentralError:
    """Build a RingCentralError from the response only (never the request)."""

    try:
        response = exc.api_response().response()
    except Exception:
        response = None

    if response is None:
        return RingCentralError("RingCentral request failed (no response)")

    status = response.status_code
    code = None
    message = ""

    try:
        body = json.loads(response.text)
        code = body.get("errorCode")
        details = body.get("errors") or []
        if details and details[0].get("errorCode"):
            code = details[0]["errorCode"]
        message = body.get("message") or body.get("error_description") or ""
    except Exception:
        message = " ".join(response.text.split())[:200]

    text = f"RingCentral HTTP {status}"
    if code:
        text += f" {code}"
    if message:
        text += f": {message}"

    return RingCentralError(text, status=status, code=code)


class SafePlatform:
    """Wraps the SDK platform so its errors can't leak credentials."""

    def __init__(self, platform):
        self._platform = platform

    def _call(self, name, *args, **kwargs):
        try:
            return getattr(self._platform, name)(*args, **kwargs)
        except ApiException as exc:
            # "from None" so the original (credential-bearing) exception
            # isn't printed as the cause in tracebacks.
            raise describe(exc) from None

    def get(self, *args, **kwargs):
        return self._call("get", *args, **kwargs)

    def post(self, *args, **kwargs):
        return self._call("post", *args, **kwargs)

    def put(self, *args, **kwargs):
        return self._call("put", *args, **kwargs)

    def patch(self, *args, **kwargs):
        return self._call("patch", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._call("delete", *args, **kwargs)

    def login(self, *args, **kwargs):
        return self._call("login", *args, **kwargs)

    def logged_in(self):
        return self._platform.logged_in()
