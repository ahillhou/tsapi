from fastapi import FastAPI
from app.tdx import get_ticket
from app.pcr import create_service_order
from app.pcr import add_equipment

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