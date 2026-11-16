"""
Copy a TDX ticket's attachments to a PCR360 Service Desk record.

Used by every form that creates a PCR360 record. Runs after TDX has its
response, so it never raises: files that can't be attached are listed in
one remark on the record instead.
"""

import logging
from collections.abc import Callable

from app.clients import pcr360

logger = logging.getLogger(__name__)

# Larger files are not sent to PCR360; a remark on the record says so.
MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024


def attach_files(
    ticket: dict,
    record: dict,
    *,
    download: Callable[[str], bytes],
    upload: Callable[..., dict],
    remark: Callable[..., dict],
) -> None:
    attachments = ticket.get("Attachments") or []
    if not attachments:
        return

    try:
        # The create returned the record number ("IQ00000127", "PR-000081").
        target = pcr360.sd_target(record["servicedesk"])
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
        # The record already exists and TDX already has its answer.
        logger.exception("Attachments for ticket %s failed", ticket.get("ID"))


def _attach_one(attachment: dict, target: dict, download, upload) -> str | None:
    """Attach one file. Returns a note for the record if it wasn't attached."""

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
