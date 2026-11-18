"""/ringcentral/parking_event (production queue 46031) and /ringcentral/test_parking_event (test queue 98765)."""

import copy

import pytest

from app.clients.ringcentral import auth as rc_auth
from app.clients.ringcentral.errors import RingCentralError
from app.services.parking_events import (
    PARKING_QUEUE_ID,
    TEST_PARKING_QUEUE_ID,
    event_name,
    parse_command,
)

PROD = "/ringcentral/parking_event"
TEST = "/ringcentral/test_parking_event"
STAFF = "+18655550100"
SENDERS = "(865) 555-0100, 865-555-0199"


def _rules_path(queue_id):
    return f"/restapi/v1.0/account/~/extension/{queue_id}/answering-rule"


class Resp:
    def __init__(self, data):
        self._data = data

    def json_dict(self):
        return copy.deepcopy(self._data)


class QueuePlatform:
    """Custom rules on a queue; records every call, applies PUTs."""

    def __init__(self):
        self.calls = []
        self.fail_put = False
        self.pages = 1
        self.rules = [
            {"id": "11", "type": "Custom", "name": "Event - Football", "enabled": False},
            {"id": "12", "type": "Custom", "name": "Event – Home Concert", "enabled": True},
            {"id": "13", "type": "Custom", "name": "Lunch break", "enabled": True},
        ]

    def logged_in(self):
        return True

    def get(self, path, params=None):
        self.calls.append(("GET", path, params))
        page = params["page"]
        per_page = -(-len(self.rules) // self.pages)
        records = self.rules[(page - 1) * per_page : page * per_page]
        return Resp({"records": records, "paging": {"page": page, "totalPages": self.pages}})

    def put(self, path, body):
        self.calls.append(("PUT", path, body))
        if self.fail_put:
            raise RingCentralError("RingCentral HTTP 403 CMN-408: no permission", 403, "CMN-408")
        rule_id = path.rsplit("/", 1)[1]
        for rule in self.rules:
            if rule["id"] == rule_id:
                rule.update(body)
        return Resp({})

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        return Resp({"id": "sms-1"})

    def puts(self):
        return [(path, body) for method, path, body in self.calls if method == "PUT"]

    def sms(self):
        return [body for method, path, body in self.calls if method == "POST"]

    def enabled(self):
        return {r["name"]: r["enabled"] for r in self.rules}


@pytest.fixture
def queue(monkeypatch):
    fake = QueuePlatform()
    monkeypatch.setattr(rc_auth, "_platform", fake)
    return fake


@pytest.fixture
def staff_client(make_client):
    return make_client(PARKING_EVENT_SENDERS=SENDERS)


def _text(client, command, path=PROD, sender=STAFF):
    return client.post(path, json_body={"command": command, "sender": sender})


# ---- parsing ---------------------------------------------------------------


@pytest.mark.parametrize(
    "message, expected",
    [
        ("FOOTBALL ON", ("ON", "FOOTBALL")),
        ("  football   on ", ("ON", "FOOTBALL")),
        ("home concert off", ("OFF", "HOME CONCERT")),
        ("event football on", ("ON", "FOOTBALL")),
        ("Event off", ("ALL_OFF", None)),
        ("all off", ("ALL_OFF", None)),
        ("OFF", ("ALL_OFF", None)),
        ("status", ("STATUS", None)),
        ("ON", ("HELP", None)),
        ("hello", ("HELP", None)),
        ("", ("HELP", None)),
    ],
)
def test_parse_command(message, expected):
    assert parse_command(message) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Event - Football", "Football"),
        ("event: Home Concert ", "Home Concert"),
        ("Event – Permit Sales", "Permit Sales"),
        ("Event message", None),
        ("Lunch break", None),
        (None, None),
    ],
)
def test_event_name(name, expected):
    assert event_name(name) == expected


# ---- switching -------------------------------------------------------------


def test_on_turns_others_off_first_then_target_on_and_replies(staff_client, queue):
    response = _text(staff_client, "football on")

    assert response.status_code == 200
    reply = "Football message is on. Callers hear it during business hours until you text FOOTBALL OFF."
    assert response.json() == {"status": "success", "message": reply}

    assert queue.calls == [
        ("GET", _rules_path(PARKING_QUEUE_ID), {"type": "Custom", "page": 1, "perPage": 100}),
        ("PUT", f"{_rules_path(PARKING_QUEUE_ID)}/12", {"enabled": False}),
        ("PUT", f"{_rules_path(PARKING_QUEUE_ID)}/11", {"enabled": True}),
        (
            "POST",
            "/restapi/v1.0/account/~/extension/~/sms",
            {"from": {"phoneNumber": "+18659740716"}, "to": [{"phoneNumber": STAFF}], "text": reply},
        ),
    ]


