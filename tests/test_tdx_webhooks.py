import base64

import pytest
import requests
from conftest import PCR_PROD_URL, PCR_TEST_URL, TDX_PROD_BASE

from app.services import ringcentral_request
from app.services.tdx_remarks import (
    build_access_request_remarks,
    build_ringcentral_request_remarks,
)

PCR_HEADERS = {"Content-Type": "application/json", "Pcr-Html-Encoded": "TRUE"}


# ---- /tdx/webhook/access_request (production) -----------------------------


IQ_NUMBER = "IQ00000127"  # what creating an IQ actually returns (2026-11-10)
ATTACHMENT_HEADERS = {"Content-Type": "application/json"}


def _expected_inquiry(ticket):
    return {
        "type": "IQ",
        "email": "ahillhou@utk.edu",  # intentional, see pcr_access_request.py
        "subject": "Add PCR Access",
        "message": build_access_request_remarks(ticket),
        "topic": 482,
        "sdc": 6,
        "csr": 566,
    }


def _prod_attachment(name, file_id):
    return {
        "type": "ATTACHMENT",
        "sd_number": IQ_NUMBER,
        "files": [{"filename": name, "data": base64.b64encode(f"file:{file_id}".encode()).decode()}],
    }


@pytest.fixture
def iq(http):
    http.pcr_response = {"status": "success", "servicedesk": IQ_NUMBER}


def test_access_request_creates_production_inquiry(client, http, ticket, iq):
    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json() == {
        "status": "processed",
        "service_request": {"status": "success", "servicedesk": IQ_NUMBER},
    }

    inquiry = http.pcr_calls()[0]
    assert inquiry["url"] == PCR_PROD_URL
    assert inquiry["headers"] == PCR_HEADERS
    assert inquiry["json"] == _expected_inquiry(ticket)


def test_access_request_without_attachments_makes_one_call(client, http, ticket, iq):
    ticket["Attachments"] = []

    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    [call] = http.calls
    assert call["json"] == _expected_inquiry(ticket)


def test_access_request_copies_attachments_from_production_tdx_to_production_pcr(
    client, http, ticket, iq
):
    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    # Exactly: inquiry, then each file downloaded from PROD TDX and attached
    # to the PROD inquiry by its number, without Pcr-Html-Encoded. No remark.
    calls = [(c["method"], c["url"]) for c in http.calls]
    assert calls == [
        ("POST", PCR_PROD_URL),
        ("POST", f"{TDX_PROD_BASE}/api/auth"),
        ("GET", f"{TDX_PROD_BASE}/api/attachments/1/content"),
        ("POST", PCR_PROD_URL),
        ("GET", f"{TDX_PROD_BASE}/api/attachments/2/content"),
        ("POST", PCR_PROD_URL),
    ]

    _, upload_a, upload_b = http.pcr_calls()
    assert upload_a["headers"] == ATTACHMENT_HEADERS
    assert upload_a["json"] == _prod_attachment("a.pdf", "1")
    assert upload_b["headers"] == ATTACHMENT_HEADERS
    assert upload_b["json"] == _prod_attachment("b.png", "2")


def test_access_request_never_touches_the_tdx_sandbox_or_pcr_test(client, http, ticket, iq):
    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert not [c for c in http.calls if "sbtdwebapi" in c["url"] or "pcr360-test" in c["url"]]


def _remarks(http):
    return [c for c in http.pcr_calls() if c["json"]["type"] == "REMARKS"]


def test_rejected_attachment_leaves_a_note_and_still_returns_200(client, http, ticket, iq):
    http.pcr_fail_types = {"ATTACHMENT"}

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200
    [remark] = _remarks(http)
    assert remark["url"] == PCR_PROD_URL
    assert remark["headers"] == PCR_HEADERS
    assert remark["json"] == {
        "type": "REMARKS",
        "sd_number": IQ_NUMBER,
        "remarks": (
            "Attachment a.pdf could not be added (PCR360 rejected the file)<br><br>"
            "Attachment b.png could not be added (PCR360 rejected the file)<br><br>"
            "Please get these files from TDX Ticket ID# 777."
        ),
    }


def test_file_over_50mb_is_not_downloaded_and_is_noted(client, http, ticket, iq):
    ticket["Attachments"][0]["Size"] = 63 * 1024 * 1024

    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    downloads = [c["url"] for c in http.calls if "/attachments/" in c["url"]]
    assert downloads == [f"{TDX_PROD_BASE}/api/attachments/2/content"]

    [remark] = _remarks(http)
    assert remark["json"]["remarks"] == (
        "Attachment a.pdf (63.0 MB) is over the 50 MB limit and was not added<br><br>"
        "Please get these files from TDX Ticket ID# 777."
    )


def test_file_that_cannot_be_downloaded_is_noted(client, http, ticket, iq):
    http.tdx_missing_attachments = {"2"}

    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    uploads = [c for c in http.pcr_calls() if c["json"]["type"] == "ATTACHMENT"]
    assert [u["json"]["files"][0]["filename"] for u in uploads] == ["a.pdf"]

    [remark] = _remarks(http)
    assert remark["json"]["remarks"].startswith(
        "Attachment b.png could not be downloaded from TDX and was not added<br><br>"
    )


