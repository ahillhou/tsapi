"""GET /reports/ringcentral/unused-licenses"""

import copy
from datetime import datetime, timezone

import pytest

from app.clients.ringcentral import auth as rc_auth
from app.clients.ringcentral.errors import RingCentralError
from app.services import ringcentral_reports

PATH = "/reports/ringcentral/unused-licenses"
SECRET = {"X-Webhook-Secret": "report-secret"}


class Resp:
    def __init__(self, data):
        self._data = data

    def json_dict(self):
        return copy.deepcopy(self._data)


def _user(ext_id, number, name, dept="", email=""):
    return {
        "id": ext_id,
        "extensionNumber": number,
        "name": name,
        "type": "User",
        "status": "Enabled",
        "contact": {"email": email, "department": dept},
    }


class ReportPlatform:
    """Two extension pages, two analytics pages."""

    EXTENSION_PAGES = {
        1: [
            _user(1, "1001", "Busy Person", "OIT", "busy@example.edu"),
            _user(2, "1002", "Zed Idle", "OIT", "zed@example.edu"),
        ],
        2: [
            _user(3, "1003", "=HYPERLINK(\"x\")", "Athletics"),
            _user(4, "1004", "Never In Analytics", "Athletics"),
        ],
    }

    ANALYTICS_PAGES = {
        1: [{"key": "1", "counters": {"allCalls": {"valueType": "Instances", "values": 12.0}}}],
        2: [
            {"key": "2", "counters": {"allCalls": {"valueType": "Instances", "values": 0.0}}},
            {"key": "3", "counters": {"allCalls": {"valueType": "Instances", "values": 0}}},
        ],
    }

    def __init__(self):
        self.calls = []
        self.fail = False

    def logged_in(self):
        return True

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        page = params["page"]
        return Resp({"records": self.EXTENSION_PAGES.get(page, []), "paging": {"totalPages": 2}})

    def post(self, path, body=None, params=None):
        self.calls.append(("POST", path, body, params))
        if self.fail:
            raise RingCentralError("RingCentral HTTP 403 CMN-401: In order to call this API endpoint, application needs to have [Analytics] permission", 403, "CMN-401")
        page = params["page"]
        return Resp(
            {
                "paging": {"page": page, "perPage": 200, "totalPages": 2, "totalElements": 3},
                "data": {"groupedBy": "Users", "records": self.ANALYTICS_PAGES[page]},
            }
        )


@pytest.fixture
def report_rc(monkeypatch):
    fake = ReportPlatform()
    monkeypatch.setattr(rc_auth, "_platform", fake)
    return fake


@pytest.fixture
def report_client(make_client):
    return make_client(REPORTS_SECRET="report-secret")


def test_unused_licenses_lists_users_without_calls(report_rc):
    now = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)

    rows = ringcentral_reports.unused_licenses(180, now=now)

    assert [r["Extension ID"] for r in rows] == ["3", "4", "2"]  # Athletics, then OIT
    assert rows[2] == {
        "Extension": "1002",
        "Name": "Zed Idle",
        "Email": "zed@example.edu",
        "Department": "OIT",
        "Extension ID": "2",
        "Calls": 0,
    }


def test_unused_licenses_exact_requests(report_rc):
    now = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)

    ringcentral_reports.unused_licenses(180, now=now)

    body = {
        "grouping": {"groupBy": "Users"},
        "timeSettings": {
            "timeZone": "America/New_York",
            "timeRange": {
                "timeFrom": "2026-05-16T15:00:00+00:00",
                "timeTo": "2026-11-12T15:00:00+00:00",
            },
        },
        "responseOptions": {"counters": {"allCalls": {"aggregationType": "Sum"}}},
    }
    ext_params = {"type": "User", "status": "Enabled", "perPage": 1000}

    assert report_rc.calls == [
        ("GET", "/restapi/v1.0/account/~/extension", {**ext_params, "page": 1}),
        ("GET", "/restapi/v1.0/account/~/extension", {**ext_params, "page": 2}),
        ("POST", "/analytics/calls/v1/accounts/~/aggregation/fetch", body, {"page": 1, "perPage": 200}),
        ("POST", "/analytics/calls/v1/accounts/~/aggregation/fetch", body, {"page": 2, "perPage": 200}),
    ]


@pytest.mark.parametrize("days", [0, 185])
def test_days_outside_analytics_range_rejected(report_rc, days):
    with pytest.raises(ValueError):
        ringcentral_reports.unused_licenses(days)
    assert report_rc.calls == []


def test_route_returns_csv(report_client, report_rc):
    response = report_client.get(PATH, headers=SECRET, query="days=90")

    assert response.status_code == 200
    lines = response.body.decode().split("\r\n")
    assert lines[0] == "Extension,Name,Email,Department,Extension ID,Calls"
    assert lines[1] == "1003,\"'=HYPERLINK(\"\"x\"\")\",,Athletics,3,0"
    assert lines[3] == "1002,Zed Idle,zed@example.edu,OIT,2,0"


def test_route_closed_when_secret_not_set(client, report_rc):
    response = client.get(PATH, headers=SECRET)

    assert response.status_code == 503
    assert report_rc.calls == []


def test_route_rejects_wrong_secret(report_client, report_rc):
    response = report_client.get(PATH, headers={"X-Webhook-Secret": "nope"})

    assert response.status_code == 401
    assert report_rc.calls == []


def test_route_ignores_secret_in_url(report_client, report_rc):
    response = report_client.get(PATH, query="key=report-secret")

    assert response.status_code == 401
    assert report_rc.calls == []


def test_route_rejects_days_over_184(report_client, report_rc):
    response = report_client.get(PATH, headers=SECRET, query="days=200")

    assert response.status_code == 422
    assert report_rc.calls == []


def test_missing_permission_is_502_with_reason(report_client, report_rc):
    report_rc.fail = True

    response = report_client.get(PATH, headers=SECRET)

    assert response.status_code == 502
    assert "Analytics" in response.json()["detail"]
