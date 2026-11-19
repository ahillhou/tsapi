"""On-demand reports (CSV downloads). Protected by REPORTS_SECRET."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool

from app.clients.pcr360 import PCR360Error
from app.clients.ringcentral.analytics import MAX_ANALYTICS_DAYS
from app.clients.ringcentral.errors import RingCentralError
from app.core.security import require_reports_secret
from app.services import number_audit, ringcentral_reports

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_reports_secret)],
)


@router.get(
    "/ringcentral/unused-licenses",
    summary="RingCentral users with no calls (CSV)",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV file"},
        401: {"description": "Missing or wrong secret (use Authorize)"},
        502: {"description": "RingCentral refused or failed"},
    },
)
async def unused_licenses(
    days: int = Query(
        ringcentral_reports.DEFAULT_UNUSED_DAYS,
        ge=1,
        le=MAX_ANALYTICS_DAYS,
        description="Look back this many days (1-184).",
    ),
):
    """
    Enabled RingCentral users with no inbound or outbound calls in the last
    `days` days: candidates for reclaiming a license.

    On this page: click **Authorize**, paste the reports secret, then
    **Try it out** > **Execute** > **Download file**. It can take a minute
    or two for a large account.
    """

    try:
        rows = await run_in_threadpool(ringcentral_reports.unused_licenses, days)
    except RingCentralError as exc:
        logger.error("Unused licenses report failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from None

    body = ringcentral_reports.to_csv(rows, ringcentral_reports.UNUSED_COLUMNS)
    filename = f"ringcentral-unused-{days}d-{date.today().isoformat()}.csv"

    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _run_number_audit() -> dict:
    try:
        return await run_in_threadpool(number_audit.run_audit)
    except (RingCentralError, PCR360Error) as exc:
        logger.error("Number audit failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from None


@router.get(
    "/number-audit",
    summary="Phone number audit: PCR360 vs RingCentral (CSV)",
    response_class=Response,
    responses={
        200: {"content": {"text/csv": {}}, "description": "CSV file"},
        401: {"description": "Missing or wrong secret (use Authorize)"},
        502: {"description": "PCR360 or RingCentral refused or failed"},
    },
)
async def phone_number_audit(
    include_matches: bool = Query(
        False,
        description="Also list numbers that agree (PCR360 Active, RingCentral assigned).",
    ),
):
    """
    Every phone number in PCR360 **production** or RingCentral, one row
    each. The **Comparison** column says where the number is in each system:

    - PCR360 side: *Not in PCR360*, *Available*, *Active*, *Order Pending*, *Inactive*
    - RingCentral side: *not in RingCentral*, *assigned* (on an extension), *unassigned*

    e.g. "PCR360 Available, RingCentral assigned" or "PCR360 Active, not in
    RingCentral". Numbers that agree (Active and assigned) are left out unless
    **include_matches** is true. Filter on **RingCentral Type** to drop e.g.
    ContactCenterNumber. Read-only on both systems; takes 1-3 minutes.

    On this page: click **Authorize**, paste the reports secret, then
    **Try it out** > **Execute** > **Download file**. For just the counts,
    use **/reports/number-audit/summary**.
    """

    audit = await _run_number_audit()
    rows = [
        {c: row[c] for c in number_audit.COLUMNS}
        for row in audit["rows"]
        if include_matches or not number_audit.is_match(row)
    ]

    body = ringcentral_reports.to_csv(rows, number_audit.COLUMNS)
    filename = f"number-audit-{date.today().isoformat()}.csv"

    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/number-audit/summary",
    summary="Phone number audit: counts only (JSON)",
    responses={
        401: {"description": "Missing or wrong secret (use Authorize)"},
        502: {"description": "PCR360 or RingCentral refused or failed"},
    },
)
async def phone_number_audit_summary():
    """
    How many numbers fall in each comparison (see /reports/number-audit),
    matches included, shown right on this page. Takes 1-3 minutes.
    """

    audit = await _run_number_audit()

    return {
        "pcr360_phone_services": audit["pcr360_phone_services"],
        "ringcentral_numbers": audit["ringcentral_numbers"],
        "counts": number_audit.summarize(audit["rows"]),
    }
