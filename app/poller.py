import time

from app.tdx import search_tickets
from app.processor import process_ringcentral_ticket

RINGCENTRAL_FORM_ID = 64352

processed_tickets = set()


def poll_tdx():

    while True:

        try:
            print("Checking for RingCentral tickets...")

            tickets = search_tickets()

            for ticket in tickets:

                ticket_id = ticket["ID"]

                if ticket_id in processed_tickets:
                    continue

                if ticket.get("FormID") != RINGCENTRAL_FORM_ID:
                    continue

                print(f"Processing ticket {ticket_id}")

                process_ringcentral_ticket(ticket_id)
                #print(f"Would process ticket {ticket_id}")

                processed_tickets.add(ticket_id)

        except Exception as e:

            print(f"Poller error: {e}")

        time.sleep(300)