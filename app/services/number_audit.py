"""
Phone number audit: PCR360 (production) vs RingCentral.

Matches numbers on their last 10 digits and lists four kinds of row, each
labelled in the "Problem" column:

- RingCentral unassigned, not in PCR360: on no RingCentral extension and
  PCR360 has no phone service with that number.
- PCR360 Available, RingCentral assigned: PCR360 says free, but RingCentral
  has it on an extension.
- PCR360 Active, RingCentral unassigned: PCR360 says in use, but it is on no
  RingCentral extension.
- PCR360 Available, RingCentral unassigned: both say free (the reusable
  pool).

"Assigned" means the RingCentral number has an extension. The RingCentral
type (DirectNumber, CompanyNumber, IntegrationNumber, ContactCenterNumber,
...) is a column so rows can be filtered; e.g. IntegrationNumber may be
Microsoft Teams numbers (unconfirmed), and company numbers on no extension
can still be live main lines routed by the auto-receptionist.
"""

import logging
import re

from app.clients import pcr360
from app.clients.ringcentral.auth import get_platform
from app.clients.ringcentral.phone_numbers import list_phone_numbers

logger = logging.getLogger(__name__)

RC_UNASSIGNED_NOT_IN_PCR = "RingCentral unassigned, not in PCR360"
PCR_AVAILABLE_RC_ASSIGNED = "PCR360 Available, RingCentral assigned"
PCR_ACTIVE_RC_UNASSIGNED = "PCR360 Active, RingCentral unassigned"
BOTH_FREE = "PCR360 Available, RingCentral unassigned"

PROBLEM_ORDER = [
    RC_UNASSIGNED_NOT_IN_PCR,
    PCR_AVAILABLE_RC_ASSIGNED,
    PCR_ACTIVE_RC_UNASSIGNED,
    BOTH_FREE,
]

COLUMNS = [
    "Problem",
    "Number",
    "PCR360 Status",
    "RingCentral Type",
    "RingCentral Status",
    "RingCentral Extension",
]

# When PCR360 has the same number more than once, the most "in use" status wins.
_PCR_STATUS_PRIORITY = ["ACTIVE", "ORDER_PENDING", "AVAILABLE", "INACTIVE"]


def ten_digits(number) -> str | None:
    """'+18659740485', '(865) 974-0485', '8659740485' -> '8659740485'."""

    digits = re.sub(r"\D", "", str(number or ""))
    return digits[-10:] if len(digits) >= 10 else None


def _fmt(number: str) -> str:
    return f"{number[:3]}-{number[3:6]}-{number[6:]}"


def _rank(status: str) -> int:
    return _PCR_STATUS_PRIORITY.index(status) if status in _PCR_STATUS_PRIORITY else len(_PCR_STATUS_PRIORITY)


def _pcr_statuses(rows: list[dict]) -> dict[str, str]:
    """10-digit number -> PCR360 status code."""

    statuses: dict[str, str] = {}

    for row in rows:
        number = ten_digits(row.get("SERVICE_ID"))
        status = (row.get("STATUS") or "").upper()

        if number and (number not in statuses or _rank(status) < _rank(statuses[number])):
            statuses[number] = status

    return statuses


def _problem(pcr_status: str | None, assigned: bool) -> str | None:
    if pcr_status is None:
        return None if assigned else RC_UNASSIGNED_NOT_IN_PCR
    if pcr_status == "AVAILABLE":
        return PCR_AVAILABLE_RC_ASSIGNED if assigned else BOTH_FREE
    if pcr_status == "ACTIVE" and not assigned:
        return PCR_ACTIVE_RC_UNASSIGNED
    return None


def build_audit(pcr_rows: list[dict], rc_numbers: list[dict]) -> list[dict]:
    """Compare the two lists; pure, so it can be tested without either system."""

    pcr = _pcr_statuses(pcr_rows)
    rows = []

    for record in rc_numbers:
        number = ten_digits(record.get("phoneNumber"))
        if not number:
            continue

        extension = record.get("extension") or {}
        assigned = bool(extension)
        pcr_status = pcr.get(number)
        problem = _problem(pcr_status, assigned)

        if problem:
            rows.append(
                {
                    "Problem": problem,
                    "Number": _fmt(number),
                    "PCR360 Status": pcr_status or "",
                    "RingCentral Type": record.get("usageType") or "",
                    "RingCentral Status": record.get("status") or "",
                    "RingCentral Extension": str(extension.get("extensionNumber") or ""),
                }
            )

    rows.sort(key=lambda r: (PROBLEM_ORDER.index(r["Problem"]), r["Number"]))
    return rows


def number_audit() -> list[dict]:
    """Read PCR360 production and RingCentral, then compare. Read-only on both."""

    pcr_rows = pcr360.prod_phone_numbers()
    rc_numbers = list_phone_numbers(get_platform())

    rows = build_audit(pcr_rows, rc_numbers)

    counts = {p: sum(r["Problem"] == p for r in rows) for p in PROBLEM_ORDER}
    logger.info(
        "Number audit: %d PCR360 phone services, %d RingCentral numbers; %s",
        len(pcr_rows),
        len(rc_numbers),
        counts,
    )

    return rows
