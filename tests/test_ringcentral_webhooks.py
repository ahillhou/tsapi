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
        ("!!!", None),
    ],
)
def test_parse_command(message, expected):
    assert parse_command(message) == expected


@pytest.mark.parametrize(
    "message",
    [
        "Day off",
        "day-off",
        "Dayoff.",
        "DAY OFF!",
        "days off",
        "I'm off today",
        "Taking the day off",
        "out",
        "I'm out sick",
        "OOO",
        "Off today, back tomorrow",
    ],
)
def test_ways_to_say_dayoff(message):
    assert parse_command(message) == {"command": "DAYOFF", "target_extension": None}


@pytest.mark.parametrize(
    "message",
    ["Back", "back.", "I'm back!", "Im back", "BACK IN", "Returning today", "Back from my day off"],
)
def test_ways_to_say_back(message):
    assert parse_command(message) == {"command": "BACK", "target_extension": None}


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Day off 1234", ("DAYOFF", "1234")),
        ("day off for ext 1234", ("DAYOFF", "1234")),
        ("Day off ext. 1234", ("DAYOFF", "1234")),
        ("dayoff x1234", ("DAYOFF", "1234")),
        ("1234 day off", ("DAYOFF", "1234")),
        ("Back #1234", ("BACK", "1234")),
        ("back ext1234", ("BACK", "1234")),
    ],
)
def test_ways_to_give_an_extension(message, expected):
    command, extension = expected
    assert parse_command(message) == {"command": command, "target_extension": extension}


@pytest.mark.parametrize("message", ["hello", "office", "in the office", "on", "backup"])
def test_other_texts_are_not_commands(message):
    assert parse_command(message)["command"] not in ("DAYOFF", "BACK")


def test_day_off_with_spaces_texts_back(client, rc):
    response = client.post("/demo/dayoff", json_body={**DAYOFF, "command": "Day off"})

    assert response.json()["message"].startswith("Call rule enabled for ")


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
            "from": {"phoneNumber": "+18659741100"},
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


# ---- plain DAYOFF/BACK acts on the sender's own extension ----------------

LOOKUP = "/restapi/v2/accounts/~/phone-numbers?phoneNumber=%2B15555550100"


def test_plain_dayoff_targets_the_sender_not_the_workflow_extension(client, rc):
    # The workflow now runs on ext 41100, so extensionId is always that one.
    body = {"command": "DAYOFF", "extensionId": "1619021040", "sender": "+15555550100"}

    response = client.post("/demo/dayoff", json_body=body)

    assert response.json()["message"] == "Call rule enabled for Nurse 101."
    gets = [path for method, path, *_ in rc.calls if method == "GET"]
    assert gets[0] == LOOKUP
    assert "/restapi/v1.0/account/~/extension/101" in gets
    assert not [p for p in gets if "1619021040" in p]
    assert _patches(rc) == [(RULE_PATH.format("101"), True)]


@pytest.mark.parametrize("sender", ["(555) 555-0100", "5555550100", "1-555-555-0100"])
def test_sender_number_formats_are_normalised(client, rc, sender):
    client.post("/demo/dayoff", json_body={**DAYOFF, "command": "BACK", "sender": sender})

    assert [path for method, path, *_ in rc.calls if method == "GET"][0] == LOOKUP
    assert _patches(rc) == [(RULE_PATH.format("101"), False)]


def test_phone_not_on_an_extension_gets_told_to_add_the_extension(client, rc):
    response = client.post("/demo/dayoff", json_body={**DAYOFF, "sender": "+15555559999"})

    assert response.json()["message"] == (
        "DAYOFF needs your extension: this phone isn't on a RingCentral extension. "
        "Text DAYOFF followed by your extension number."
    )
    assert _patches(rc) == []
    assert rc.sms_sent()[0]["to"] == [{"phoneNumber": "+15555559999"}]


def test_naming_an_extension_skips_the_sender_lookup(client, rc):
    client.post("/demo/dayoff", json_body={**DAYOFF, "command": "dayoff 1234"})

    assert not [p for m, p, *_ in rc.calls if m == "GET" and "phone-numbers" in p]
    assert _patches(rc) == [(RULE_PATH.format("555"), True)]


@pytest.mark.parametrize(
    "number, expected",
    [
        ("+18659741100", "+18659741100"),
        ("8659741100", "+18659741100"),
        ("1 (865) 974-1100", "+18659741100"),
        ("41100", None),
        ("", None),
    ],
)
def test_to_e164(number, expected):
    from app.clients.ringcentral.extensions import to_e164

    assert to_e164(number) == expected