def test_non_event_rules_are_never_touched(staff_client, queue):
    _text(staff_client, "football on")
    _text(staff_client, "event off")

    assert queue.enabled()["Lunch break"] is True
    assert not [p for p, _ in queue.puts() if p.endswith("/13")]


def test_on_when_already_on_changes_nothing(staff_client, queue):
    response = _text(staff_client, "HOME CONCERT ON")

    assert response.json()["message"].startswith("Home Concert message is on.")
    assert queue.puts() == []


def test_off_turns_only_that_event_off(staff_client, queue):
    response = _text(staff_client, "home concert off")

    assert response.json()["message"] == "Home Concert message is off."
    assert queue.puts() == [(f"{_rules_path(PARKING_QUEUE_ID)}/12", {"enabled": False})]


def test_event_off_turns_every_event_off(staff_client, queue):
    queue.rules[0]["enabled"] = True

    response = _text(staff_client, "EVENT OFF")

    assert response.json()["message"] == "All event messages are off."
    assert queue.puts() == [
        (f"{_rules_path(PARKING_QUEUE_ID)}/11", {"enabled": False}),
        (f"{_rules_path(PARKING_QUEUE_ID)}/12", {"enabled": False}),
    ]


def test_status_reports_and_changes_nothing(staff_client, queue):
    response = _text(staff_client, "status")

    assert response.json()["message"] == "Event message on: Home Concert."
    assert queue.puts() == []

    queue.rules[1]["enabled"] = False
    assert _text(staff_client, "status").json()["message"] == "No event message is on."


def test_unknown_event_lists_events_and_changes_nothing(staff_client, queue):
    response = _text(staff_client, "basketball on")

    assert response.json()["message"] == (
        "No event called BASKETBALL. Text <EVENT> ON or <EVENT> OFF, EVENT OFF, "
        "or STATUS. Events: Football, Home Concert."
    )
    assert queue.puts() == []
    assert len(queue.sms()) == 1


def test_anything_else_gets_help(staff_client, queue):
    response = _text(staff_client, "hi")

    assert response.json()["message"] == (
        "Text <EVENT> ON or <EVENT> OFF, EVENT OFF, or STATUS. Events: Football, Home Concert."
    )
    assert queue.puts() == []


def test_rules_on_later_pages_are_found(staff_client, queue):
    queue.pages = 3

    _text(staff_client, "football on")

    gets = [params["page"] for method, path, params in queue.calls if method == "GET"]
    assert gets == [1, 2, 3]
    assert queue.enabled()["Event - Football"] is True


# ---- who may text ----------------------------------------------------------


@pytest.mark.parametrize("sender", ["+18655550100", "8655550199", "+1 (865) 555-0199"])
def test_approved_numbers_match_in_any_format(staff_client, queue, sender):
    assert _text(staff_client, "status", sender=sender).json()["status"] == "success"


def test_unapproved_number_is_ignored_without_reply(staff_client, queue):
    response = _text(staff_client, "football on", sender="+18655559999")

    assert response.json() == {"status": "ignored"}
    assert queue.calls == []


def test_nobody_is_approved_until_senders_are_set(client, queue):
    assert _text(client, "football on").json() == {"status": "ignored"}
    assert queue.calls == []


def test_secret_required_when_set(make_client, queue):
    client = make_client(PARKING_EVENT_SENDERS=SENDERS, RINGCENTRAL_WEBHOOK_SECRET="s3cret")

    assert _text(client, "football on").status_code == 401
    assert queue.calls == []


# ---- test vs production ----------------------------------------------------


def test_test_route_only_touches_the_test_queue(staff_client, queue):
    _text(staff_client, "football on", path=TEST)

    paths = [path for method, path, *_ in queue.calls if method in ("GET", "PUT")]
    assert paths and all(p.startswith(_rules_path(TEST_PARKING_QUEUE_ID)) for p in paths)


def test_production_route_only_touches_the_parking_queue(staff_client, queue):
    _text(staff_client, "football on", path=PROD)

    paths = [path for method, path, *_ in queue.calls if method in ("GET", "PUT")]
    assert paths and all(p.startswith(_rules_path(PARKING_QUEUE_ID)) for p in paths)


# ---- failures --------------------------------------------------------------


def test_ringcentral_failure_is_502_and_staff_are_told(staff_client, queue):
    queue.fail_put = True

    response = _text(staff_client, "football on")

    assert response.status_code == 502
    [sms] = queue.sms()
    assert sms["text"].startswith("Sorry, that didn't work")
    assert "rc-jwt" not in response.body.decode()
