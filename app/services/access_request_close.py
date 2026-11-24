"""
Close the TDX ticket when its PCR access request is finished.

Staff finish a PCR access request (TDX form -> PCR360 production Inquiry,
see pcr_access_request.py) by ticking its "Complete" checkbox and setting it
to VOID. This finds those inquiries in PCR360 production (read-only) and
sets each one's production TDX ticket to Resolved with a private comment.

Safe to run again and again: a ticket that is already closed (Resolved,
Cancelled...) is never touched, so a reopened or hand-closed ticket stays
as staff left it. PCR360 is never written to.
"""

import asyncio
import logging
import re
import threading
import time
from datetime import datetime, timedelta

from fastapi.concurrency import run_in_threadpool

from app.clients import pcr360, tdx
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Production TDX "OIT ITSM" app, where the access request form's tickets live,
# and its "Resolved" status (POST /api/2278/tickets/statuses, 2026-11-24).
TDX_APP_ID = 2278
RESOLVED_STATUS_ID = 98857

# TDX StatusClass: 3 = Completed, 4 = Cancelled.
CLOSED_STATUS_CLASSES = (3, 4)

DEFAULT_DAYS = 14

# TDX allows 60 API calls a minute per IP, for this app and everything else
# on the server. Pause before every call (at most ~55 a minute), and on a
# 429 wait for the window to reset and try again.
PAUSE_SECONDS = 1.1
RATE_LIMIT_WAIT_SECONDS = 61
RATE_LIMIT_RETRIES = 2

sleep = time.sleep  # replaced in tests

# Tickets seen closed (or closed by us) since the app started. They are not
# read again, so the timer costs TDX calls only for new completions, and a
# ticket staff reopen afterwards stays as they left it.
_known_closed: set[int] = set()
_lock = threading.Lock()  # one run at a time (timer and Swagger)

_TICKET_ID = re.compile(r"TDX Ticket ID#:\s*(\d+)")


def ticket_id(message: str | None) -> int | None:
    """The TDX ticket number our remarks put in the inquiry text."""

    match = _TICKET_ID.search(message or "")
    return int(match.group(1)) if match else None


def comment(sd_number: str) -> str:
    return f"Completed in PCR360 ({sd_number}). Closed automatically by TS API."


def close_completed(days: int = DEFAULT_DAYS, dry_run: bool = True, only: str | None = None) -> dict:
    """
    Resolve the TDX tickets of access requests completed in the last `days`
    days (by void date). With dry_run, nothing in TDX changes; the result
    says what would happen. `only` limits it to one inquiry number.

    Raises PCR360Error if the PCR360 query fails; a failure on one ticket is
    recorded in its result and the rest still run.
    """

    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    with _lock:
        inquiries = pcr360.prod_completed_access_requests(since)

        if only:
            inquiries = [i for i in inquiries if i["SD_NUMBER"] == only.strip().upper()]

        results = [_close_one(inquiry, dry_run) for inquiry in inquiries]

    counts: dict[str, int] = {}
    for result in results:
        counts[result["action"]] = counts.get(result["action"], 0) + 1

    logger.info(
        "Access request close-out (%s, voided since %s): %s",
        "dry run" if dry_run else "live",
        since,
        counts or "nothing to do",
    )

    return {"dry_run": dry_run, "since": since, "counts": counts, "results": results}


def _why(exc: Exception) -> str:
    """Short reason for a failed TDX call, e.g. 'HTTPError 403' (no URLs)."""

    status = getattr(getattr(exc, "response", None), "status_code", None)
    return f"{type(exc).__name__} {status}" if status else type(exc).__name__


def _tdx(call, *args):
    """One TDX call, paced, retried after a rate-limit (429) wait."""

    for attempt in range(RATE_LIMIT_RETRIES + 1):
        sleep(PAUSE_SECONDS)

        try:
            return call(*args)
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status != 429 or attempt == RATE_LIMIT_RETRIES:
                raise

        logger.info("TDX rate limit hit; waiting %d s", RATE_LIMIT_WAIT_SECONDS)
        sleep(RATE_LIMIT_WAIT_SECONDS)


def _close_one(inquiry: dict, dry_run: bool) -> dict:
    sd_number = inquiry["SD_NUMBER"]
    tid = ticket_id(inquiry.get("MESSAGE"))
    result = {"inquiry": sd_number, "voided": inquiry.get("VOID_DATE"), "ticket": tid}

    if tid is None:
        logger.warning("Access request %s has no TDX ticket number; skipped", sd_number)
        return {**result, "action": "no ticket number"}

    if tid in _known_closed:
        return {**result, "action": "already closed"}

    try:
        ticket = _tdx(tdx.get_prod_ticket, tid)
    except Exception as exc:  # one bad ticket must not stop the rest
        logger.error("Could not read TDX ticket %s for %s: %s", tid, sd_number, _why(exc))
        return {**result, "action": "error", "error": f"read failed: {_why(exc)}"}

    result["ticket_status"] = ticket.get("StatusName")

    if ticket.get("AppID") != TDX_APP_ID:
        logger.warning("TDX ticket %s (%s) is in app %s, not %s; skipped", tid, sd_number, ticket.get("AppID"), TDX_APP_ID)
        return {**result, "action": "wrong app"}

    if ticket.get("StatusClass") in CLOSED_STATUS_CLASSES:
        _known_closed.add(tid)
        return {**result, "action": "already closed"}

    if dry_run:
        logger.info("Dry run: would resolve TDX ticket %s (%s)", tid, sd_number)
        return {**result, "action": "would resolve"}

    try:
        _tdx(tdx.update_prod_ticket_status, TDX_APP_ID, tid, RESOLVED_STATUS_ID, comment(sd_number))
    except Exception as exc:
        logger.error("Could not resolve TDX ticket %s for %s: %s", tid, sd_number, _why(exc))
        return {**result, "action": "error", "error": f"update failed: {_why(exc)}"}

    _known_closed.add(tid)
    logger.info("Resolved TDX ticket %s (%s completed in PCR360)", tid, sd_number)
    return {**result, "action": "resolved"}


# How often the timer runs (see app/main.py), when ACCESS_REQUEST_AUTOCLOSE
# is dry_run or on.
INTERVAL_SECONDS = 15 * 60


async def run_forever() -> None:
    """The timer: run close_completed every INTERVAL_SECONDS. Never raises."""

    mode = get_settings().access_request_autoclose
    logger.info("Access request close-out timer started (%s, every %d min)", mode, INTERVAL_SECONDS // 60)

    while True:
        await asyncio.sleep(INTERVAL_SECONDS)

        try:
            await run_in_threadpool(close_completed, DEFAULT_DAYS, mode != "on")
        except Exception as exc:  # keep the timer alive; try again next time
            logger.error("Access request close-out run failed: %s", exc)
