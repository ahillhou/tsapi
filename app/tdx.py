import requests
#from dotenv import load_dotenv
import os

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

BASE_URL = "https://utk.teamdynamix.com/sbtdwebapi"

APP_ID = 2278


def authenticate():
    """
    Authenticate with TDX and return request headers.
    """

    auth_response = requests.post(
        f"{BASE_URL}/api/auth",
        json={
            "UserName": USERNAME,
            "Password": PASSWORD
        }
    )

    auth_response.raise_for_status()

    token = auth_response.text

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }


def get_ticket(ticket_id):
    """
    Retrieve a specific ticket by ID.
    """

    headers = authenticate()

    response = requests.get(
        f"{BASE_URL}/api/tickets/{ticket_id}",
        headers=headers
    )

    response.raise_for_status()

    return response.json()


def search_tickets(search_body=None):
    """
    Search for tickets.
    """

    if search_body is None:
        search_body = {}

    headers = authenticate()

    response = requests.post(
        f"{BASE_URL}/api/{APP_ID}/tickets/search",
        headers=headers,
        json=search_body
    )

    response.raise_for_status()

    return response.json()

def get_attribute(ticket, name):

    for attr in ticket["Attributes"]:

        if attr["Name"] == name:
            return attr["ValueText"]

    return None

def build_service_request_remarks(ticket):

    remarks = (
        f"Requestor: {ticket['RequestorName']}<br><br>"
        f"Email: {ticket['RequestorEmail']}<br><br>"
        f"Extension Option: {get_attribute(ticket, 'RC Ext Options')}<br><br>"
        f"Location: {get_attribute(ticket, 'RC Location')}<br><br>"
        f"Address: {get_attribute(ticket, 'RC Address')}<br><br>"
        f"Outbound ID: {get_attribute(ticket, 'RC Outbound ID')}<br><br>"
        f"DASH COA: {get_attribute(ticket, 'RC DASH COA')}<br><br>"
        f"Account Type: {get_attribute(ticket, 'RC Account Type')}<br><br>"
        f"Queue Option: {get_attribute(ticket, 'RC Queue Options')}<br><br>"
        f"Physical Handset: {get_attribute(ticket, 'RC Physical Handset')}<br><br>"
        f"Data Port: {get_attribute(ticket, 'RC Physical Handset Data Port')}"
        f"TDX Ticket: {ticket['WebUiUrl']}<br><br>"
    )

    return remarks

#PRODUCTION
#PCR account access request
def build_access_request_remarks(ticket):

    access_change = get_attribute(
        ticket,
        "PCR Type"
    )

    remarks = (
        f"Access Change: {access_change}<br><br>"
    )

    users_to_add = get_attribute(
        ticket,
        "PCR New Users"
    )

    if users_to_add:
        remarks += (
            f"Users to Add: {users_to_add}<br><br>"
        )

    users_to_remove = get_attribute(
        ticket,
        "PCR Remove Users"
    )

    if users_to_remove:
        remarks += (
            f"Users to Remove: {users_to_remove}<br><br>"
        )

    billing_account = ticket.get("Description")

    remarks += (
        f"Billing Account Number: {ticket['Description']}<br><br>"
    )

    for attachment in ticket.get("Attachments", []):

        remarks += (
            f"Attachment: {attachment['Name']}<br><br>"
        )

    remarks += (
        f"Requestor Name: {ticket['RequestorName']}<br><br>"
    )

    remarks += (
        f"Requestor Email: {ticket['RequestorEmail']}<br><br>"
    )

    remarks += (
        f"TDX Ticket ID#: {ticket['ID']}<br><br>"
    )

    return remarks

def download_attachment(content_uri):

    headers = authenticate()

    response = requests.get(
        f"{BASE_URL}/{content_uri}",
        headers=headers
    )

    response.raise_for_status()

    return response.content

#TEST
#ring central request
def create_ringcentral_request(ticket):

    print("=" * 50)
    print("PROCESSING RINGCENTRAL REQUEST")

    attributes = ticket.get("Attributes", [])

    for attribute in attributes:
        print(attribute)

    return "RingCentral request processed"