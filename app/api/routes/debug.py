"""
Manual testing endpoints. Not called by TDX or RingCentral.

Most of these talk to PCR360 test; /ticket and /test-fields read live
TDX tickets.
"""

import os

from fastapi import APIRouter

from app.clients import pcr360
from app.clients.tdx import get_attribute, get_ticket
from app.services.ringcentral_request import process_ringcentral_ticket

router = APIRouter(tags=["debug"])


@router.get("/envtest")
def envtest():
    return {
        "tdx_username": os.getenv("TDX_USERNAME"),
        "has_password": os.getenv("TDX_PASSWORD") is not None,
    }


@router.post("/test-so")
def test_so():
    so_number = pcr360.create_service_order()
    equipment_result = pcr360.add_equipment(so_number)

    return {"service_order": so_number, "equipment_result": equipment_result}


@router.post("/test_attachment")
def test_attachment():
    with open("test.txt", "rb") as f:
        file_content = f.read()

    return pcr360.upload_attachment(
        sd_number="IQ00000011",
        filename="test.txt",
        file_content=file_content,
    )


@router.get("/ticket/{ticket_id}")
def ticket_lookup(ticket_id: int):
    return get_ticket(ticket_id)


@router.post("/process-ticket/{ticket_id}")
def process_ticket(ticket_id: int):
    return process_ringcentral_ticket(ticket_id)


@router.get("/test-fields/{ticket_id}")
def test_fields(ticket_id: int):
    ticket = get_ticket(ticket_id)

    return {
        "location": get_attribute(ticket, "RC Location"),
        "account_type": get_attribute(ticket, "RC Account Type"),
        "handset": get_attribute(ticket, "RC Physical Handset"),
    }
