import os
import json

from fastapi import FastAPI, Request
from app.tdx import get_ticket
from app.tdx import build_service_request_remarks
from app.tdx import build_access_request_remarks
from app.tdx import get_attribute
from app.pcr import create_service_order
from app.pcr import create_service_request
from app.pcr import create_inquiry
from app.pcr import add_equipment
from app.processor import process_ringcentral_ticket
from .ring_test import set_dnd
from app.services.nurse_dayoff_service import NurseDayOffService
from app.integrations.ringcentral.auth import get_platform


app = FastAPI()


@app.get("/")
def root():
    return {
        "message": "Voice Automation API Online"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

@app.get("/envtest")
def envtest():
    return {
        "tdx_username": os.getenv("TDX_USERNAME"),
        "has_password": os.getenv("TDX_PASSWORD") is not None
    }

@app.get("/ping")
async def ping():
    print("Ping received")
    return {"message": "pong"}

# @app.on_event("startup")
# def startup_event():

#     thread = threading.Thread(
#         target=poll_tdx,
#         daemon=True
#     )

#     thread.start()

#     print("TDX Poller Started")
    
@app.post("/test-so")
def test_so():

    so_number = create_service_order()
    print("SO: Number:", so_number)
    equipment_result = add_equipment(so_number)

    return {"service_order": so_number, "equipment_result": equipment_result}

# @app.post("/tdx/webhook")
# def tdx_webhook(payload: dict):

#     print("Webhook received")
#     print(payload)

#     return {
#         "status": "received"
#     }

#TDX RC form -> PCR360 as Service Request
# @app.post("/tdx/webhook")
# def ringcentral_request(payload: dict):

#     ticket = payload["data"]

#     remarks = build_service_request_remarks(ticket)

#     result = create_service_request(
#         description=ticket["Title"],
#         remarks=remarks
#     )

#     return {
#         "status": "processed",
#         "service_request": result
#     }

#TDX RC form -> PCR360 as Service Request (DEMO TEST VERSION)
@app.post("/tdx/webhook")
def account_creation_request(payload: dict):

    ticket = payload["data"]

    #remarks = build_service_request_remarks(ticket)
    remarks = "test"

    result = create_inquiry(
        subject=ticket["Title"],
        message=remarks,
        email=ticket["RequestorEmail"],
        topic=349
    )

    return {
        "status": "processed",
        "inquiry": result
    }

# #test this first
# @app.post("/tdx/webhook/access_request")
# def account_creation_request2(payload: dict):

#     ticket = payload["data"]

#     remarks = build_access_request_remarks(ticket)

#     result = create_inquiry(
#         subject=ticket["Title"],
#         message=remarks,
#         email=ticket["RequestorEmail"],
#         topic=349
#     )

#     return {
#         "status": "processed",
#         "inquiry": result
#     }

@app.post("/tdx/webhook/account_creation_request")
def account_creation_request(payload: dict):

    ticket = payload["data"]

    print("=" * 50)
    print("PCR Access Request Received")
    print(f"Ticket ID: {ticket['ID']}")
    print(f"Title: {ticket['Title']}")

    remarks = build_access_request_remarks(ticket)

    print("Generated Remarks:")
    print(remarks)

    result = create_inquiry(
        description=ticket["Title"],
        remarks=remarks
    )

    print("PCR Response:")
    print(result)

    print("=" * 50)

    return {
        "status": "processed",
        "service_request": result
    }

@app.post("/ringcentral/dayoff")
async def dayoff_webhook(request: Request):
    body = await request.body()

    body_str = body.decode("utf-8")
    body_str = body_str.replace("\u00A0", " ")

    data = json.loads(body_str)

    service = NurseDayOffService()

    result = service.handle(data)

    return {
        "status": "success",
        "message": result
    }

@app.post("/ringcentral/dnd")
async def webhook(request: Request):

    print("=" * 50)

    body = await request.body()

    body_str = body.decode("utf-8")

    # Remove RingCentral's non-breaking spaces
    body_str = body_str.replace("\u00A0", " ")

    print(body_str)

    data = json.loads(body_str)

    command = data["command"].strip().upper()
    extension_id = data["extensionId"].strip()

    print(f"Command: {command}")
    print(f"Extension ID: {extension_id}")

    if command == "DAYOFF":
        set_dnd(extension_id, True)

        return {
            "status": "success",
            "action": "dnd_enabled"
        }

    elif command == "BACK":
        set_dnd(extension_id, False)

        return {
            "status": "success",
            "action": "dnd_disabled"
        }

    return {
        "status": "ignored",
        "command": command
    }

@app.post("/demo/dayoff")
async def demo_dayoff(request: Request):

    body = await request.body()

    body_str = body.decode("utf-8")
    body_str = body_str.replace("\u00A0", " ")

    data = json.loads(body_str)

    command = data["command"].strip().upper()

    platform = get_platform()

    service = NurseDayOffService(platform)

    result = service.handle_extension_command(
        "1017318040",
        command
    )

    return {
        "status": "success",
        "message": result
    }

@app.get("/ticket/{ticket_id}")
def ticket_lookup(ticket_id: int):

    return get_ticket(ticket_id)

@app.post("/process-ticket/{ticket_id}")
def process_ticket(ticket_id: int):

    return process_ringcentral_ticket(ticket_id)

@app.get("/test-fields/{ticket_id}")
def test_fields(ticket_id: int):

    ticket = get_ticket(ticket_id)

    return {
        "location": get_attribute(ticket, "RC Location"),
        "account_type": get_attribute(ticket, "RC Account Type"),
        "handset": get_attribute(ticket, "RC Physical Handset"),
    }