"""/tdx/webhook/project_intake (production) and /tdx/webhook/test_project_intake (test)."""

import base64

import pytest
from conftest import PCR_PROD_URL, PCR_TEST_URL, TDX_BASE, TDX_PROD_BASE

from app.services.tdx_remarks import build_project_intake_remarks

PR_NUMBER = "PR-000081"  # what creating a project returned on PCR360 test
PCR_HEADERS = {"Content-Type": "application/json", "Pcr-Html-Encoded": "TRUE"}
ATTACHMENT_HEADERS = {"Content-Type": "application/json"}

PROD = "/tdx/webhook/project_intake"
TEST = "/tdx/webhook/test_project_intake"


@pytest.fixture
def pr(http):
    http.pcr_response = {"status": "success", "page": "1", "count": 1, "servicedesk": PR_NUMBER}


@pytest.fixture
def intake(ticket):
    ticket["Title"] = "New building wiring"
    ticket["Description"] = "Wire the new annex"
    ticket["AccountName"] = "OIT Technology Fee STF 111401"
    ticket["Attributes"] = [
        {"Name": "Project Type", "ValueText": "Construction"},
        {"Name": "Empty Field", "ValueText": ""},
        {"Name": "Due Date", "ValueText": "2027-01-15"},
    ]
    return ticket


def _project(ticket, csr):
    return {
        "type": "PR",
        "csr": csr,
        "description": "New building wiring",
        "remarks": build_project_intake_remarks(ticket),
    }


def _attachment(name, file_id):
    return {
        "type": "ATTACHMENT",
        "sd_number": PR_NUMBER,
        "files": [{"filename": name, "data": base64.b64encode(f"file:{file_id}".encode()).decode()}],
    }


def test_remarks_list_filled_fields_then_requestor():
    ticket = {
        "ID": 9,
        "Description": "Wire the new annex",
        "RequestorName": "Pat Doe",
        "RequestorEmail": "pat@example.edu",
        "AccountName": "OIT 111401",
        "Attributes": [
            {"Name": "Project Type", "ValueText": "Construction"},
            {"Name": "Empty Field", "ValueText": ""},
            {"Name": "Notes", "ValueText": None},
        ],
    }

    assert build_project_intake_remarks(ticket) == (
        "Project Type: Construction<br><br>"
        "Description: Wire the new annex<br><br>"
        "Requestor Name: Pat Doe<br><br>"
        "Requestor Email: pat@example.edu<br><br>"
        "Department: OIT 111401<br><br>"
        "TDX Ticket ID#: 9<br><br>"
    )


def test_production_creates_project_and_copies_files_prod_to_prod(client, http, intake, pr):
    response = client.post(PROD, json_body={"data": intake})

    assert response.status_code == 200
    assert response.json()["service_request"]["servicedesk"] == PR_NUMBER

    calls = [(c["method"], c["url"]) for c in http.calls]
    assert calls == [
        ("POST", PCR_PROD_URL),
        ("POST", f"{TDX_PROD_BASE}/api/auth"),
        ("GET", f"{TDX_PROD_BASE}/api/attachments/1/content"),
        ("POST", PCR_PROD_URL),
        ("GET", f"{TDX_PROD_BASE}/api/attachments/2/content"),
        ("POST", PCR_PROD_URL),
    ]

    project, upload_a, upload_b = http.pcr_calls()
    assert project["headers"] == PCR_HEADERS
    assert project["json"] == _project(intake, csr=566)
    assert upload_a["headers"] == ATTACHMENT_HEADERS
    assert upload_a["json"] == _attachment("a.pdf", "1")
    assert upload_b["json"] == _attachment("b.png", "2")


def test_test_route_creates_project_and_copies_files_sandbox_to_test(client, http, intake, pr):
    response = client.post(TEST, json_body={"data": intake})

    assert response.status_code == 200

    calls = [(c["method"], c["url"]) for c in http.calls]
    assert calls == [
        ("POST", PCR_TEST_URL),
        ("POST", f"{TDX_BASE}/api/auth"),
        ("GET", f"{TDX_BASE}/api/attachments/1/content"),
        ("POST", PCR_TEST_URL),
        ("GET", f"{TDX_BASE}/api/attachments/2/content"),
        ("POST", PCR_TEST_URL),
    ]
    assert http.pcr_calls()[0]["json"] == _project(intake, csr=1)


def test_production_never_touches_sandbox_or_pcr_test(client, http, intake, pr):
    client.post(PROD, json_body={"data": intake})

    assert not [c for c in http.calls if "sbtdwebapi" in c["url"] or "pcr360-test" in c["url"]]


def test_test_route_never_touches_production(client, http, intake, pr):
    client.post(TEST, json_body={"data": intake})

    assert not [c for c in http.calls if "/tdwebapi" in c["url"] or "//pcr360.utk" in c["url"]]


def test_missing_title_gets_a_description(client, http, intake, pr):
    intake["Title"] = ""
    intake["Attachments"] = []

    client.post(PROD, json_body={"data": intake})

    [call] = http.calls
    assert call["json"]["description"] == "Project intake (TDX 777)"


@pytest.mark.parametrize("path", [PROD, TEST])
def test_pcr_failure_is_502_and_attaches_nothing(client, http, intake, path):
    http.pcr_response = {"status": "failure", "message": "Invalid csr"}

    response = client.post(path, json_body={"data": intake})

    assert response.status_code == 502
    assert len(http.calls) == 1


@pytest.mark.parametrize("path", [PROD, TEST])
def test_pcr_http_error_is_502(client, http, intake, path):
    http.pcr_status = 500

    response = client.post(path, json_body={"data": intake})

    assert response.status_code == 502


def test_rejected_attachment_leaves_note_on_project(client, http, intake, pr):
    http.pcr_fail_types = {"ATTACHMENT"}

    response = client.post(PROD, json_body={"data": intake})

    assert response.status_code == 200
    [remark] = [c for c in http.pcr_calls() if c["json"]["type"] == "REMARKS"]
    assert remark["url"] == PCR_PROD_URL
    assert remark["json"] == {
        "type": "REMARKS",
        "sd_number": PR_NUMBER,
        "remarks": (
            "Attachment a.pdf could not be added (PCR360 rejected the file)<br><br>"
            "Attachment b.png could not be added (PCR360 rejected the file)<br><br>"
            "Please get these files from TDX Ticket ID# 777."
        ),
    }


def test_api_key_never_in_502_detail(client, http, intake):
    http.pcr_status = 500

    response = client.post(PROD, json_body={"data": intake})

    assert "KEY-PROD" not in response.body.decode()


@pytest.mark.parametrize("path", [PROD, TEST])
def test_secret_required_when_set(make_client, http, intake, path):
    client = make_client(TDX_WEBHOOK_SECRET="s3cret")

    assert client.post(path, json_body={"data": intake}).status_code == 401
    assert http.calls == []
