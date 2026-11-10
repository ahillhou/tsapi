from conftest import TDX_BASE

from app.clients import tdx


def _logins(http):
    return [c for c in http.calls if c["url"] == f"{TDX_BASE}/api/auth"]


def test_token_is_reused_across_calls(http):
    tdx.get_ticket(1)
    tdx.get_ticket(2)
    tdx.download_attachment("api/attachments/1/content")

    assert len(_logins(http)) == 1


def test_token_is_refreshed_after_max_age(http, monkeypatch):
    tdx.get_ticket(1)

    monkeypatch.setattr(tdx, "_token_issued_at", tdx._token_issued_at - tdx.TOKEN_MAX_AGE_SECONDS - 1)
    tdx.get_ticket(2)

    assert len(_logins(http)) == 2


def test_rejected_token_logs_in_again_and_retries_once(http):
    tdx.get_ticket(1)
    http.tdx_reject_next = 1

    ticket = tdx.get_ticket(2)

    assert ticket["ID"] == 777
    assert len(_logins(http)) == 2
    last = http.calls[-1]
    assert last["headers"]["Authorization"] == "Bearer TDX-TOKEN-2"


def test_search_uses_app_id_and_cached_token(http):
    results = tdx.search_tickets({"MaxResults": 5})

    assert results == [{"ID": 777}]
    search = http.calls[-1]
    assert search["url"] == f"{TDX_BASE}/api/2278/tickets/search"
    assert search["json"] == {"MaxResults": 5}


def test_get_attribute_handles_missing_attributes():
    assert tdx.get_attribute({"Attributes": None}, "PCR Type") is None
    assert tdx.get_attribute({}, "PCR Type") is None
