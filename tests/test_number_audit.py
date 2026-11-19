"""GET /reports/number-audit: PCR360 production phone numbers vs RingCentral."""

import copy

import pytest
from conftest import PCR_PROD_URL

from app.clients import pcr360
from app.clients.ringcentral import auth as rc_auth
from app.clients.ringcentral import phone_numbers
from app.clients.ringcentral.errors import RingCentralError
from app.services import number_audit
from app.services.number_audit import (
    BOTH_FREE,
    PCR_ACTIVE_RC_UNASSIGNED,
    PCR_AVAILABLE_RC_ASSIGNED,
    RC_UNASSIGNED_NOT_IN_PCR,
    build_audit,
    ten_digits,
)

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


def test_each_problem_and_what_is_left_out():
    pcr = [
        _pcr("8650000002", "AVAILABLE"),  # RC assigned -> problem
        _pcr("8650000003", "ACTIVE"),  # RC unassigned -> problem
        _pcr("8650000004", "AVAILABLE"),  # RC unassigned -> free in both
        _pcr("8650000005", "ACTIVE"),  # RC assigned -> fine, not listed
        _pcr("8650000006", "INACTIVE"),  # RC unassigned -> not asked for
        _pcr("8650000099", "AVAILABLE"),  # not in RC at all -> not listed
    ]
    rc = [
        _rc("+18650000001", "CompanyNumber"),  # not in PCR, unassigned -> problem
        _rc("+18650000002", ext="41000"),
        _rc("+18650000003", "CompanyNumber", status="PortedIn"),
        _rc("+18650000004", "CompanyNumber"),
        _rc("+18650000005", ext="41001"),
        _rc("+18650000006", "CompanyNumber"),
        _rc("+18650000007", "IntegrationNumber", ext="41002"),  # assigned, not in PCR -> fine
    ]

    rows = build_audit(pcr, rc)

    assert rows == [
        {"Problem": RC_UNASSIGNED_NOT_IN_PCR, "Number": "865-000-0001", "PCR360 Status": "",
         "RingCentral Type": "CompanyNumber", "RingCentral Status": "Normal", "RingCentral Extension": ""},
        {"Problem": PCR_AVAILABLE_RC_ASSIGNED, "Number": "865-000-0002", "PCR360 Status": "AVAILABLE",
         "RingCentral Type": "DirectNumber", "RingCentral Status": "Normal", "RingCentral Extension": "41000"},
        {"Problem": PCR_ACTIVE_RC_UNASSIGNED, "Number": "865-000-0003", "PCR360 Status": "ACTIVE",
         "RingCentral Type": "CompanyNumber", "RingCentral Status": "PortedIn", "RingCentral Extension": ""},
        {"Problem": BOTH_FREE, "Number": "865-000-0004", "PCR360 Status": "AVAILABLE",
         "RingCentral Type": "CompanyNumber", "RingCentral Status": "Normal", "RingCentral Extension": ""},
    ]


def test_rows_sorted_by_problem_then_number():
    rc = [_rc("+18650000009", "CompanyNumber"), _rc("+18650000002", ext="1"), _rc("+18650000001", "CompanyNumber")]
    pcr = [_pcr("8650000002", "AVAILABLE")]

    assert [(r["Problem"], r["Number"]) for r in build_audit(pcr, rc)] == [
        (RC_UNASSIGNED_NOT_IN_PCR, "865-000-0001"),
        (RC_UNASSIGNED_NOT_IN_PCR, "865-000-0009"),
        (PCR_AVAILABLE_RC_ASSIGNED, "865-000-0002"),
    ]


def test_duplicate_pcr_number_uses_the_most_in_use_status():
    pcr = [_pcr("865-000-0002", "AVAILABLE"), _pcr("8650000002", "ACTIVE")]

    assert build_audit(pcr, [_rc("+18650000002", ext="41000")]) == []


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


def test_route_returns_csv_and_reads_only_production_pcr(report_client, http, numbers):
    http.sql_results = [_pcr("8650000002", "AVAILABLE")]

    response = report_client.get(PATH, headers=SECRET)

    assert response.status_code == 200
    lines = response.body.decode().split("\r\n")
    assert lines[0] == "Problem,Number,PCR360 Status,RingCentral Type,RingCentral Status,RingCentral Extension"
    assert lines[1] == "\"RingCentral unassigned, not in PCR360\",865-000-0001,,CompanyNumber,Normal,"
    assert lines[2] == "\"PCR360 Available, RingCentral assigned\",865-000-0002,AVAILABLE,DirectNumber,Normal,41000"
    assert [c["url"] for c in http.calls] == [PCR_PROD_SQL_URL]


def test_route_needs_the_reports_secret(report_client, http, numbers):
    assert report_client.get(PATH).status_code == 401
    assert http.calls == [] and numbers.calls == []


def test_route_pcr_failure_is_502(report_client, http, numbers):
    http.sql_status = 400
    http.sql_response = {"status": "failure", "message": "SQL is not valid"}

    response = report_client.get(PATH, headers=SECRET)

    assert response.status_code == 502
    assert "KEY-PROD" not in response.body.decode()


def test_number_audit_logs_counts(http, numbers, caplog):
    http.sql_results = []

    with caplog.at_level("INFO", logger="app.services.number_audit"):
        rows = number_audit.number_audit()

    assert [r["Problem"] for r in rows] == [RC_UNASSIGNED_NOT_IN_PCR]
    assert "Number audit: 0 PCR360 phone services, 2 RingCentral numbers" in caplog.text
