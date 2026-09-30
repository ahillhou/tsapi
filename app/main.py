import os
import threading

from fastapi import FastAPI
from app.tdx import get_ticket
from app.tdx import build_ringcentral_remarks
from app.tdx import get_attribute
from app.pcr import create_service_order
from app.pcr import create_service_request
from app.pcr import add_equipment
from app.poller import poll_tdx
from app.processor import process_ringcentral_ticket


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

@app.on_event("startup")
def startup_event():

    thread = threading.Thread(
        target=poll_tdx,
        daemon=True
    )

    thread.start()

    print("TDX Poller Started")
    
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