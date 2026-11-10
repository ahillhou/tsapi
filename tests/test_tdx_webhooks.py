import base64

import pytest
import requests
from conftest import PCR_PROD_URL, PCR_TEST_URL

from app.services import ringcentral_request
from app.services.tdx_remarks import (
    build_access_request_remarks,
    build_ringcentral_request_remarks,
)

PCR_HEADERS = {"Content-Type": "application/json", "Pcr-Html-Encoded": "TRUE"}


# ---- /tdx/webhook/access_request (production) -----------------------------


def test_access_request_creates_production_inquiry(client, http, ticket):
    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json() == {
        "status": "processed",
        "service_request": {"servicedesk": "SD-1"},
    }

    [call] = http.pcr_calls()
    assert call["url"] == PCR_PROD_URL
    assert call["headers"] == PCR_HEADERS
    assert call["json"] == {
        "type": "IQ",
        "email": "ahillhou@utk.edu",  # intentional, see pcr_access_request.py
        "subject": "Add PCR Access",
        "message": build_access_request_remarks(ticket),
        "topic": 482,
        "sdc": 6,
        "csr": 566,
    }


def test_access_request_makes_no_other_calls(client, http, ticket):
    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert len(http.calls) == 1


def test_access_request_pcr_error_returns_502(client, http, ticket):
    http.pcr_status = 400
    http.pcr_response = {"error": "bad topic"}

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 502
    assert response.json()["detail"]["status"] == "error"


def test_access_request_pcr_failure_body_with_http_200_returns_502(client, http, ticket):
    # PCR360 can report a failed write in the body while still returning 200.
    http.pcr_response = {"status": "failure", "message": "Invalid topic"}

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 502
    assert response.json()["detail"]["message"] == "Invalid topic"


def test_access_request_without_data_is_rejected(client, http):
    response = client.post("/tdx/webhook/access_request", json_body={"nope": {}})

    assert response.status_code == 422
    assert http.calls == []


# ---- /tdx/webhook (RingCentral Request form -> PCR360 test SO) -----------


def test_ringcentral_request_creates_so_with_attachments_in_one_call(client, http, ticket):
    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json()["service_request"] == {"servicedesk": "SD-1"}

    [so] = http.pcr_calls()  # no separate ATTACHMENT calls

    assert so["url"] == PCR_TEST_URL
    assert so["headers"] == PCR_HEADERS
    assert so["json"] == {
        "type": "SO",
        "csr": 1,
        "description": "RingCentral New Request",
        "remarks": build_ringcentral_request_remarks(ticket),
        "files": [
            {"filename": "a.pdf", "data": base64.b64encode(b"file:1").decode()},
            {"filename": "b.png", "data": base64.b64encode(b"file:2").decode()},
        ],
    }


def test_ringcentral_request_downloads_attachments_from_tdx(client, http, ticket):
    client.post("/tdx/webhook", json_body={"data": ticket})

    downloads = [c for c in http.calls if "/attachments/" in c["url"]]

    assert [c["url"] for c in downloads] == [
        "https://utk.teamdynamix.com/sbtdwebapi/api/attachments/1/content",
        "https://utk.teamdynamix.com/sbtdwebapi/api/attachments/2/content",
    ]
    assert all(c["headers"]["Authorization"] == "Bearer TDX-TOKEN-1" for c in downloads)
    assert http.tdx_logins == 1  # one login reused for both downloads


def test_ringcentral_request_pcr_failure_is_an_error(client, http, ticket):
    http.pcr_status = 500

    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 500


def test_ringcentral_request_failure_body_returns_502(client, http, ticket):
    http.pcr_response = {"status": "failure", "message": "Invalid sdc"}

    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 502
    assert len(http.pcr_calls()) == 1


def test_ringcentral_request_without_attachments_sends_no_files(client, http, ticket):
    ticket["Attachments"] = None

    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 200
    [so] = http.pcr_calls()
    assert "files" not in so["json"]


