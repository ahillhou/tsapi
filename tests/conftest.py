"""
Shared test setup.

No test talks to the real TDX, PCR360 or RingCentral: `requests` and the
RingCentral platform are replaced with fakes that record every call, so
tests can assert exactly what would have been sent.
"""

import asyncio
import copy
import json
import os

# Set before the app is imported. Values already in the environment win
# over app/.env, so real local secrets are never used by tests.
TEST_ENV = {
    "TDX_USERNAME": "tdx-user",
    "TDX_PASSWORD": "tdx-pass",
    "PCR_API_KEY": "KEY-LEGACY",
    "PCR_TEST_API_KEY": "KEY-TEST",
    "PCR_PROD_API_KEY": "KEY-PROD",
    "RC_CLIENT_ID": "rc-id",
    "RC_CLIENT_SECRET": "rc-secret",
    "RC_JWT_TOKEN": "rc-jwt",
    "TDX_WEBHOOK_SECRET": "",
    "RINGCENTRAL_WEBHOOK_SECRET": "",
    "ENABLE_DEBUG_ROUTES": "",
    "LOG_LEVEL": "WARNING",
}
os.environ.update(TEST_ENV)

import pytest  # noqa: E402
import requests  # noqa: E402

from app.clients.ringcentral import auth as rc_auth  # noqa: E402
from app.core.config import get_settings  # noqa: E402

PCR_TEST_URL = "https://pcr360-test.utk.pcr-360.com/api/KEY-TEST/servicedesk.json"
PCR_PROD_URL = "https://pcr360.utk.pcr-360.com/api/KEY-PROD/servicedesk.json"
PCR_LEGACY_URL = "https://pcr360-test.utk.pcr-360.com/api/KEY-LEGACY/servicedesk.json"
TDX_BASE = "https://utk.teamdynamix.com/sbtdwebapi"

SAMPLE_TICKET = {
    "ID": 777,
    "Title": "Form title",
    "Description": "ACCT-123",
    "RequestorName": "Pat Doe",
    "RequestorEmail": "pat@example.edu",
    "WebUiUrl": "https://tdx/ticket/777",
    "Attributes": [
        {"Name": "PCR Type", "ValueText": "Add"},
        {"Name": "PCR New Users", "ValueText": "a, b"},
        {"Name": "RC Ext Options", "ValueText": "New"},
        {"Name": "RC Exist Ext", "ValueText": "4-1234"},
        {"Name": "RC Account Type", "ValueText": "Standard"},
        {"Name": "RC Location", "ValueText": "Campus"},
        {"Name": "RC Outbound ID", "ValueText": "Main"},
        {"Name": "RC Queue Options", "ValueText": "Yes"},
        {"Name": "RC Queue Options List", "ValueText": "Q1"},
        {"Name": "RC Physical Handset", "ValueText": "Yes"},
        {"Name": "RC Physical Handset Data Port", "ValueText": "P12"},
        {"Name": "RC DASH COA", "ValueText": "COA1"},
    ],
    "Attachments": [
        {"Name": "a.pdf", "ContentUri": "api/attachments/1/content"},
        {"Name": "b.png", "ContentUri": "api/attachments/2/content"},
    ],
}


@pytest.fixture
def ticket():
    return copy.deepcopy(SAMPLE_TICKET)


