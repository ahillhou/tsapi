"""GET /reports/number-audit: PCR360 production phone numbers vs RingCentral."""

import copy

import pytest
from conftest import PCR_PROD_URL

from app.clients import pcr360
from app.clients.ringcentral import auth as rc_auth
from app.clients.ringcentral import phone_numbers
from app.clients.ringcentral.errors import RingCentralError
from app.services import number_audit
from app.services.number_audit import build_audit, summarize, ten_digits

PATH = "/reports/number-audit"
SECRET = {"X-Webhook-Secret": "report-secret"}
PCR_PROD_SQL_URL = PCR_PROD_URL.replace("servicedesk.json", "sql.json")


def _rc(number, usage="DirectNumber", ext=None, status="Normal"):
    record = {"phoneNumber": number, "usageType": usage, "status": status}
    if ext:
        record["extension"] = {"id": "9" + ext, "extensionNumber": ext}
    return record


def _pcr(number, status):
    return {"SERVICE_ID": number, "STATUS": status}


# ---- comparison ------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [("+18659740485", "8659740485"), ("(865) 974-0485", "8659740485"), ("8659740485", "8659740485"), ("40485", None), (None, None)],
)
def test_ten_digits(value, expected):
    assert ten_digits(value) == expected


def _view(rows):
    return [(r["Comparison"], r["Number"]) for r in rows]


def test_every_number_in_either_system_is_classified():
    pcr = [
        _pcr("8650000002", "AVAILABLE"),
        _pcr("8650000003", "ACTIVE"),
        _pcr("8650000004", "AVAILABLE"),
        _pcr("8650000005", "ACTIVE"),
        _pcr("8650000006", "INACTIVE"),
        _pcr("8650000010", "ACTIVE"),  # not in RingCentral
        _pcr("8650000011", "AVAILABLE"),  # not in RingCentral
        _pcr("8650000012", "ORDER_PENDING"),
        _pcr("40716", "ACTIVE"),  # too short to match a phone number: skipped
    ]
    rc = [
        _rc("+18650000001", "CompanyNumber"),
        _rc("+18650000002", ext="41000"),
        _rc("+18650000003", "CompanyNumber", status="PortedIn"),
        _rc("+18650000004", "CompanyNumber"),
        _rc("+18650000005", ext="41001"),
        _rc("+18650000006", "CompanyNumber"),
        _rc("+18650000007", "IntegrationNumber", ext="41002"),
        _rc("+18650000012", ext="41003"),
    ]

    rows = build_audit(pcr, rc)

    assert _view(rows) == [
        ("Not in PCR360, RingCentral unassigned", "865-000-0001"),
        ("Not in PCR360, RingCentral assigned", "865-000-0007"),
        ("PCR360 Active, not in RingCentral", "865-000-0010"),
        ("PCR360 Available, not in RingCentral", "865-000-0011"),
        ("PCR360 Available, RingCentral assigned", "865-000-0002"),
        ("PCR360 Active, RingCentral unassigned", "865-000-0003"),
        ("PCR360 Order Pending, RingCentral assigned", "865-000-0012"),
        ("PCR360 Inactive, RingCentral unassigned", "865-000-0006"),
        ("PCR360 Available, RingCentral unassigned", "865-000-0004"),
        ("PCR360 Active, RingCentral assigned", "865-000-0005"),
    ]

    by_number = {r["Number"]: r for r in rows}
    assert {k: v for k, v in by_number["865-000-0002"].items() if k != "_key"} == {
        "Comparison": "PCR360 Available, RingCentral assigned",
        "Number": "865-000-0002",
        "PCR360 Status": "AVAILABLE",
        "RingCentral Type": "DirectNumber",
        "RingCentral Status": "Normal",
        "RingCentral Extension": "41000",
    }
    assert {k: v for k, v in by_number["865-000-0010"].items() if k != "_key"} == {
        "Comparison": "PCR360 Active, not in RingCentral",
        "Number": "865-000-0010",
        "PCR360 Status": "ACTIVE",
        "RingCentral Type": "",
        "RingCentral Status": "",
        "RingCentral Extension": "",
    }


