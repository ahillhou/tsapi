import pytest

from conftest import PCR_LEGACY_URL, PCR_TEST_URL

DEBUG_ROUTES = [
    ("GET", "/envtest"),
    ("POST", "/test-so"),
    ("POST", "/test_attachment"),
    ("GET", "/ticket/777"),
    ("POST", "/process-ticket/777"),
    ("GET", "/test-fields/777"),
]


@pytest.mark.parametrize("method, path", DEBUG_ROUTES)
def test_debug_routes_are_hidden_by_default(client, http, method, path):
    response = client.request(method, path)

    assert response.status_code == 404
    assert http.calls == []


@pytest.fixture
def debug_client(make_client):
    return make_client(ENABLE_DEBUG_ROUTES="true")


def test_test_fields(debug_client):
    response = debug_client.get("/test-fields/777")

    assert response.json() == {"location": "Campus", "account_type": "Standard", "handset": "Yes"}


def test_test_so_uses_pcr_test(debug_client, http):
    response = debug_client.post("/test-so")

    assert response.status_code == 200
    assert [c["url"] for c in http.pcr_calls()] == [PCR_TEST_URL, PCR_LEGACY_URL]


def test_process_ticket_creates_test_sr(debug_client, http):
    response = debug_client.post("/process-ticket/777")

    assert response.status_code == 200
    [sr] = http.pcr_calls()
    assert sr["url"] == PCR_TEST_URL
    assert sr["json"]["description"] == "Form title"
