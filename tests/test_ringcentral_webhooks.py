import pytest

from app.services.nurse_dayoff import parse_command

NBSP = " "
RULE_PATH = "/restapi/v2/accounts/~/extensions/{}/comm-handling/voice/interaction-rules/r9"
DAYOFF = {"command": "DAYOFF", "extensionId": "101", "sender": "+15555550100"}


@pytest.mark.parametrize(
    "message, expected",
    [
        ("DAYOFF", {"command": "DAYOFF", "target_extension": None}),
        ("  back  ", {"command": "BACK", "target_extension": None}),
        ("dayoff 1234", {"command": "DAYOFF", "target_extension": "1234"}),
        ("", None),
        ("   ", None),
    ],
)
def test_parse_command(message, expected):
    assert parse_command(message) == expected


def _patches(rc):
    return [(path, body["enabled"]) for method, path, body in rc.calls if method == "PATCH"]


# ---- /demo/dayoff --------------------------------------------------------


def test_dayoff_enables_own_rule_and_texts_back(client, rc):
    response = client.post("/demo/dayoff", json_body=DAYOFF)

    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Call rule enabled for Nurse 101."}
    assert _patches(rc) == [(RULE_PATH.format("101"), True)]
    assert rc.sms_sent() == [
        {
            "from": {"phoneNumber": "+18659740716"},
            "to": [{"phoneNumber": "+15555550100"}],
            "text": "Call rule enabled for Nurse 101.",
        }
    ]


def test_manager_back_with_extension_number_targets_that_nurse(client, rc):
    response = client.post("/demo/dayoff", json_body={**DAYOFF, "command": "back 1234"})

    assert response.json()["message"] == "Call rule disabled for Target Nurse."
    assert _patches(rc) == [(RULE_PATH.format("555"), False)]


def test_invalid_command_changes_nothing_but_still_replies(client, rc):
    response = client.post("/demo/dayoff", json_body={**DAYOFF, "command": "hello"})

    assert response.json()["message"] == "Invalid command. Use DAYOFF or BACK."
    assert _patches(rc) == []
    assert len(rc.sms_sent()) == 1


def test_missing_rule_is_reported(client, rc):
    rc.no_rule_for.add("101")

    response = client.post("/demo/dayoff", json_body=DAYOFF)

    assert response.json()["message"] == "Call rule not found for Nurse 101."
    assert _patches(rc) == []


def test_ringcentral_non_breaking_spaces_and_padding_are_handled(client, rc):
    body = (
        '{"command":' + NBSP + '" DAYOFF ",' + NBSP
        + '"extensionId": " 101 ", "sender": " +15555550100 "}'
    )

    response = client.post("/demo/dayoff", content=body)

    assert response.status_code == 200
    assert _patches(rc) == [(RULE_PATH.format("101"), True)]
    assert rc.sms_sent()[0]["to"] == [{"phoneNumber": "+15555550100"}]


def test_sms_failure_does_not_fail_the_request(client, rc, monkeypatch):
    def broken_post(path, body):
        raise RuntimeError("SMS down")

    monkeypatch.setattr(rc, "post", broken_post)

    response = client.post("/demo/dayoff", json_body=DAYOFF)

    assert response.status_code == 200
    assert _patches(rc) == [(RULE_PATH.format("101"), True)]


# ---- /ringcentral/dnd ----------------------------------------------------


@pytest.mark.parametrize(
    "command, action, dnd_status",
    [
        ("DAYOFF", "dnd_enabled", "DoNotAcceptAnyCalls"),
        (" back ", "dnd_disabled", "TakeAllCalls"),
    ],
)
def test_dnd(client, rc, command, action, dnd_status):
    response = client.post(
        "/ringcentral/dnd", json_body={"command": command, "extensionId": "202"}
    )

    assert response.json() == {"status": "success", "action": action}
    assert rc.calls == [
        (
            "PUT",
            "/restapi/v1.0/account/~/extension/202/presence",
            {"dndStatus": dnd_status},
        )
    ]


def test_dnd_unknown_command_is_ignored(client, rc):
    response = client.post(
        "/ringcentral/dnd", json_body={"command": "nope", "extensionId": "202"}
    )

    assert response.json() == {"status": "ignored", "command": "NOPE"}
    assert rc.calls == []


def test_ringcentral_dayoff_is_not_implemented(client, rc):
    response = client.post("/ringcentral/dayoff", json_body={"command": "DAYOFF"})

    assert response.status_code == 501
    assert rc.calls == []
