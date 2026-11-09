"""TeamDynamix (TDX) API client."""

import requests

from app.core.config import get_settings


def authenticate() -> dict:
    """Authenticate with TDX and return request headers."""

    s = get_settings()

    auth_response = requests.post(
        f"{s.tdx_base_url}/api/auth",
        json={
            "UserName": s.tdx_username,
            "Password": s.tdx_password,
        },
    )
    auth_response.raise_for_status()

    token = auth_response.text

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def get_ticket(ticket_id: int) -> dict:
    """Retrieve a specific ticket by ID."""

    s = get_settings()

    response = requests.get(
        f"{s.tdx_base_url}/api/tickets/{ticket_id}",
        headers=authenticate(),
    )
    response.raise_for_status()

    return response.json()


def search_tickets(search_body: dict | None = None) -> list:
    """Search for tickets in the configured TDX app."""

    s = get_settings()

    response = requests.post(
        f"{s.tdx_base_url}/api/{s.tdx_app_id}/tickets/search",
        headers=authenticate(),
        json=search_body or {},
    )
    response.raise_for_status()

    return response.json()


def download_attachment(content_uri: str) -> bytes:
    """Download an attachment's bytes from its ContentUri."""

    s = get_settings()

    response = requests.get(
        f"{s.tdx_base_url}/{content_uri}",
        headers=authenticate(),
    )
    response.raise_for_status()

    return response.content


def get_attribute(ticket: dict, name: str) -> str | None:
    """Return the ValueText of a ticket's custom attribute, or None."""

    for attr in ticket["Attributes"]:
        if attr["Name"] == name:
            return attr["ValueText"]

    return None
