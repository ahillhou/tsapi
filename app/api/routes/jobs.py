"""Jobs run by hand from the Swagger page. Protected by REPORTS_SECRET."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from app.clients.pcr360 import PCR360Error
from app.core.security import require_reports_secret
from app.services import access_request_close

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_reports_secret)],
)


@router.post(
    "/access-requests/close",
    summary="Resolve TDX tickets of finished PCR access requests",
    responses={
        401: {"description": "Missing or wrong secret (use Authorize)"},
        502: {"description": "PCR360 query failed"},
    },
)
async def close_access_requests(
    dry_run: bool = Query(True, description="Only report what would change. Set false to resolve the tickets."),
    days: int = Query(
        access_request_close.DEFAULT_DAYS,
        ge=1,
        le=365,
        description="Access requests voided in the last this many days.",
    ),
    only: str | None = Query(None, description="Just this inquiry, e.g. IQ00000141."),
):
    """
    Finds PCR access requests in PCR360 **production** that are VOID with
    **Complete** ticked, and sets each one's **production** TDX ticket to
    Resolved with a private comment ("Completed in PCR360 (IQ...)").
    Tickets that are already closed are left alone. PCR360 is only read.

    Leave **dry_run** on first: the result lists every inquiry with
    `would resolve`, `already closed`, `wrong app`, `no ticket number` or
    `error`. On this page: **Authorize** with the reports secret, then
    **Try it out** > **Execute**.
    """

    try:
        return await run_in_threadpool(access_request_close.close_completed, days, dry_run, only)
    except PCR360Error as exc:
        logger.error("Access request close-out failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from None
