"""On-demand reports (CSV downloads). Protected by REPORTS_SECRET."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.concurrency import run_in_threadpool

from app.clients.ringcentral.analytics import MAX_ANALYTICS_DAYS
from app.clients.ringcentral.errors import RingCentralError
from app.core.security import require_reports_secret
from app.services import ringcentral_reports

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_reports_secret)],
)


@router.get("/ringcentral/unused-licenses")
async def unused_licenses(
    days: int = Query(ringcentral_reports.DEFAULT_UNUSED_DAYS, ge=1, le=MAX_ANALYTICS_DAYS),
):
    """CSV of enabled RingCentral users with no calls in the last `days` days."""

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
