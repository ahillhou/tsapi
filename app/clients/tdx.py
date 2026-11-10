"""TeamDynamix (TDX) API client."""

import logging
import threading
import time

import requests

from app.core.config import HTTP_TIMEOUT, get_settings

logger = logging.getLogger(__name__)

# TDX tokens are valid for 24 hours and /api/auth is rate limited, so log in
# once and reuse the token. Refresh well before expiry, and immediately if
# TDX answers 401.
TOKEN_MAX_AGE_SECONDS = 12 * 60 * 60

_token: str | None = None
_token_issued_at = 0.0
_token_lock = threading.Lock()


def _login() -> str:
    s = get_settings()

    response = requests.post(
        f"{s.tdx_base_url}/api/auth",
        json={
            "UserName": s.tdx_username,
            "Password": s.tdx_password,
        },
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()

    logger.info("Logged in to TDX")
    return response.text


def authenticate(force_refresh: bool = False) -> dict:
    """Return TDX request headers with a valid bearer token."""

    global _token, _token_issued_at

    with _token_lock:
        expired = time.monotonic() - _token_issued_at > TOKEN_MAX_AGE_SECONDS

        if force_refresh or _token is None or expired:
            _token = _login()
            _token_issued_at = time.monotonic()

        return {
            "Authorization": f"Bearer {_token}",
            "Content-Type": "application/json",
        }


def clear_token() -> None:
    """Forget the cached token (used by tests)."""

    global _token, _token_issued_at

    with _token_lock:
        _token = None
        _token_issued_at = 0.0


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Authenticated request; logs in again once if the token was rejected."""

    send = getattr(requests, method)

    response = send(url, headers=authenticate(), timeout=HTTP_TIMEOUT, **kwargs)

    if response.status_code == 401:
        logger.info("TDX token rejected; logging in again")
        response = send(
            url,
            headers=authenticate(force_refresh=True),
            timeout=HTTP_TIMEOUT,
            **kwargs,
        )

    response.raise_for_status()
    return response


def get_ticket(ticket_id: int) -> dict:
    """Retrieve a specific ticket by ID."""

    s = get_settings()

    return _request("get", f"{s.tdx_base_url}/api/tickets/{ticket_id}").json()


def search_tickets(search_body: dict | None = None) -> list:
    """
    Search for tickets in the configured TDX app.

    Search results leave out Attributes, Description and Attachments; call
    get_ticket() for each result before building remarks.
    """

    s = get_settings()

    return _request(
        "post",
        f"{s.tdx_base_url}/api/{s.tdx_app_id}/tickets/search",
        json=search_body or {},
    ).json()


def download_attachment(content_uri: str) -> bytes:
    """Download an attachment's bytes from its ContentUri."""

    s = get_settings()

    return _request("get", f"{s.tdx_base_url}/{content_uri}").content


def get_attribute(ticket: dict, name: str) -> str | None:
    """Return the ValueText of a ticket's custom attribute, or None."""

    for attr in ticket.get("Attributes") or []:
        if attr["Name"] == name:
            return attr["ValueText"]

    return None