def test_pcr_html_error_page_is_shortened_in_logs(client, http, ticket, caplog, monkeypatch):
    http.pcr_status = 500
    html = "<html>" + "x" * 5000 + "</html>"

    def post(url, **kwargs):
        response = http.post(url, **kwargs)
        if "pcr-360.com" in url:
            response.text = html
        return response

    monkeypatch.setattr(requests, "post", post)

    with caplog.at_level("INFO", logger="app.clients.pcr360"):
        client.post("/tdx/webhook", json_body={"data": ticket})

    logged = [r.getMessage() for r in caplog.records if "SO status 500" in r.getMessage()]
    assert logged and all(len(m) < 500 for m in logged)


def test_ringcentral_request_puts_department_in_remarks(client, http, ticket):
    ticket["AccountName"] = "SPSF Student Health Services 115017"

    client.post("/tdx/webhook", json_body={"data": ticket})

    [so, *_] = http.pcr_calls()
    assert "Department: SPSF Student Health Services 115017<br><br>" in so["json"]["remarks"]


# ---- Department -> workflow (SDC) routing ---------------------------------


@pytest.fixture
def sdcs(monkeypatch):
    monkeypatch.setattr(ringcentral_request, "DESIGN_SDC", 11)
    monkeypatch.setattr(ringcentral_request, "DEFAULT_SDC", 22)


@pytest.mark.parametrize(
    "account_name",
    [
        # How TDX shows them: name, then the department number
        "SPSF Student Health Services 115017",
        "SPSF Student Counseling Services 115009",
        "CHEW Employee Wellness 113018",
        "OIT Technology Fee STF 111401",
        "One Stop 103008",
        "Athletic Information Tech 150012",
        "Police Control 110525",
        "VetMed Hospital Operations Administration 190500",
        "Digital Learning 103800",
        # Tolerate other layouts
        "115017 - SPSF Student Health Services",
        "Digital Learning (103800) ",
    ],
)
def test_design_departments_go_to_design_sdc(client, http, ticket, sdcs, account_name):
    ticket["AccountName"] = account_name

    client.post("/tdx/webhook", json_body={"data": ticket})

    [so, *_] = http.pcr_calls()
    assert so["json"]["sdc"] == 11


@pytest.mark.parametrize(
    "account_name",
    [
        "Some Other Dept 999999",
        "Member",
        "",
        None,
        "Not a match 1150170",
        "Not a match x115017",
        "Not a match 11501",
    ],
)
def test_other_departments_go_to_default_sdc(client, http, ticket, sdcs, account_name):
    ticket["AccountName"] = account_name

    client.post("/tdx/webhook", json_body={"data": ticket})

    [so, *_] = http.pcr_calls()
    assert so["json"]["sdc"] == 22


def test_missing_account_name_goes_to_default_sdc(client, http, ticket, sdcs):
    ticket.pop("AccountName", None)

    client.post("/tdx/webhook", json_body={"data": ticket})

    [so, *_] = http.pcr_calls()
    assert so["json"]["sdc"] == 22


def test_no_sdc_sent_until_configured(client, http, ticket):
    ticket["AccountName"] = "SPSF Student Health Services 115017"

    client.post("/tdx/webhook", json_body={"data": ticket})

    [so, *_] = http.pcr_calls()
    assert "sdc" not in so["json"]


# ---- /tdx/webhook/test_access_request (PCR360 test) -----------------------


def test_test_access_request_uses_pcr_test(client, http, ticket):
    response = client.post("/tdx/webhook/test_access_request", json_body={"data": ticket})

    assert response.status_code == 200

    inquiry, upload_a, upload_b = http.pcr_calls()
    assert inquiry["url"] == PCR_TEST_URL
    assert inquiry["json"]["email"] == "pat@example.edu"
    assert inquiry["json"]["topic"] == 349

    # Attachments go to the inquiry number PCR360 returned
    for upload, name in ((upload_a, "a.pdf"), (upload_b, "b.png")):
        assert upload["url"] == PCR_TEST_URL
        assert upload["json"]["sd_number"] == "SD-1"
        assert upload["json"]["files"][0]["filename"] == name


# ---- Outbound call hygiene ----------------------------------------------


def test_every_outbound_call_has_a_timeout(client, http, ticket):
    client.post("/tdx/webhook", json_body={"data": ticket})
    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert http.calls
    assert all(c["timeout"] for c in http.calls)
