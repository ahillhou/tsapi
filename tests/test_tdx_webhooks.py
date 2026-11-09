import base64

from conftest import PCR_PROD_URL, PCR_TEST_URL

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


def test_access_request_without_data_is_rejected(client, http):
    response = client.post("/tdx/webhook/access_request", json_body={"nope": {}})

    assert response.status_code == 422
    assert http.calls == []


# ---- /tdx/webhook (RingCentral request form -> PCR360 test SR) -----------


def test_ringcentral_request_creates_sr_and_uploads_attachments(client, http, ticket):
    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 200
    assert response.json()["service_request"] == {"servicedesk": "SD-1"}

    sr, upload_a, upload_b = http.pcr_calls()

    assert sr["url"] == PCR_TEST_URL
    assert sr["json"] == {
        "type": "SR",
        "csr": 1,
        "description": "RingCentral New Request",
        "remarks": build_ringcentral_request_remarks(ticket),
    }

    for upload, name, file_id in ((upload_a, "a.pdf", "1"), (upload_b, "b.png", "2")):
        assert upload["url"] == PCR_TEST_URL
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


def test_ringcentral_request_downloads_attachments_from_tdx(client, http, ticket):
    client.post("/tdx/webhook", json_body={"data": ticket})

    downloads = [c for c in http.calls if "/attachments/" in c["url"]]

    assert [c["url"] for c in downloads] == [
        "https://utk.teamdynamix.com/sbtdwebapi/api/attachments/1/content",
        "https://utk.teamdynamix.com/sbtdwebapi/api/attachments/2/content",
    ]
    assert all(c["headers"]["Authorization"] == "Bearer TDX-TOKEN" for c in downloads)


def test_ringcentral_request_pcr_failure_is_an_error(client, http, ticket):
    http.pcr_status = 500

    response = client.post("/tdx/webhook", json_body={"data": ticket})

    assert response.status_code == 500


# ---- /tdx/webhook/test_access_request (PCR360 test) -----------------------


def test_test_access_request_uses_pcr_test(client, http, ticket):
    response = client.post("/tdx/webhook/test_access_request", json_body={"data": ticket})

    assert response.status_code == 200

    inquiry = http.pcr_calls()[0]
    assert inquiry["url"] == PCR_TEST_URL
    assert inquiry["json"]["email"] == "pat@example.edu"
    assert inquiry["json"]["topic"] == 349
    assert all(c["url"] == PCR_TEST_URL for c in http.pcr_calls())
