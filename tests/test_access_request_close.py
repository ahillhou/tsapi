"""Resolve production TDX tickets of finished PCR access requests (/jobs/access-requests/close)."""

import pytest

from app.core.config import get_settings
from app.services import access_request_close
from app.services.access_request_close import close_completed, closed_before, ticket_id
from tests.conftest import TDX_BASE, TDX_PROD_BASE, FakeResponse

PROD_SQL_URL = "https://pcr360.utk.pcr-360.com/api/KEY-PROD/sql.json"
ROUTE = "/jobs/access-requests/close"
SECRET = {"X-Webhook-Secret": "r3port"}


def _inquiry(sd_number, tid):
    message = f"Access Change: Add<br><br>Requestor Name: Pat Doe<br><br>TDX Ticket ID#: {tid}<br><br>"
    return {"SD_NUMBER": sd_number, "VOID_DATE": "2026-11-23 09:15:01", "MESSAGE": message}


def _ticket(tid, status_class=1, app_id=2278, name="New"):
    return {"ID": tid, "AppID": app_id, "StatusClass": status_class, "StatusName": name}


@pytest.fixture(autouse=True)
def waits(monkeypatch):
    """No real sleeping; records every wait. Forgets tickets seen closed."""

    slept = []
    monkeypatch.setattr(access_request_close, "sleep", slept.append)
    access_request_close._known_closed.clear()
    access_request_close._left_open.clear()
    yield slept
    access_request_close._known_closed.clear()
    access_request_close._left_open.clear()


@pytest.fixture
def pcr(http):
    """Two finished access requests whose tickets are still open."""

    http.sql_results = [_inquiry("IQ00000149", 24800607), _inquiry("IQ00000150", 24803438)]
    http.prod_tickets = {24800607: _ticket(24800607), 24803438: _ticket(24803438, status_class=2, name="Open")}
    return http


def _feed_posts(http):
    return [c for c in http.calls if c["method"] == "POST" and c["url"].endswith("/feed")]


def _ticket_reads(http):
    return [c["url"] for c in http.calls if c["method"] == "GET" and "/api/tickets/" in c["url"]]


# ---- what is sent ----------------------------------------------------------


def test_live_run_resolves_each_open_ticket_with_exact_payload(pcr):
    result = close_completed(dry_run=False)

    assert [c["url"] for c in _feed_posts(pcr)] == [
        f"{TDX_PROD_BASE}/api/2278/tickets/24800607/feed",
        f"{TDX_PROD_BASE}/api/2278/tickets/24803438/feed",
    ]
    assert _feed_posts(pcr)[0]["json"] == {
        "NewStatusID": 98857,
        "Comments": "Completed in PCR360 (IQ00000149). Closed automatically by TS API.",
        "IsPrivate": True,
        "IsRichHtml": False,
        "Notify": [],
    }
    assert result["counts"] == {"resolved": 2}
    assert result["results"][0] == {
        "inquiry": "IQ00000149",
        "voided": "2026-11-23 09:15:01",
        "ticket": 24800607,
        "ticket_status": "New",
        "action": "resolved",
    }


def test_pcr_is_only_read_on_production_with_the_complete_and_void_query(pcr):
    close_completed(dry_run=False, days=14)

    pcr_calls = pcr.pcr_calls()
    assert [c["url"] for c in pcr_calls] == [PROD_SQL_URL]

    sql = pcr_calls[0]["json"]["sql"]
    assert "L.CODE = 'VOID'" in sql
    assert "U.IDENTIFIER = 'COMPLETE_REQUEST'" in sql
    assert "V.BOOL_VALUE = 1" in sql
    assert "I.SUBJECT LIKE '%PCR Access'" in sql
    assert "SD.VOID_DATE >= '" in sql


def test_only_production_tdx_is_used(pcr):
    close_completed(dry_run=False)

    tdx_urls = [c["url"] for c in pcr.calls if c["url"].startswith("https://utk.teamdynamix.com/")]
    assert tdx_urls and not [u for u in tdx_urls if u.startswith(TDX_BASE)]


# ---- dry run ---------------------------------------------------------------


def test_dry_run_reads_tickets_but_changes_nothing(pcr):
    result = close_completed(dry_run=True)

    assert _feed_posts(pcr) == []
    assert len(_ticket_reads(pcr)) == 2
    assert result["dry_run"] is True
    assert result["counts"] == {"would resolve": 2}


def test_dry_run_is_the_default(pcr):
    close_completed()

    assert _feed_posts(pcr) == []


# ---- what is left alone ----------------------------------------------------