def test_summary_counts_in_listing_order():
    rows = build_audit(
        [_pcr("8650000001", "ACTIVE"), _pcr("8650000002", "ACTIVE"), _pcr("8650000003", "AVAILABLE")],
        [_rc("+18650000001", ext="1"), _rc("+18650000002", ext="2")],
    )

    assert summarize(rows) == {
        "PCR360 Available, not in RingCentral": 1,
        "PCR360 Active, RingCentral assigned": 2,
    }


def test_rows_sorted_by_comparison_then_number():
    rc = [_rc("+18650000009", "CompanyNumber"), _rc("+18650000002", ext="1"), _rc("+18650000001", "CompanyNumber")]
    pcr = [_pcr("8650000002", "AVAILABLE")]

    assert _view(build_audit(pcr, rc)) == [
        ("Not in PCR360, RingCentral unassigned", "865-000-0001"),
        ("Not in PCR360, RingCentral unassigned", "865-000-0009"),
        ("PCR360 Available, RingCentral assigned", "865-000-0002"),
    ]


def test_duplicate_numbers_are_listed_once():
    pcr = [_pcr("865-000-0002", "AVAILABLE"), _pcr("8650000002", "ACTIVE")]
    rc = [_rc("+18650000002", ext="41000"), _rc("+1 865 000 0002", ext="41000")]

    assert _view(build_audit(pcr, rc)) == [("PCR360 Active, RingCentral assigned", "865-000-0002")]


# ---- PCR360 production reader -----------------------------------------------


def test_prod_phone_numbers_queries_production_page_by_page(http, monkeypatch):
    monkeypatch.setattr(pcr360, "SQL_PAGE_SIZE", 1)
    http.sql_response = {"status": "success", "total_count": "3", "results": [_pcr("8650000001", "AVAILABLE")]}

    rows = pcr360.prod_phone_numbers()

    assert len(rows) == 3
    calls = http.pcr_calls()
    assert [c["url"] for c in calls] == [PCR_PROD_SQL_URL] * 3
    assert [c["json"] for c in calls] == [
        {"sql": pcr360.PHONE_NUMBERS_SQL, "limit": 1},
        {"sql": pcr360.PHONE_NUMBERS_SQL, "limit": 1, "page": 2},
        {"sql": pcr360.PHONE_NUMBERS_SQL, "limit": 1, "page": 3},
    ]
    assert pcr360.PHONE_NUMBERS_SQL.startswith("SELECT ")


def test_prod_phone_numbers_failure_raises_without_key(http):
    http.sql_response = {"status": "failure", "message": "The API key supplied does not allow you to execute queries."}

    with pytest.raises(pcr360.PCR360Error) as info:
        pcr360.prod_phone_numbers()

    assert "KEY-PROD" not in str(info.value)


# ---- RingCentral number list ------------------------------------------------


class Resp:
    def __init__(self, data):
        self._data = data

    def json_dict(self):
        return copy.deepcopy(self._data)


class NumbersPlatform:
    def __init__(self, pages, rate_limited=0):
        self.pages = pages
        self.rate_limited = rate_limited
        self.calls = []

    def logged_in(self):
        return True

    def get(self, path, params=None):
        self.calls.append((path, params))
        if self.rate_limited:
            self.rate_limited -= 1
            raise RingCentralError("RingCentral HTTP 429 CMN-301: Request rate exceeded", 429, "CMN-301")
        page = params["page"]
        return Resp({"records": self.pages[page - 1], "paging": {"page": page, "totalPages": len(self.pages)}})


def test_list_phone_numbers_pages_and_pauses():
    platform = NumbersPlatform([[_rc("+18650000001")], [_rc("+18650000002")]])
    sleeps = []

    numbers = phone_numbers.list_phone_numbers(platform, sleep=sleeps.append)

    assert [n["phoneNumber"] for n in numbers] == ["+18650000001", "+18650000002"]
    assert platform.calls == [
        ("/restapi/v1.0/account/~/phone-number", {"page": 1, "perPage": 1000}),
        ("/restapi/v1.0/account/~/phone-number", {"page": 2, "perPage": 1000}),
    ]
    assert sleeps == [phone_numbers.PAGE_PAUSE_SECONDS]