def test_failed_note_still_returns_200(client, http, ticket, iq):
    http.pcr_fail_types = {"ATTACHMENT", "REMARKS"}

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json()["service_request"]["servicedesk"] == IQ_NUMBER


def test_unexpected_attachment_error_still_returns_200(client, http, ticket, iq, monkeypatch):
    from app.services import pcr_access_request

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(pcr_access_request, "download_prod_attachment", boom)
    monkeypatch.setattr(pcr_access_request.pcr360, "upload_prod_attachment", boom)

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200


def test_failed_inquiry_attaches_nothing(client, http, ticket):
    http.pcr_status = 400
    http.pcr_response = {"error": "bad topic"}

    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 502
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


def test_ringcentral_request_creates_so_then_uploads_attachments(client, http, ticket):
    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json()["service_request"] == {"servicedesk": "SD-1"}

    so, upload_a, upload_b = http.pcr_calls()

    assert so["url"] == PCR_TEST_URL
    assert so["headers"] == PCR_HEADERS
    assert so["json"] == {
        "type": "SO",
        "csr": 1,
        "description": "RingCentral New Request",
        "remarks": build_ringcentral_request_remarks(ticket),
    }

    for upload, name, file_id in ((upload_a, "a.pdf", "1"), (upload_b, "b.png", "2")):
        assert upload["url"] == PCR_TEST_URL
        # No Pcr-Html-Encoded on attachments (PCR360 500s on the files list)
        assert upload["headers"] == {"Content-Type": "application/json"}
        assert upload["json"] == {
            "type": "ATTACHMENT",
            "sd_number": "SD-1",
            "files": [
                {
                    "filename": name,
                    "data": base64.b64encode(f"file:{file_id}".encode()).decode(),
                }
            ],
        }


def test_failed_attachment_still_returns_the_so(client, http, ticket, monkeypatch):
    def post(url, **kwargs):
        response = http.post(url, **kwargs)
        if kwargs["json"].get("type") == "ATTACHMENT":
            response.status_code = 500
            response.text = "<html>error</html>"
        return response

    monkeypatch.setattr(requests, "post", post)

    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json()["service_request"] == {"servicedesk": "SD-1"}


def test_pcr_errors_never_include_the_api_key(client, http, ticket, monkeypatch, caplog):
    def post(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(requests, "post", post)

    with caplog.at_level("INFO"):
        response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 500
    assert "KEY-TEST" not in caplog.text
    assert "KEY-TEST" not in response.body.decode()


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


def test_test_access_request_uses_sandbox_tdx_and_pcr_test(client, http, ticket, iq):
    http.pcr_fail_types = {"ATTACHMENT"}
    ticket["Attachments"] = ticket["Attachments"][:1]

    response = client.post("/tdx/webhook/test_access_request", json_body={"data": ticket})

    assert response.status_code == 200

    inquiry, upload, remark = http.pcr_calls()
    assert inquiry["url"] == PCR_TEST_URL
    assert inquiry["json"]["email"] == "pat@example.edu"
    assert inquiry["json"]["topic"] == 349

    # Attachments go to the inquiry number, downloaded from the TDX sandbox
    assert upload["url"] == PCR_TEST_URL
    assert upload["headers"] == ATTACHMENT_HEADERS
    assert upload["json"]["sd_number"] == IQ_NUMBER
    assert "sd_recid" not in upload["json"]
    assert remark["url"] == PCR_TEST_URL
    assert remark["json"]["sd_number"] == IQ_NUMBER

    downloads = [c["url"] for c in http.calls if "/attachments/" in c["url"]]
    assert downloads == ["https://utk.teamdynamix.com/sbtdwebapi/api/attachments/1/content"]
    assert not [c for c in http.calls if "pcr360.utk" in c["url"] or "/tdwebapi/" in c["url"]]


# ---- Outbound call hygiene ----------------------------------------------


def test_every_outbound_call_has_a_timeout(client, http, ticket):
    client.post("/tdx/webhook", json_body={"data": ticket})
    client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert http.calls
    assert all(c["timeout"] for c in http.calls)


def test_pcr_exception_traceback_has_no_api_key(monkeypatch):
    import traceback

    from app.clients import pcr360

    def post(url, **kwargs):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(requests, "post", post)

    with pytest.raises(pcr360.PCR360Error) as info:
        pcr360.create_service_order("d", "r")

    printed = "".join(traceback.format_exception(info.value))
    assert "KEY-TEST" not in printed


def test_pcr_http_error_traceback_has_no_api_key(http):
    import traceback

    from app.clients import pcr360

    http.pcr_status = 500

    with pytest.raises(pcr360.PCR360Error) as info:
        pcr360.create_service_order("d", "r")

    assert "HTTP 500" in str(info.value)
    assert "KEY-TEST" not in "".join(traceback.format_exception(info.value))


@pytest.mark.parametrize(
    "servicedesk, target",
    [
        ("IQ00000127", {"sd_number": "IQ00000127"}),
        ("SO-000079", {"sd_number": "SO-000079"}),
        (33359, {"sd_recid": 33359}),
        ("33359", {"sd_recid": 33359}),
    ],
)
def test_sd_target(servicedesk, target):
    from app.clients import pcr360

    assert pcr360.sd_target(servicedesk) == target
