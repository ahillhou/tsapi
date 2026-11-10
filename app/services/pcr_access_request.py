"""TDX "PCR account access" form -> PCR360 Inquiry."""

import logging

from app.clients import pcr360
from app.clients.tdx import download_attachment, get_attribute
from app.services.tdx_remarks import build_access_request_remarks

logger = logging.getLogger(__name__)

# Every production access request goes to this mailbox on purpose, not to
# the TDX requestor (their name and email are included in the remarks).
INQUIRY_EMAIL = "ahillhou@utk.edu"
INQUIRY_TOPIC = 482

TEST_INQUIRY_TOPIC = 349


def submit_access_request(ticket: dict) -> dict:
    """Create the Inquiry in PCR360 **production**."""

    logger.info("PCR access request: ticket %s, %s", ticket["ID"], ticket["Title"])

    remarks = build_access_request_remarks(ticket)
    logger.info("Remarks: %s", remarks)

    access_change = get_attribute(ticket, "PCR Type")

    result = pcr360.create_inquiry(
        subject=f"{access_change} PCR Access",
        message=remarks,
        email=INQUIRY_EMAIL,
        topic=INQUIRY_TOPIC,
    )

    logger.info("PCR360 servicedesk: %s", result.get("servicedesk"))

    return result


def submit_test_access_request(ticket: dict) -> dict:
    """Same flow against PCR360 **test**, including attachments."""

    logger.info("TEST PCR access request: ticket %s, %s", ticket["ID"], ticket["Title"])

    remarks = build_access_request_remarks(ticket)
    access_change = get_attribute(ticket, "PCR Type")

    result = pcr360.test_create_inquiry(
        subject=f"{access_change} PCR Access",
        message=remarks,
        email=ticket["RequestorEmail"],
        topic=TEST_INQUIRY_TOPIC,
    )

    iq_number = result["servicedesk"]
    logger.info("Inquiry number: %s", iq_number)

    # PCR360 ATTACHMENT takes the service desk number itself (e.g. "IQ123"),
    # which the create call already returned.
    for attachment in ticket.get("Attachments", []):
        file_content = download_attachment(attachment["ContentUri"])

        pcr360.upload_attachment(
            sd_number=iq_number,
            filename=attachment["Name"],
            file_content=file_content,
        )

    return result
