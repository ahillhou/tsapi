"""RingCentral SDK errors must never put tokens or secrets in logs."""

import json
import traceback

import pytest
import requests
from ringcentral.http.api_exception import ApiException
from ringcentral.http.api_response import ApiResponse

from app.clients.ringcentral import auth as rc_auth
from app.clients.ringcentral.errors import RingCentralError, SafePlatform

SECRET_TOKEN = "SECRET-BEARER-TOKEN"


def sdk_error(status=403, body=None):
    """A real SDK ApiException whose request carries a bearer token."""

    request = requests.Request(
        "POST",
        "https://platform.ringcentral.com/restapi/v1.0/account/~/extension/~/sms",
        headers={"Authorization": f"bearer {SECRET_TOKEN}"},
        json={"text": "hi"},
    ).prepare()

    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(
        body
        or {
            "errorCode": "FeatureNotAvailable",
            "message": "Phone number doesn't belong to extension",
            "errors": [{"errorCode": "MSG-304", "message": "Phone number doesn't belong to extension"}],
        }
    ).encode()

    exc = ApiException(ApiResponse(request, response), requests.HTTPError("403"))
    assert SECRET_TOKEN in str(exc)  # proves the SDK itself leaks it
    return exc


class FailingPlatform:
    def __init__(self, exc):
        self.exc = exc

    def logged_in(self):
        return True

    def post(self, *args, **kwargs):
        raise self.exc

    login = get = put = patch = post


def test_safe_platform_error_has_status_and_code_but_no_token():
    platform = SafePlatform(FailingPlatform(sdk_error()))

    with pytest.raises(RingCentralError) as info:
        platform.post("/sms", {})

    err = info.value
    assert err.status == 403
    assert err.code == "MSG-304"
    assert str(err) == "RingCentral HTTP 403 MSG-304: Phone number doesn't belong to extension"
    assert SECRET_TOKEN not in "".join(traceback.format_exception(err))


def test_failed_login_does_not_leak(monkeypatch):
    class NotLoggedIn(FailingPlatform):
        def logged_in(self):
            return False

    monkeypatch.setattr(rc_auth, "_platform", NotLoggedIn(sdk_error(400, {"error_description": "bad JWT"})))

    with pytest.raises(RingCentralError) as info:
        rc_auth.get_platform()

    assert str(info.value) == "RingCentral HTTP 400: bad JWT"
    assert SECRET_TOKEN not in "".join(traceback.format_exception(info.value))


def test_sms_failure_is_logged_without_token_and_explains_msg_304(client, rc, monkeypatch, caplog):
    exc = sdk_error()
    original_post = rc.post

    def post(path, body):
        if path.endswith("/sms"):
            raise exc
        return original_post(path, body)

    monkeypatch.setattr(rc, "post", post)

    with caplog.at_level("INFO"):
        response = client.post(
            "/demo/dayoff",
            json_body={"extensionId": "101", "command": "DAYOFF", "sender": "+15550001111"},
        )

    assert response.status_code == 200
    assert SECRET_TOKEN not in caplog.text
    assert all(r.exc_info is None for r in caplog.records)
    assert "MSG-304" in caplog.text
    assert "+18659749955 is not an SMS-enabled number" in caplog.text
