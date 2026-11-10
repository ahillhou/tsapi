"""TDX "RingCentral Request" form -> PCR360 Service Order (test)."""

import logging
import re

from app.clients import pcr360
from app.clients.tdx import download_attachment, get_ticket
from app.services.tdx_remarks import (
    build_ringcentral_request_remarks,
    build_service_request_remarks,
)

logger = logging.getLogger(__name__)

SERVICE_ORDER_DESCRIPTION = "RingCentral New Request"

# Departments whose requests go to the OIT Communications Design group's
# workflow. Matched on the 6-digit department number in the ticket's
# Acct/Dept name; TDX shows it after the name, e.g.
# "SPSF Student Health Services 115017".
DESIGN_DEPARTMENTS = {
    "115017": "SPSF Student Health Services",
    "115009": "SPSF Student Counseling Services",
    "113018": "CHEW Employee Wellness",
    "111401": "OIT Technology Fee STF",
    "103008": "One Stop",
    "150012": "Athletic Information Tech",
    "110525": "Police Control",
    "190500": "VetMed Hospital Operations Administration",
    "103800": "Digital Learning",
}

# PCR360 (test) Service Desk Classification RECIDs. Each one selects a
# workflow. None = not created yet, so no sdc is sent.
DESIGN_SDC: int | None = None
DEFAULT_SDC: int | None = None

_DEPARTMENT_NUMBER = re.compile(r"\b(\d{6})\b")


def department_number(ticket: dict) -> str | None:
    """The 6-digit department number in the ticket's Acct/Dept, if any (last one wins)."""

    numbers = _DEPARTMENT_NUMBER.findall(ticket.get("AccountName") or "")
    return numbers[-1] if numbers else None


def is_design_department(ticket: dict) -> bool:
    return department_number(ticket) in DESIGN_DEPARTMENTS


def choose_sdc(ticket: dict) -> int | None:
    return DESIGN_SDC if is_design_department(ticket) else DEFAULT_SDC


def submit_ringcentral_request(ticket: dict) -> dict:
    """Create the Service Order and copy the ticket's attachments to it."""

    attachments = ticket.get("Attachments") or []
    design = is_design_department(ticket)
    sdc = choose_sdc(ticket)

    logger.info(
        "RingCentral request: ticket %s, %s, dept %r -> %s workflow (sdc %s), %d attachments",
        ticket["ID"],
        ticket["Title"],
        ticket.get("AccountName"),
        "design" if design else "default",
        sdc,
        len(attachments),
    )

    remarks = build_ringcentral_request_remarks(ticket)

    # Attachments go in the SO create call itself. A separate
    # type=ATTACHMENT call made PCR360 test return HTTP 500 (2026-11-10).
    files = []
    for attachment in attachments:
        file_content = download_attachment(attachment["ContentUri"])
        logger.info("Downloaded attachment %s (%d bytes)", attachment["Name"], len(file_content))
        files.append(pcr360.encode_file(attachment["Name"], file_content))

    result = pcr360.create_service_order(
        description=SERVICE_ORDER_DESCRIPTION,
        remarks=remarks,
        sdc=sdc,
        files=files,
    )

    sd_number = result.get("servicedesk")
    if not sd_number or result.get("status") == "failure":
        # The route turns this into a 502 for TDX.
        logger.error("PCR360 did not create the SO: %s", result)
        return result

    logger.info("PCR360 SO number: %s (sent %d attachments with it)", sd_number, len(files))

    return result


def process_ringcentral_ticket(ticket_id: int) -> dict:
    """Fetch a ticket from TDX and create a Service Request from it (debug)."""

    ticket = get_ticket(ticket_id)

    return pcr360.create_service_request(
        description=ticket["Title"],
        remarks=build_service_request_remarks(ticket),
    )