def test_list_phone_numbers_waits_out_rate_limit():
    platform = NumbersPlatform([[_rc("+18650000001")]], rate_limited=2)
    sleeps = []

    numbers = phone_numbers.list_phone_numbers(platform, sleep=sleeps.append)

    assert len(numbers) == 1
    assert sleeps == [phone_numbers.RATE_LIMIT_WAIT_SECONDS] * 2


def test_list_phone_numbers_gives_up_after_retries():
    platform = NumbersPlatform([[]], rate_limited=10)

    with pytest.raises(RingCentralError):
        phone_numbers.list_phone_numbers(platform, sleep=lambda s: None)

    assert len(platform.calls) == phone_numbers.RATE_LIMIT_RETRIES + 1


# ---- route ------------------------------------------------------------------


@pytest.fixture
def report_client(make_client):
    return make_client(REPORTS_SECRET="report-secret")


@pytest.fixture
def numbers(monkeypatch):
    platform = NumbersPlatform([[_rc("+18650000001", "CompanyNumber"), _rc("+18650000002", ext="41000")]])
    monkeypatch.setattr(rc_auth, "_platform", platform)
    monkeypatch.setattr(phone_numbers.time, "sleep", lambda s: None)
    return platform


def test_route_returns_csv_without_matches_by_default(report_client, http, numbers):
    http.sql_results = [_pcr("8650000002", "AVAILABLE"), _pcr("8650000003", "ACTIVE")]
    numbers.pages[0].append(_rc("+18650000003", ext="41001"))  # a match

    response = report_client.get(PATH, headers=SECRET)

    assert response.status_code == 200
    lines = response.body.decode().split("\r\n")
    assert lines[0] == "Comparison,Number,PCR360 Status,RingCentral Type,RingCentral Status,RingCentral Extension"
    assert lines[1:] == [
        "\"Not in PCR360, RingCentral unassigned\",865-000-0001,,CompanyNumber,Normal,",
        "\"PCR360 Available, RingCentral assigned\",865-000-0002,AVAILABLE,DirectNumber,Normal,41000",
        "",
    ]
    assert [c["url"] for c in http.calls] == [PCR_PROD_SQL_URL]


def test_route_can_include_matches(report_client, http, numbers):
    http.sql_results = [_pcr("8650000002", "ACTIVE")]

    response = report_client.get(PATH, headers=SECRET, query="include_matches=true")

    assert "\"PCR360 Active, RingCentral assigned\",865-000-0002" in response.body.decode()


def test_summary_route(report_client, http, numbers):
    http.sql_results = [_pcr("8650000002", "ACTIVE"), _pcr("8650000009", "AVAILABLE")]

    response = report_client.get(PATH + "/summary", headers=SECRET)

    assert response.status_code == 200
    assert response.json() == {
        "pcr360_phone_services": 2,
        "ringcentral_numbers": 2,
        "counts": {
            "Not in PCR360, RingCentral unassigned": 1,
            "PCR360 Available, not in RingCentral": 1,
            "PCR360 Active, RingCentral assigned": 1,
        },
    }


@pytest.mark.parametrize("path", [PATH, PATH + "/summary"])
def test_routes_need_the_reports_secret(report_client, http, numbers, path):
    assert report_client.get(path).status_code == 401
    assert http.calls == [] and numbers.calls == []


@pytest.mark.parametrize("path", [PATH, PATH + "/summary"])
def test_pcr_failure_is_502(report_client, http, numbers, path):
    http.sql_status = 400
    http.sql_response = {"status": "failure", "message": "SQL is not valid"}

    response = report_client.get(path, headers=SECRET)

    assert response.status_code == 502
    assert "KEY-PROD" not in response.body.decode()


def test_run_audit_logs_counts(http, numbers, caplog):
    http.sql_results = []

    with caplog.at_level("INFO", logger="app.services.number_audit"):
        audit = number_audit.run_audit()

    assert audit["ringcentral_numbers"] == 2
    assert "Number audit: 0 PCR360 phone services, 2 RingCentral numbers" in caplog.text
