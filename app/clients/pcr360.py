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


def create_service_order() -> str:
    """Create a sample Service Order in PCR360 **test**. Debug use only."""

    remarks = (
        "Employee Name: John Smith<br><br>"
        "Employee NetID: jsmith27<br><br>"
        "Phone Number: (865) 555-1234<br><br>"
        "Date When Needed: 1/23/27<br><br>"
        "Account Number: 8934563<br><br>"
        "Software Only Account: No<br><br>"
        "Phone Model Requested: VVX-150"
    )

    payload = {
        "type": "SO",
        "csr": 1,
        "description": "New Voice Request",
        "remarks": remarks,
    }

    response = requests.post(_test_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)
    response.raise_for_status()

    return response.json()["servicedesk"]


def create_service_request(description: str, remarks: str) -> dict:
    """Create a Service Request in PCR360 **test**."""

    payload = {
        "type": "SR",
        "csr": 1,
        "description": description,
        "remarks": remarks,
    }

    response = requests.post(_test_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)
    response.raise_for_status()

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

    response = requests.post(_prod_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)

    logger.info("PCR360 status %s: %s", response.status_code, response.text)

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

    response = requests.post(_test_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)

    logger.info("PCR360 status %s: %s", response.status_code, response.text)

    response.raise_for_status()
    return response.json()


def add_equipment(so_number: str) -> dict:
    """Add a VVX-150 to a Service Order in PCR360 **test**. Debug use only."""

    payload = {
        "type": "EQUIPMENT",
        "sd_number": so_number,
        "qty": 1,
        "eqp_catalog": VVX_150,
    }

    response = requests.post(_legacy_test_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)

    logger.info("Equipment status %s: %s", response.status_code, response.text)

    response.raise_for_status()
    return response.json()


def upload_attachment(sd_number: str, filename: str, file_content: bytes) -> dict:
    """
    Attach a file to a Service Desk record in PCR360 **test**.

    Returns {"status": "error", "response": ...} instead of raising when
    PCR360 rejects the request.
    """

    payload = {
        "type": "ATTACHMENT",
        "sd_number": sd_number,
        "files": [
            {
                "filename": filename,
                "data": base64.b64encode(file_content).decode("utf-8"),
            }
        ],
    }

    logger.info(
        "Uploading attachment %s (%d bytes) to %s",
        filename,
        len(file_content),
        sd_number,
    )

    response = requests.post(_test_url(), headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)

    logger.info("Attachment status %s: %s", response.status_code, response.text)

    if response.status_code >= 400:
        return {
            "status": "error",
            "response": response.text,
        }

    return response.json()
