"""TDX "PCR account access" form -> PCR360 Inquiry."""

import logging
from collections.abc import Callable

from app.clients import pcr360
from app.clients.tdx import download_attachment, download_prod_attachment, get_attribute
from app.services.tdx_remarks import build_access_request_remarks

logger = logging.getLogger(__name__)

# Every production access request goes to this mailbox on purpose, not to
# the TDX requestor (their name and email are included in the remarks).
INQUIRY_EMAIL = "ahillhou@utk.edu"
INQUIRY_TOPIC = 482

TEST_INQUIRY_TOPIC = 349

# Larger files are not sent to PCR360; a remark on the inquiry says so.
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


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


def attach_access_request_files(ticket: dict, inquiry: dict) -> None:
    """
    Copy the ticket's attachments to the **production** inquiry.

    Runs after TDX has its response, so it must never raise.
    """

    _attach_files(
        ticket,
        inquiry,
        download=download_prod_attachment,
        upload=pcr360.upload_prod_attachment,
        remark=pcr360.add_prod_remark,
    )


def submit_test_access_request(ticket: dict) -> dict:
    """Same flow against PCR360 **test**."""

    logger.info("TEST PCR access request: ticket %s, %s", ticket["ID"], ticket["Title"])

    remarks = build_access_request_remarks(ticket)
    access_change = get_attribute(ticket, "PCR Type")

    result = pcr360.test_create_inquiry(
        subject=f"{access_change} PCR Access",
        message=remarks,
        email=ticket["RequestorEmail"],
        topic=TEST_INQUIRY_TOPIC,
    )

    logger.info("Inquiry RECID: %s", result.get("servicedesk"))

    return result


def attach_test_access_request_files(ticket: dict, inquiry: dict) -> None:
    """Copy the (sandbox) ticket's attachments to the **test** inquiry."""

    _attach_files(
        ticket,
        inquiry,
        download=download_attachment,
        upload=pcr360.upload_attachment,
        remark=pcr360.add_remark,
    )


def _attach_files(
    ticket: dict,
    inquiry: dict,
    *,
    download: Callable[[str], bytes],
    upload: Callable[..., dict],
    remark: Callable[..., dict],
) -> None:
    attachments = ticket.get("Attachments") or []
    if not attachments:
        return

    try:
        # The create returned the inquiry number ("IQ00000127").
        target = pcr360.sd_target(inquiry["servicedesk"])
        problems = []

        for attachment in attachments:
            problem = _attach_one(attachment, target, download, upload)
            if problem:
                problems.append(problem)

        if problems:
            note = (
                "".join(f"{p}<br><br>" for p in problems)
                + f"Please get these files from TDX Ticket ID# {ticket['ID']}."
            )

            result = remark(note, **target)
            if result.get("status") == "error":
                logger.error("Could not add the attachment note to %s: %s", target, result)

    except Exception:
        # The inquiry already exists and TDX already has its answer.
        logger.exception("Attachments for ticket %s failed", ticket.get("ID"))


def _attach_one(attachment: dict, target: dict, download, upload) -> str | None:
    """Attach one file. Returns a note for the inquiry if it wasn't attached."""

    name = attachment.get("Name") or "(unnamed file)"
    size = attachment.get("Size") or 0

    if size > MAX_ATTACHMENT_BYTES:
        logger.warning("Attachment %s is too large (%d bytes); not sent", name, size)
        return f"Attachment {name} ({_mb(size)}) is over the 50 MB limit and was not added"

    try:
        content = download(attachment["ContentUri"])
    except Exception as exc:
        logger.error("Could not download attachment %s from TDX: %s", name, type(exc).__name__)
        return f"Attachment {name} could not be downloaded from TDX and was not added"

    if len(content) > MAX_ATTACHMENT_BYTES:
        logger.warning("Attachment %s is too large (%d bytes); not sent", name, len(content))
        return f"Attachment {name} ({_mb(len(content))}) is over the 50 MB limit and was not added"

    result = upload(name, content, **target)

    if result.get("status") == "error":
        logger.error("PCR360 rejected attachment %s: %s", name, result)
        return f"Attachment {name} could not be added (PCR360 rejected the file)"

    return None


def _mb(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"
