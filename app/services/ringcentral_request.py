"""TDX "RingCentral new request" form -> PCR360 Service Request (test)."""

import logging

from app.clients import pcr360
from app.clients.tdx import download_attachment, get_ticket
from app.services.tdx_remarks import (
    build_ringcentral_request_remarks,
    build_service_request_remarks,
)

logger = logging.getLogger(__name__)


def submit_ringcentral_request(ticket: dict) -> dict:
    """Create the Service Request and copy the ticket's attachments to it."""

    attachments = ticket.get("Attachments", [])

    logger.info(
        "RingCentral request: ticket %s, %s (%d attachments)",
        ticket["ID"],
        ticket["Title"],
        len(attachments),
    )

    remarks = build_ringcentral_request_remarks(ticket)
    logger.info("Remarks: %s", remarks)

    result = pcr360.create_service_request(
        description="RingCentral New Request",
        remarks=remarks,
    )

    sd_number = result["servicedesk"]
    logger.info("PCR360 SR number: %s", sd_number)

    for attachment in attachments:
        logger.info("Processing attachment: %s", attachment["Name"])

        file_content = download_attachment(attachment["ContentUri"])

        pcr360.upload_attachment(
            sd_number=sd_number,
            filename=attachment["Name"],
            file_content=file_content,
        )

    return result


def process_ringcentral_ticket(ticket_id: int) -> dict:
    """Fetch a ticket from TDX and create a Service Request from it."""

    ticket = get_ticket(ticket_id)

    return pcr360.create_service_request(
        description=ticket["Title"],
        remarks=build_service_request_remarks(ticket),
    )