# --------------------------------------------------------------------------
# Fake HTTP (requests) for TDX and PCR360
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None, content=b""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.text = text if text is not None else json.dumps(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeHTTP:
    """Records requests.post/get calls and returns canned responses."""

    def __init__(self):
        self.calls = []
        self.pcr_status = 200
        self.pcr_response = {"servicedesk": "SD-1"}

    def post(self, url, headers=None, json=None, **kwargs):
        self.calls.append({"method": "POST", "url": url, "headers": headers, "json": json})

        if url == f"{TDX_BASE}/api/auth":
            return FakeResponse(text="TDX-TOKEN")

        return FakeResponse(self.pcr_status, self.pcr_response)

    def get(self, url, headers=None, params=None, **kwargs):
        self.calls.append({"method": "GET", "url": url, "headers": headers, "params": params})

        if url.startswith(f"{TDX_BASE}/api/tickets/"):
            return FakeResponse(json_data=copy.deepcopy(SAMPLE_TICKET))

        if "/attachments/" in url:
            return FakeResponse(content=b"file:" + url.rsplit("/", 2)[-2].encode())

        return FakeResponse(json_data={"recid": 42})

    def pcr_calls(self):
        return [c for c in self.calls if "pcr-360.com" in c["url"]]


# --------------------------------------------------------------------------
# Fake RingCentral platform
# --------------------------------------------------------------------------


class FakeRCResponse:
    def __init__(self, data):
        self._data = data

    def json_dict(self):
        return copy.deepcopy(self._data)


class FakePlatform:
    """
    Directory: extension 101 is "Nurse 101" (ID 101); extension number 1234
    is "Target Nurse" (ID 555). Every extension has the day-off rule unless
    its ID is in `no_rule_for`.
    """

    RULE = {"id": "r9", "displayName": "Nurses Out of Office Custom Rule", "enabled": False}

    def __init__(self):
        self.calls = []
        self.no_rule_for = set()

    def logged_in(self):
        return True

    def login(self, **kwargs):
        pass

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))

        if path.endswith("/interaction-rules"):
            ext_id = path.split("/extensions/")[1].split("/")[0]
            records = [] if ext_id in self.no_rule_for else [self.RULE]
            return FakeRCResponse({"records": records})

        if "/interaction-rules/" in path:
            return FakeRCResponse(self.RULE)

        if path == "/restapi/v1.0/account/~/extension":
            if params["page"] == 1:
                return FakeRCResponse(
                    {"records": [{"id": "555", "extensionNumber": 1234, "name": "Target Nurse"}]}
                )
            return FakeRCResponse({"records": []})

        ext_id = path.rsplit("/", 1)[1]
        return FakeRCResponse({"id": ext_id, "name": f"Nurse {ext_id}"})

    def put(self, path, body):
        self.calls.append(("PUT", path, body))
        return FakeRCResponse({})

    def patch(self, path, body):
        self.calls.append(("PATCH", path, body))
        return FakeRCResponse({})

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        return FakeRCResponse({"id": "sms-1"})

    def sms_sent(self):
        return [body for method, path, body in self.calls if path.endswith("/sms")]


@pytest.fixture(autouse=True)
def http(monkeypatch):
    fake = FakeHTTP()
    monkeypatch.setattr(requests, "post", fake.post)
    monkeypatch.setattr(requests, "get", fake.get)
    return fake


@pytest.fixture(autouse=True)
def rc(monkeypatch):
    fake = FakePlatform()
    monkeypatch.setattr(rc_auth, "_platform", fake)
    return fake


# --------------------------------------------------------------------------
# App + minimal ASGI test client (no extra HTTP library needed)
# --------------------------------------------------------------------------


class Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        return json.loads(self.body)


class Client:
    def __init__(self, app):
        self.app = app

    def request(self, method, path, json_body=None, content=None, headers=None, query=""):
        if json_body is not None:
            content = json.dumps(json_body).encode()
        elif isinstance(content, str):
            content = content.encode("utf-8")

        hdrs = [(b"content-type", b"application/json"), (b"host", b"test")]
        hdrs += [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]

        return asyncio.run(self._call(method, path, content or b"", hdrs, query.encode()))

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    async def _call(self, method, path, body, headers, query):
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query,
            "root_path": "",
            "headers": headers,
            "server": ("test", 80),
            "client": ("10.0.0.5", 50000),
        }
        sent = False
        messages = []

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            await asyncio.sleep(3600)

        async def send(message):
            messages.append(message)

        try:
            await self.app(scope, receive, send)
        except Exception:
            # The server already sent a 500; the exception is re-raised for
            # logging. The status is checked below.
            pass

        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        raw = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return Response(status, raw)


@pytest.fixture
def make_client(monkeypatch):
    """Build a client for an app created with extra env settings."""

    def _make(**env):
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        get_settings.cache_clear()

        from app.main import create_app

        return Client(create_app())

    yield _make

    get_settings.cache_clear()


@pytest.fixture
def client(make_client):
    return make_client()
