import pytest

TDX_SECRET = "tdx-s3cret"
RC_SECRET = "rc-s3cret"

DAYOFF = {"command": "DAYOFF", "extensionId": "101", "sender": "+15555550100"}


@pytest.fixture
def secured(make_client):
    return make_client(TDX_WEBHOOK_SECRET=TDX_SECRET, RINGCENTRAL_WEBHOOK_SECRET=RC_SECRET)


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Webhook-Secret": "wrong"},
        {"X-Webhook-Secret": RC_SECRET},  # the other caller's secret
        {"X-Webhook-Secret": ""},
    ],
)
def test_tdx_rejects_bad_secret_before_calling_pcr(secured, http, ticket, headers):
    response = secured.post(
        "/tdx/webhook/access_request", json_body={"data": ticket}, headers=headers
    )

    assert response.status_code == 401
    assert http.calls == []


@pytest.mark.parametrize(
    "path",
    ["/tdx/webhook", "/tdx/webhook/access_request", "/tdx/webhook/test_access_request"],
)
def test_all_tdx_routes_are_protected(secured, http, ticket, path):
    assert secured.post(path, json_body={"data": ticket}).status_code == 401
    assert http.calls == []


def test_tdx_accepts_secret_header(secured, http, ticket):
    response = secured.post(
        "/tdx/webhook/access_request",
        json_body={"data": ticket},
        headers={"X-Webhook-Secret": TDX_SECRET},
    )

    assert response.status_code == 200
    assert http.pcr_calls()


def test_tdx_accepts_secret_query_param(secured, ticket):
    response = secured.post(
        "/tdx/webhook", json_body={"data": ticket}, query=f"key={TDX_SECRET}"
    )

    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/demo/dayoff", "/ringcentral/dnd", "/ringcentral/dayoff"])
def test_ringcentral_rejects_missing_secret(secured, rc, path):
    response = secured.post(path, json_body=DAYOFF)

    assert response.status_code == 401
    assert rc.calls == []


def test_ringcentral_rejects_tdx_secret(secured, rc):
    response = secured.post(
        "/demo/dayoff", json_body=DAYOFF, headers={"X-Webhook-Secret": TDX_SECRET}
    )

    assert response.status_code == 401
    assert rc.calls == []


def test_ringcentral_accepts_secret(secured, rc):
    response = secured.post(
        "/demo/dayoff", json_body=DAYOFF, headers={"X-Webhook-Secret": RC_SECRET}
    )

    assert response.status_code == 200
    assert rc.sms_sent()


def test_health_needs_no_secret(secured):
    assert secured.get("/health").status_code == 200


def test_unset_secret_leaves_routes_open(client, ticket):
    response = client.post("/tdx/webhook/access_request", json_body={"data": ticket})

    assert response.status_code == 200
