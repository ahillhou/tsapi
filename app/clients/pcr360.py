"""
PCR360 API client.

Each function talks to a fixed PCR360 instance (test or prod). That is
deliberate and matches what is deployed today; see the docstrings.
"""

import base64
import json
import logging

import requests

from app.core.config import HTTP_TIMEOUT, get_settings

logger = logging.getLogger(__name__)

HEADERS = {
    "Content-Type": "application/json",
    "Pcr-Html-Encoded": "TRUE",
}

# See upload_attachment().
ATTACHMENT_HEADERS = {"Content-Type": "application/json"}

VVX_150 = 889


def _servicedesk_url(host: str, api_key: str | None) -> str:
    return f"{host}/api/{api_key}/servicedesk.json"


def _test_url() -> str:
    s = get_settings()
    return _servicedesk_url(s.pcr_test_host, s.pcr_test_api_key)


def _prod_url() -> str:
    s = get_settings()
    return _servicedesk_url(s.pcr_prod_host, s.pcr_prod_api_key)


def _legacy_test_url() -> str:
    """Test instance using PCR_API_KEY (only used by add_equipment)."""
    s = get_settings()
    return _servicedesk_url(s.pcr_test_host, s.pcr_api_key)


def encode_file(filename: str, file_content: bytes) -> dict:
    """One entry of PCR360's `files` list."""

    return {
        "filename": filename,
        "data": base64.b64encode(file_content).decode("utf-8"),
    }


def _short(response: requests.Response, limit: int = 300) -> str:
    """Response text for logs. PCR360 errors can be a whole HTML page."""

    text = " ".join(response.text.split())
    return text if len(text) <= limit else text[:limit] + "..."


class PCR360Error(Exception):
    """A failed PCR360 call. Never includes the URL (it holds the API key)."""


def _post(url: str, payload: dict, headers: dict = HEADERS) -> requests.Response:
    try:
        return requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        # requests puts the URL (and so the API key) in its messages.
        raise PCR360Error(f"PCR360 {payload.get('type')} request failed: {type(exc).__name__}") from None


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code >= 400:
        raise PCR360Error(f"PCR360 returned HTTP {response.status_code}: {_short(response, 120)}")


def create_service_order(
    description: str,
    remarks: str,
    sdc: int | None = None,
    files: list[dict] | None = None,
) -> dict:
    """
    Create a Service Order in PCR360 **test**.

    `sdc` is the Service Desk Classification RECID, which picks the
    workflow. It is only sent when given. PCR360's docs list `sdc` for
    IN/WO/IQ but not SO, so confirm on test that an SO accepts it.

    `files` (from encode_file) are attached as part of the create call,
    which the docs allow for any Service Desk item.
    """

    payload = {
        "type": "SO",
        "csr": 1,
        "description": description,
        "remarks": remarks,
    }

    if sdc is not None:
        payload["sdc"] = sdc

    if files:
        payload["files"] = files

    response = _post(_test_url(), payload)

    logger.info(
        "PCR360 SO status %s (%d files): %s",
        response.status_code,
        len(files or []),
        _short(response),
    )

    _raise_for_status(response)
    return response.json()


def create_service_request(description: str, remarks: str) -> dict:
    """Create a Service Request in PCR360 **test**."""

    payload = {
        "type": "SR",
        "csr": 1,
        "description": description,
        "remarks": remarks,
    }

    response = _post(_test_url(), payload)
    _raise_for_status(response)

    return response.json()


def create_inquiry(subject: str, message: str, email: str, topic: int) -> dict:
    """
    Create an Inquiry in PCR360 **production**.

    Returns {"status": "error", "response": ...} instead of raising when
    PCR360 rejects the request.
    """

    payload = {
        "type": "IQ",
        "email": email,
        "subject": subject,
        "message": message,
        "topic": topic,
        "sdc": 6,
        "csr": 566,
    }

    logger.info("Creating PCR360 inquiry for %s", email)
    logger.info("Payload: %s", json.dumps(payload, indent=2))

    response = _post(_prod_url(), payload)

    logger.info("PCR360 status %s: %s", response.status_code, _short(response))

    if response.status_code >= 400:
        return {
            "status": "error",
            "response": response.text,
        }

    return response.json()


