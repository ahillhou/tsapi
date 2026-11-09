"""Webhooks called by RingCentral workflows."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.clients.ringcentral.presence import set_dnd
from app.core.security import ringcentral_webhook
from app.services.nurse_dayoff import handle_sms_command

logger = logging.getLogger(__name__)

router = APIRouter(
    tags=["ringcentral"],
    dependencies=[Depends(ringcentral_webhook)],
)


async def read_ringcentral_json(request: Request) -> dict:
    """
    Parse a RingCentral workflow body.

    RingCentral sends non-breaking spaces (U+00A0) that break JSON parsing,
    so they're replaced first. String values are stripped of whitespace.
    """
    body = (await request.body()).decode("utf-8").replace(" ", " ")
    logger.info("RingCentral payload: %s", body)

    data = json.loads(body)

    return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}


# RingCentral SDK calls are blocking, so they run in a worker thread to
# avoid stalling other requests (e.g. TDX webhooks) on the event loop.


@router.post("/demo/dayoff")
async def demo_dayoff(request: Request):
    """Nurse texts DAYOFF/BACK -> toggle their call rule and text back."""

    data = await read_ringcentral_json(request)

    result = await run_in_threadpool(
        handle_sms_command,
        data["extensionId"],
        data["command"],
        data["sender"],
    )

    return {"status": "success", "message": result}


@router.post("/ringcentral/dnd")
async def dnd(request: Request):
    """DAYOFF/BACK -> turn Do Not Disturb on/off for an extension."""

    data = await read_ringcentral_json(request)

    command = data["command"].upper()
    extension_id = data["extensionId"]

    if command == "DAYOFF":
        await run_in_threadpool(set_dnd, extension_id, True)
        return {"status": "success", "action": "dnd_enabled"}

    if command == "BACK":
        await run_in_threadpool(set_dnd, extension_id, False)
        return {"status": "success", "action": "dnd_disabled"}

    return {"status": "ignored", "command": command}


@router.post("/ringcentral/dayoff")
async def dayoff(request: Request):
    """
    Not working: before the restructure this route always crashed
    (NurseDayOffService was created without a RingCentral platform and
    handle() was called with the wrong arguments). It now fails clearly
    instead. /demo/dayoff is the working version.
    """

    await read_ringcentral_json(request)

    raise HTTPException(
        status_code=501,
        detail="/ringcentral/dayoff is not implemented; use /demo/dayoff",
    )
