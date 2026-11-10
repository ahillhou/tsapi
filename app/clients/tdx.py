"""
TeamDynamix (TDX) API client.

Talks to the TDX **sandbox** (settings.tdx_base_url), except
download_prod_attachment(), which reads attachments from production TDX
forms. Both use the same TDX account; each instance gets its own token.
"""

import logging
import threading
import time

import requests

from app.core.config import HTTP_TIMEOUT, get_settings

logger = logging.getLogger(__name__)

# TDX tokens are valid for 24 hours and /api/auth is rate limited, so log in
# once per instance and reuse the token. Refresh well before expiry, and
# immediately if TDX answers 401.
TOKEN_MAX_AGE_SECONDS = 12 * 60 * 60

# base URL -> (token, time.monotonic() when issued)
_tokens: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def _sandbox() -> str:
    return get_settings().tdx_base_url


def _login(base_url: str) -> str:
    s = get_settings()

    response = requests.post(
        f"{base_url}/api/auth",
        json={
            "UserName": s.tdx_username,
            "Password": s.tdx_password,
        },
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()

    logger.info("Logged in to TDX (%s)", base_url.rsplit("/", 1)[-1])
    return response.text


def authenticate(force_refresh: bool = False, base_url: str | None = None) -> dict:
    """Return TDX request headers with a valid bearer token."""

    base_url = base_url or _sandbox()

    with _token_lock:
        token, issued_at = _tokens.get(base_url, (None, 0.0))
        expired = time.monotonic() - issued_at > TOKEN_MAX_AGE_SECONDS

        if force_refresh or token is None or expired:
            token = _login(base_url)
            _tokens[base_url] = (token, time.monotonic())

        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }


def clear_token() -> None:
    """Forget all cached tokens (used by tests)."""

    with _token_lock:
        _tokens.clear()


def _request(method: str, url: str, base_url: str | None = None, **kwargs) -> requests.Response:
    """Authenticated request; logs in again once if the token was rejected."""

    send = getattr(requests, method)

    response = send(url, headers=authenticate(base_url=base_url), timeout=HTTP_TIMEOUT, **kwargs)

    if response.status_code == 401:
        logger.info("TDX token rejected; logging in again")
        response = send(
            url,
            headers=authenticate(force_refresh=True, base_url=base_url),
            timeout=HTTP_TIMEOUT,
            **kwargs,
        )

    response.raise_for_status()
    return response


def get_ticket(ticket_id: int) -> dict:
    """Retrieve a specific ticket by ID."""

    return _request("get", f"{_sandbox()}/api/tickets/{ticket_id}").json()


def search_tickets(search_body: dict | None = None) -> list:
    """
    Search for tickets in the configured TDX app.

    Search results leave out Attributes, Description and Attachments; call
    get_ticket() for each result before building remarks.
    """

    s = get_settings()

    return _request(
        "post",
        f"{_sandbox()}/api/{s.tdx_app_id}/tickets/search",
        json=search_body or {},
    ).json()


def download_attachment(content_uri: str) -> bytes:
    """Download an attachment's bytes from its ContentUri (sandbox TDX)."""

    return _request("get", f"{_sandbox()}/{content_uri}").content


def download_prod_attachment(content_uri: str) -> bytes:
    """Download an attachment's bytes from its ContentUri (**production** TDX)."""

    base_url = get_settings().tdx_prod_base_url

    return _request("get", f"{base_url}/{content_uri}", base_url=base_url).content


def get_attribute(ticket: dict, name: str) -> str | None:
    """Return the ValueText of a ticket's custom attribute, or None."""

    for attr in ticket.get("Attributes") or []:
        if attr["Name"] == name:
            return attr["ValueText"]

    return None