@pytest.mark.parametrize("status_class, name", [(3, "Resolved"), (4, "Cancelled")])
def test_closed_tickets_are_never_touched(pcr, status_class, name):
    pcr.prod_tickets[24800607] = _ticket(24800607, status_class=status_class, name=name)

    result = close_completed(dry_run=False)

    assert [c["url"] for c in _feed_posts(pcr)] == [f"{TDX_PROD_BASE}/api/2278/tickets/24803438/feed"]
    assert result["results"][0]["action"] == "already closed"
    assert result["results"][0]["ticket_status"] == name


def test_ticket_in_another_app_is_skipped(pcr):
    pcr.prod_tickets[24800607] = _ticket(24800607, app_id=9999)

    result = close_completed(dry_run=False)

    assert result["results"][0]["action"] == "wrong app"
    assert len(_feed_posts(pcr)) == 1


def test_inquiry_without_ticket_number_is_skipped(pcr):
    pcr.sql_results = [{"SD_NUMBER": "IQ00000002", "VOID_DATE": None, "MESSAGE": "typed by hand"}]

    result = close_completed(dry_run=False)

    assert result["results"] == [
        {"inquiry": "IQ00000002", "voided": None, "ticket": None, "action": "no ticket number"}
    ]
    assert _ticket_reads(pcr) == []


def test_one_failed_ticket_does_not_stop_the_rest(pcr):
    del pcr.prod_tickets[24800607]  # 404

    result = close_completed(dry_run=False)

    assert result["results"][0]["action"] == "error"
    assert result["results"][0]["error"] == "read failed: HTTPError 404"
    assert result["results"][1]["action"] == "resolved"


def test_only_limits_to_one_inquiry(pcr):
    result = close_completed(dry_run=False, only="iq00000150")

    assert [r["inquiry"] for r in result["results"]] == ["IQ00000150"]
    assert len(_feed_posts(pcr)) == 1


@pytest.mark.parametrize(
    "message, expected",
    [
        ("Requestor Email: a@b.edu<br><br>TDX Ticket ID#: 24800607<br><br>", 24800607),
        ("TDX Ticket ID#:24800607", 24800607),
        ("no number here", None),
        (None, None),
    ],
)
def test_ticket_id(message, expected):
    assert ticket_id(message) == expected


# ---- reopened tickets (e.g. a requester's comment) -------------------------


def _change(old, new, who="Kat Grimsley"):
    return {"CreatedFullName": who, "Body": f'Changed Status from "<b>{old}</b>" to "<b>{new}</b>".<br><br>note'}


def _comment(text="Still can't log in"):
    return {"CreatedFullName": "Pat Doe", "Body": text}


@pytest.mark.parametrize("closed_as", ["Resolved", "Cancelled", "Referred"])
def test_ticket_closed_before_and_reopened_is_left_open(pcr, closed_as):
    # newest first, as TDX returns it
    pcr.prod_feeds[24803438] = [_comment(), _change("Open", closed_as), _change("New", "Open")]

    result = close_completed(dry_run=False)

    assert result["results"][1]["action"] == "reopened, left open"
    assert [c["url"] for c in _feed_posts(pcr)] == [f"{TDX_PROD_BASE}/api/2278/tickets/24800607/feed"]


def test_ticket_we_closed_and_was_reopened_is_left_open(pcr):
    pcr.prod_feeds[24803438] = [
        _change("Resolved", "Open", who="Pat Doe"),
        _change("Open", "Resolved", who="Telephone Services TDX API"),
    ]

    result = close_completed(dry_run=False)

    assert result["results"][1]["action"] == "reopened, left open"
    assert len(_feed_posts(pcr)) == 1


def test_routed_to_open_but_never_closed_is_resolved(pcr):
    # Help Desk routing sets Open (ticket 24784303 on 2026-11-16).
    pcr.prod_feeds[24803438] = [_change("New", "Open", who="Help Desk"), _comment()]

    result = close_completed(dry_run=False)

    assert result["results"][1]["action"] == "resolved"


def test_dry_run_reports_reopened_too(pcr):
    pcr.prod_feeds[24803438] = [_change("Open", "Resolved")]

    result = close_completed(dry_run=True)

    assert result["counts"] == {"would resolve": 1, "reopened, left open": 1}


def test_reopened_ticket_is_not_checked_again(pcr):
    pcr.prod_feeds[24803438] = [_change("Open", "Resolved")]

    close_completed(dry_run=False)
    reads = len(_ticket_reads(pcr))
    second = close_completed(dry_run=False)

    assert second["results"][1]["action"] == "reopened, left open"
    # only the first ticket's (closed by us, so remembered) and nothing for the reopened one
    assert len(_ticket_reads(pcr)) == reads