def test_create_inquiry(subject: str, message: str, email: str, topic: int) -> dict:
    """Create an Inquiry in PCR360 **test**."""

    payload = {
        "type": "IQ",
        "email": email,
        "subject": subject,
        "message": message,
        "topic": topic,
    }

    response = _post(_test_url(), payload)

    logger.info("PCR360 status %s: %s", response.status_code, _short(response))

    _raise_for_status(response)
    return response.json()


def add_equipment(so_number: str) -> dict:
    """Add a VVX-150 to a Service Order in PCR360 **test**. Debug use only."""

    payload = {
        "type": "EQUIPMENT",
        "sd_number": so_number,
        "qty": 1,
        "eqp_catalog": VVX_150,
    }

    response = _post(_legacy_test_url(), payload)

    logger.info("Equipment status %s: %s", response.status_code, _short(response))

    _raise_for_status(response)
    return response.json()


def _soft_post(url: str, payload: dict, headers: dict = HEADERS) -> dict:
    """
    POST that never raises: returns {"status": "error", "response": ...} on
    a network error, an HTTP error, a non-JSON body or a "failure" body.
    """

    try:
        response = _post(url, payload, headers=headers)
    except PCR360Error as exc:
        return {"status": "error", "response": str(exc)}

    logger.info("PCR360 %s status %s: %s", payload["type"], response.status_code, _short(response))

    if response.status_code >= 400 or not response.text.strip().startswith("{"):
        return {"status": "error", "response": _short(response)}

    result = response.json()

    if result.get("status") == "failure":
        return {"status": "error", "response": result.get("message") or _short(response)}

    return result


def _attachment_payload(target: dict, filename: str, file_content: bytes) -> dict:
    logger.info("Uploading attachment %s (%d bytes) to %s", filename, len(file_content), target)

    return {
        "type": "ATTACHMENT",
        **target,
        "files": [encode_file(filename, file_content)],
    }


# Attachments are sent WITHOUT Pcr-Html-Encoded: that header makes PCR360
# HTML-decode every parameter, and with the nested `files` list it answered
# HTTP 500 (2026-11-10). Nothing in the payload is HTML-encoded, so it isn't
# needed. With the header removed, uploads to an SO work.


def upload_attachment(
    filename: str,
    file_content: bytes,
    *,
    sd_number: str | None = None,
    sd_recid: int | None = None,
) -> dict:
    """
    Attach a file to a Service Desk record in PCR360 **test**.

    Pass sd_number for an SO ("SO-000079") or sd_recid for an Inquiry
    (creating an IQ returns its RECID, not an IQ number). Never raises;
    see _soft_post().
    """

    target = {"sd_recid": sd_recid} if sd_recid is not None else {"sd_number": sd_number}

    return _soft_post(
        _test_url(),
        _attachment_payload(target, filename, file_content),
        headers=ATTACHMENT_HEADERS,
    )


def upload_prod_attachment(filename: str, file_content: bytes, *, sd_recid: int) -> dict:
    """Attach a file to a record in PCR360 **production** by RECID. Never raises."""

    return _soft_post(
        _prod_url(),
        _attachment_payload({"sd_recid": sd_recid}, filename, file_content),
        headers=ATTACHMENT_HEADERS,
    )


def _remark_payload(sd_recid: int, remarks: str) -> dict:
    return {"type": "REMARKS", "sd_recid": sd_recid, "remarks": remarks}


def add_remark(sd_recid: int, remarks: str) -> dict:
    """Add a remark to a record in PCR360 **test**. Never raises."""

    return _soft_post(_test_url(), _remark_payload(sd_recid, remarks))


def add_prod_remark(sd_recid: int, remarks: str) -> dict:
    """Add a remark to a record in PCR360 **production**. Never raises."""

    return _soft_post(_prod_url(), _remark_payload(sd_recid, remarks))
