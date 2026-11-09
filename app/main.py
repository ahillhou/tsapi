import os
import json

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from app.tdx import get_ticket
from app.tdx import build_service_request_remarks
from app.tdx import build_access_request_remarks
from app.tdx import get_attribute
from app.tdx import download_attachment
from app.tdx import build_ringcentral_request_remarks
from app.pcr import create_service_order
from app.pcr import create_service_request
from app.pcr import create_inquiry
from app.pcr import test_create_inquiry
from app.pcr import add_equipment
from app.pcr import upload_attachment
from app.pcr import lookup_sd
from app.processor import process_ringcentral_ticket
from .ring_test import set_dnd
from app.services.nurse_dayoff_service import NurseDayOffService
from app.integrations.ringcentral.auth import get_platform
from app.integrations.ringcentral.sms import send_sms


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

# #TDX RC form -> PCR360 as Service Request (DEMO TEST VERSION)
# @app.post("/tdx/webhook")
# def account_creation_request(payload: dict):

#     ticket = payload["data"]

#     #remarks = build_service_request_remarks(ticket)
#     remarks = "test"

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

#TDX RC form -> PCR360 as Service Request (DEMO TEST VERSION)
@app.post("/tdx/webhook")
def ringcentral_request(payload: dict):

    ticket = payload["data"]

    #error checking for attachments
    print("=" * 50)
    print("ATTACHMENT COUNT")
    print(len(ticket.get("Attachments", [])))
    print("=" * 50)

    print("=" * 50)
    print("RingCentral Request Received")
    print(f"Ticket ID: {ticket['ID']}")
    print(f"Title: {ticket['Title']}")

    remarks = build_ringcentral_request_remarks(ticket)

    print("Generated Remarks:")
    print(remarks)

    result = create_service_request(
        description="RingCentral New Request",
        remarks=remarks
    )

    sd_number = result["servicedesk"]
    print("PCR SR NUMBER:", sd_number)

    for attachment in ticket.get("Attachments", []):

        print("Processing Attachment:", attachment["Name"])

        file_content = download_attachment(
            attachment["ContentUri"]
        )

        upload_result = upload_attachment(
            sd_number=sd_number,
            filename=attachment["Name"],
            file_content=file_content
        )

        print(upload_result)

    print(result)

    print("=" * 50)

    return {
        "status": "processed",
        "service_request": result
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

@app.post("/tdx/webhook/access_request")
def account_creation_request(payload: dict):

    # print("=" * 80)
    # print("RAW PAYLOAD")
    # print("=" * 80)
    # print(json.dumps(payload, indent=4))
    # print("=" * 80)

    # print("ATTACHMENT PAYLOAD:")
    # print(json.dumps(payload, indent=4)[:2000])

    ticket = payload["data"]

    print("=" * 50)
    print("PCR Access Request Received")
    print(f"Ticket ID: {ticket['ID']}")
    print(f"Title: {ticket['Title']}")

    remarks = build_access_request_remarks(ticket)

    print("Generated Remarks:")
    print(remarks)

    access_change = get_attribute(
        ticket,
        "PCR Type"
    )

    result = create_inquiry(
        subject = f"{access_change} PCR Access",
        message=remarks,
        #email=ticket["RequestorEmail"],
        email = "ahillhou@utk.edu",
        #topic=349,
        topic=482,
    )

    print(result)

    #get service desk id#
    # iq_number = result["servicedesk"]

    # lookup_sd(iq_number)

    #download and upload attatchments
    # for attachment in ticket.get(
    #     "Attachments",
    #     []
    # ):

    #     file_content = download_attachment(
    #         attachment["ContentUri"]
    #     )

    #     upload_attachment(
    #         sd_number=iq_number,
    #         filename=attachment["Name"],
    #         file_content=file_content
    #     )
    
    print("PCR Response:")
    print(result["servicedesk"])

    print("=" * 50)

    return {
        "status": "processed",
        "service_request": result
    }

@app.post("/tdx/webhook/test_access_request")
def test_account_creation_request(payload: dict):

    # print("=" * 80)
    # print("RAW PAYLOAD")
    # print("=" * 80)
    # print(json.dumps(payload, indent=4))
    # print("=" * 80)

    # print("ATTACHMENT PAYLOAD:")
    # print(json.dumps(payload, indent=4)[:2000])

    ticket = payload["data"]

    print("=" * 50)
    print("PCR Access Request Received")
    print(f"Ticket ID: {ticket['ID']}")
    print(f"Title: {ticket['Title']}")

    remarks = build_access_request_remarks(ticket)

    print("Generated Remarks:")
    print(remarks)

    access_change = get_attribute(
        ticket,
        "PCR Type"
    )

    result = test_create_inquiry(
        subject = f"{access_change} PCR Access",
        message=remarks,
        email=ticket["RequestorEmail"],
        topic=349,
        #topic=482,
    )

    print(result)

    iq_number = result["servicedesk"]
    print("IQNUMBER:")
    print(iq_number)

    sd_recid = lookup_sd(iq_number)

    for attachment in ticket.get(
        "Attachments",
        []
    ):

        file_content = download_attachment(
            attachment["ContentUri"]
        )

        upload_attachment(
            sd_number=sd_recid,
            filename=attachment["Name"],
            file_content=file_content
        )
    
    print("PCR Response:")
    print(result["servicedesk"])

    print("=" * 50)

    return {
        "status": "processed",
        "service_request": result
    }

#test for attachments
@app.post("/test_attachment")
def test_attachment():

    with open("test.txt", "rb") as f:
        file_content = f.read()

    return upload_attachment(
        sd_number="IQ00000011",
        filename="test.txt",
        file_content=file_content
    )

@app.post("/ringcentral/dayoff")
async def dayoff_webhook(request: Request):
    body = await request.body()

    body_str = body.decode("utf-8")
    body_str = body_str.replace("\u00A0", " ")

    data = json.loads(body_str)

    service = NurseDayOffService()

    result = await run_in_threadpool(service.handle, data)

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
        await run_in_threadpool(set_dnd, extension_id, True)

        return {
            "status": "success",
            "action": "dnd_enabled"
        }

    elif command == "BACK":
        await run_in_threadpool(set_dnd, extension_id, False)

        return {
            "status": "success",
            "action": "dnd_disabled"
        }

    return {
        "status": "ignored",
        "command": command
    }

# @app.post("/demo/dayoff")
# async def demo_dayoff(request: Request):

#     body = await request.body()

#     body_str = body.decode("utf-8")
#     body_str = body_str.replace("\u00A0", " ")

#     data = json.loads(body_str)

#     command = data["command"].strip().upper()

#     platform = get_platform()

#     service = NurseDayOffService(platform)

#     result = service.handle_extension_command(
#         "1017318040",
#         command
#     )

#     return {
#         "status": "success",
#         "message": result
#     }

@app.post("/demo/dayoff")
async def demo_dayoff(request: Request):

    #data = await request.json()

    body = await request.body()

    body_str = body.decode("utf-8")
    body_str = body_str.replace("\u00A0", " ")

    print(body_str)

    data = json.loads(body_str)

    data = {
        k: v.strip() if isinstance(v, str) else v
        for k, v in data.items()
    }

    print("COMMAND:", data["command"])
    print("EXTENSION:", data["extensionId"])
    print("SENDER:", data["sender"])

    # RingCentral SDK calls are blocking; run them in a worker thread so
    # they don't stall other requests (e.g. TDX webhooks) on the event loop.
    platform = await run_in_threadpool(get_platform)

    service = NurseDayOffService(
        platform
    )

    result = await run_in_threadpool(
        service.handle,
        {
            "id": data["extensionId"]
        },
        data["command"]
    )

    print("RESULT:", result)

    try:
        await run_in_threadpool(
            send_sms,
            platform,
            data["sender"],
            result
        )
    except Exception as e:
        print("SMS failed:")
        print(e)

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