def test_history_read_failure_never_resolves(pcr, monkeypatch):
    real_get = pcr.get

    def get(url, **kwargs):
        if url.endswith("/24803438/feed"):
            pcr.calls.append({"method": "GET", "url": url})
            return FakeResponse(500, {})
        return real_get(url, **kwargs)

    monkeypatch.setattr("requests.get", get)

    result = close_completed(dry_run=False)

    assert result["results"][1]["action"] == "error"
    assert result["results"][1]["error"] == "history read failed: HTTPError 500"
    assert [c["url"] for c in _feed_posts(pcr)] == [f"{TDX_PROD_BASE}/api/2278/tickets/24800607/feed"]


def test_statuses_are_read_once_per_run(pcr):
    close_completed(dry_run=True)

    assert len([c for c in pcr.calls if c["url"].endswith("/tickets/statuses")]) == 1


@pytest.mark.parametrize(
    "feed, expected",
    [
        ([], False),
        ([_comment()], False),
        ([_change("New", "Open")], False),
        ([_change("Open", "Resolved")], True),
        ([_change("Open", "resolved")], True),
        ([{"Body": None}], False),
        (None, False),
    ],
)
def test_closed_before(feed, expected):
    assert closed_before(feed, {"resolved", "cancelled"}) is expected


# ---- TDX rate limit (60 calls a minute) -----------------------------------


def test_every_tdx_call_is_paced(pcr, waits):
    close_completed(dry_run=False)

    # statuses once + 2 tickets x (read + history + resolve)
    assert waits == [1.1] * 7


def test_rate_limited_call_waits_and_retries(pcr, waits, monkeypatch):
    real_get = pcr.get
    answers = iter([429])

    def get(url, **kwargs):
        if "/api/tickets/24800607" in url:
            status = next(answers, None)
            if status:
                pcr.calls.append({"method": "GET", "url": url})
                return FakeResponse(status, {})
        return real_get(url, **kwargs)

    monkeypatch.setattr("requests.get", get)

    result = close_completed(dry_run=False)

    assert result["counts"] == {"resolved": 2}
    assert 61 in waits


def test_closed_tickets_are_not_read_again(pcr):
    pcr.prod_tickets[24800607] = _ticket(24800607, status_class=3, name="Resolved")

    close_completed(dry_run=False)
    reads_before = len(_ticket_reads(pcr))
    second = close_completed(dry_run=False)

    # 24800607 was closed, 24803438 we closed: neither is read again.
    assert len(_ticket_reads(pcr)) == reads_before
    assert second["counts"] == {"already closed": 2}
    assert len(_feed_posts(pcr)) == 1


def test_dry_run_does_not_remember_would_resolve(pcr):
    close_completed(dry_run=True)
    close_completed(dry_run=True)

    assert len(_ticket_reads(pcr)) == 4


# ---- route -----------------------------------------------------------------


def test_route_is_closed_until_reports_secret_is_set(client, pcr):
    assert client.post(ROUTE).status_code == 503
    assert pcr.calls == []


def test_route_needs_the_secret(make_client, pcr):
    app = make_client(REPORTS_SECRET="r3port")

    assert app.post(ROUTE, headers={"X-Webhook-Secret": "wrong"}).status_code == 401
    assert pcr.calls == []


def test_route_defaults_to_dry_run(make_client, pcr):
    response = make_client(REPORTS_SECRET="r3port").post(ROUTE, headers=SECRET)

    assert response.status_code == 200
    assert response.json()["counts"] == {"would resolve": 2}
    assert _feed_posts(pcr) == []


def test_route_live_run(make_client, pcr):
    response = make_client(REPORTS_SECRET="r3port").post(
        ROUTE, headers=SECRET, query="dry_run=false&only=IQ00000149"
    )

    assert response.json()["counts"] == {"resolved": 1}
    assert len(_feed_posts(pcr)) == 1


def test_route_pcr_failure_is_502(make_client, pcr):
    pcr.sql_status = 500

    response = make_client(REPORTS_SECRET="r3port").post(ROUTE, headers=SECRET)

    assert response.status_code == 502
    assert "KEY-PROD" not in response.body.decode()
    assert _feed_posts(pcr) == []


# ---- timer setting ---------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [("", "off"), ("off", "off"), ("dry_run", "dry_run"), (" ON ", "on"), ("yes", "off")],
)
def test_autoclose_setting(monkeypatch, value, expected):
    monkeypatch.setenv("ACCESS_REQUEST_AUTOCLOSE", value)
    get_settings.cache_clear()

    assert get_settings().access_request_autoclose == expected

    get_settings.cache_clear()


def test_timer_interval_is_15_minutes():
    assert access_request_close.INTERVAL_SECONDS == 900
