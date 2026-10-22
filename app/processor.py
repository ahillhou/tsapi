from app.tdx import get_ticket
from app.tdx import build_service_request_remarks
from app.pcr import create_service_request


def process_ringcentral_ticket(ticket_id):

    ticket = get_ticket(ticket_id)

    remarks = build_service_request_remarks(ticket)

    return create_service_request(
        description=ticket["Title"],
        remarks=remarks
    )