"""TDX project intake form -> PCR360 Project (test and production)."""

import logging

from app.clients import pcr360
from app.clients.tdx import download_attachment, download_prod_attachment
from app.services.pcr_attachments import attach_files
from app.services.tdx_remarks import build_project_intake_remarks

logger = logging.getLogger(__name__)

# CSR (contact RECID) on the created project. Production uses the same CSR
# as the access-request inquiries; test uses the demo contact like the
# other test records.
PROJECT_CSR = 566
TEST_PROJECT_CSR = 1

# Service Desk Classification (workflow). None = PCR360's default. Set
# these once project SDCs exist.
PROJECT_SDC: int | None = None
TEST_PROJECT_SDC: int | None = None


def _description(ticket: dict) -> str:
    return ticket.get("Title") or f"Project intake (TDX {ticket['ID']})"


def submit_project_intake(ticket: dict) -> dict:
    """Create the Project in PCR360 **production**."""

    logger.info("Project intake: ticket %s, %s", ticket["ID"], ticket.get("Title"))

    result = pcr360.create_project(
        description=_description(ticket),
        remarks=build_project_intake_remarks(ticket),
        csr=PROJECT_CSR,
        sdc=PROJECT_SDC,
    )

    logger.info("PCR360 project: %s", result.get("servicedesk") or result)
    return result


def attach_project_intake_files(ticket: dict, project: dict) -> None:
    """Copy the (production TDX) ticket's attachments to the production project."""

    attach_files(
        ticket,
        project,
        download=download_prod_attachment,
        upload=pcr360.upload_prod_attachment,
        remark=pcr360.add_prod_remark,
    )


def submit_test_project_intake(ticket: dict) -> dict:
    """Create the Project in PCR360 **test**."""

    logger.info("TEST project intake: ticket %s, %s", ticket["ID"], ticket.get("Title"))

    result = pcr360.create_test_project(
        description=_description(ticket),
        remarks=build_project_intake_remarks(ticket),
        csr=TEST_PROJECT_CSR,
        sdc=TEST_PROJECT_SDC,
    )

    logger.info("PCR360 test project: %s", result.get("servicedesk") or result)
    return result


def attach_test_project_intake_files(ticket: dict, project: dict) -> None:
    """Copy the (sandbox TDX) ticket's attachments to the test project."""

    attach_files(
        ticket,
        project,
        download=download_attachment,
        upload=pcr360.upload_attachment,
        remark=pcr360.add_remark,
    )
