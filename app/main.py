import os
import json
#import threading

from fastapi import FastAPI, Request
from app.tdx import get_ticket
from app.tdx import build_ringcentral_remarks
from app.tdx import get_attribute
from app.pcr import create_service_order
from app.pcr import create_service_request
from app.pcr import add_equipment
from app.pcr import build_new_account_remarks
#from app.poller import poll_tdx
from app.processor import process_ringcentral_ticket
from .ring_test import set_dnd


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

@app.post("/tdx/webhook")
def tdx_webhook(payload: dict):

    print("Webhook received")
    print(payload)

    return {
        "status": "received"
    }

@app.post("/tdx_pcr/service_request/new_account")
def new_account_request(payload: dict):

    remarks = build_new_account_remarks(payload)

    result = create_service_request(
        description=payload["Title"],
        remarks=remarks
    )

    return {
        "status": "processed",
        "service_request": result
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