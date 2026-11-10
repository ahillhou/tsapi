"""
Webhooks called by TDX form workflows.

DO NOT change these paths. The TDX admin owns the form/web-service
configuration and the URLs can't be updated from our side. See
tests/test_route_contract.py.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import tdx_webhook

from app.schemas.tdx import TDXWebhook
from app.services.pcr_access_request import (
    submit_access_request,
    submit_test_access_request,
)
from app.services.ringcentral_request import submit_ringcentral_request

router = APIRouter(
    prefix="/tdx",
    tags=["tdx"],
    dependencies=[Depends(tdx_webhook)],
)


def _processed(result: dict) -> dict:
    # PCR360 errors must not come back to TDX as a 200, or the failure
    # would look like a success in the TDX workflow. PCR360 can report a
    # failure as {"status": "failure", "message": ...} even with HTTP 200,
    # so anything without a servicedesk number counts as failed.
    if result.get("status") in ("error", "failure") or not result.get("servicedesk"):
        raise HTTPException(status_code=502, detail=result)

    return {"status": "processed", "service_request": result}


@router.post("/webhook")
def ringcentral_request(payload: TDXWebhook):
    """RingCentral new request form -> PCR360 (test) Service Request."""
    return _processed(submit_ringcentral_request(payload.data))


@router.post("/webhook/access_request")
def access_request(payload: TDXWebhook):
    """PCR account access form -> PCR360 (production) Inquiry."""
    return _processed(submit_access_request(payload.data))


@router.post("/webhook/test_access_request")
def test_access_request(payload: TDXWebhook):
    """PCR account access form -> PCR360 (test) Inquiry with attachments."""
    return _processed(submit_test_access_request(payload.data))
