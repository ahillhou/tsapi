"""
Phone number audit: PCR360 (production) vs RingCentral.

Every number in either system is matched on its last 10 digits and gets a
"Comparison" label made of two halves:

    <where it is in PCR360>, <where it is in RingCentral>

PCR360 side:      Not in PCR360 | PCR360 Available | PCR360 Active |
                  PCR360 Order Pending | PCR360 Inactive
RingCentral side: not in RingCentral | RingCentral assigned |
                  RingCentral unassigned

"Assigned" means the RingCentral number is on an extension. The only
combination treated as matching is "PCR360 Active, RingCentral assigned";
the CSV leaves those out unless asked. The RingCentral type (DirectNumber,
CompanyNumber, IntegrationNumber, ContactCenterNumber, ...) is a column so
rows can be filtered: company numbers on no extension can still be live
main lines routed by an auto-receptionist, and contact center numbers are
never on an extension.
"""

import logging
import re

from app.clients import pcr360
from app.clients.ringcentral.auth import get_platform
from app.clients.ringcentral.phone_numbers import list_phone_numbers

logger = logging.getLogger(__name__)

PCR_LABELS = {
    None: "Not in PCR360",
    "AVAILABLE": "PCR360 Available",
    "ACTIVE": "PCR360 Active",
    "ORDER_PENDING": "PCR360 Order Pending",
    "INACTIVE": "PCR360 Inactive",
}

RC_LABELS = {
    None: "not in RingCentral",
    "assigned": "RingCentral assigned",
    "unassigned": "RingCentral unassigned",
}

MATCH = ("ACTIVE", "assigned")

# (PCR360 status, RingCentral state) in the order rows are listed: mismatches
# first, then "free in both", then the matches.
ORDER = [
    (None, "unassigned"),
    (None, "assigned"),
    ("ACTIVE", None),
    ("ORDER_PENDING", None),
    ("AVAILABLE", None),
    ("INACTIVE", None),
    ("AVAILABLE", "assigned"),
    ("ACTIVE", "unassigned"),
    ("ORDER_PENDING", "assigned"),
    ("ORDER_PENDING", "unassigned"),
    ("INACTIVE", "assigned"),
    ("INACTIVE", "unassigned"),
    ("AVAILABLE", "unassigned"),
    MATCH,
]

COLUMNS = [
    "Comparison",
    "Number",
    "PCR360 Status",
    "RingCentral Type",
    "RingCentral Status",
    "RingCentral Extension",
]

# When PCR360 has the same number more than once, the most "in use" status wins.
_PCR_STATUS_PRIORITY = ["ACTIVE", "ORDER_PENDING", "AVAILABLE", "INACTIVE"]


def label(pcr_status: str | None, rc_state: str | None) -> str:
    pcr = PCR_LABELS.get(pcr_status) or f"PCR360 {pcr_status.replace('_', ' ').title()}"
    return f"{pcr}, {RC_LABELS[rc_state]}"


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


def _order(key: tuple) -> int:
    return ORDER.index(key) if key in ORDER else len(ORDER)


def build_audit(pcr_rows: list[dict], rc_numbers: list[dict]) -> list[dict]:
    """
    One row per number found in either system, matches included, sorted
    by comparison then number. Pure, so it can be tested without either system.
    """

    pcr = _pcr_statuses(pcr_rows)
    rows = []
    seen = set()

    for record in rc_numbers:
        number = ten_digits(record.get("phoneNumber"))
        if not number or number in seen:
            continue
        seen.add(number)

        extension = record.get("extension") or {}
        key = (pcr.get(number), "assigned" if extension else "unassigned")
        rows.append(
            {
                "_key": key,
                "Comparison": label(*key),
                "Number": _fmt(number),
                "PCR360 Status": key[0] or "",
                "RingCentral Type": record.get("usageType") or "",
                "RingCentral Status": record.get("status") or "",
                "RingCentral Extension": str(extension.get("extensionNumber") or ""),
            }
        )

    for number, status in pcr.items():
        if number not in seen:
            key = (status, None)
            rows.append(
                {
                    "_key": key,
                    "Comparison": label(*key),
                    "Number": _fmt(number),
                    "PCR360 Status": status,
                    "RingCentral Type": "",
                    "RingCentral Status": "",
                    "RingCentral Extension": "",
                }
            )

    rows.sort(key=lambda r: (_order(r["_key"]), r["Number"]))
    return rows


def is_match(row: dict) -> bool:
    return row["_key"] == MATCH


def summarize(rows: list[dict]) -> dict[str, int]:
    """Comparison label -> count, in listing order."""

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["Comparison"]] = counts.get(row["Comparison"], 0) + 1
    return counts


def run_audit() -> dict:
    """
    Read PCR360 production and RingCentral, then compare. Read-only on both.
    Returns {"pcr360_phone_services", "ringcentral_numbers", "rows"}.
    """

    pcr_rows = pcr360.prod_phone_numbers()
    rc_numbers = list_phone_numbers(get_platform())
    rows = build_audit(pcr_rows, rc_numbers)

    logger.info(
        "Number audit: %d PCR360 phone services, %d RingCentral numbers; %s",
        len(pcr_rows),
        len(rc_numbers),
        summarize(rows),
    )

    return {
        "pcr360_phone_services": len(pcr_rows),
        "ringcentral_numbers": len(rc_numbers),
        "rows": rows,
    }
