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
def build_ringcentral_request_remarks(ticket):

    extension_option = get_attribute(
        ticket,
        "RC Ext Options"
    )

    remarks = (
        f"Extension Request: {extension_option}<br><br>"
    )

    existing_extension = get_attribute(
        ticket,
        "RC Exist Ext"
    )

    if existing_extension:
        remarks += (
            f"Existing Extension: {existing_extension}<br><br>"
        )

    account_type = get_attribute(
        ticket,
        "RC Account Type"
    )

    remarks += (
        f"Account Type: {account_type}<br><br>"
    )

    location = get_attribute(
        ticket,
        "RC Location"
    )

    remarks += (
        f"Work Location: {location}<br><br>"
    )

    location_details = get_attribute(
        ticket,
        "RC Address"
    )

    if location_details:
        remarks += (
            f"Location Details: {location_details}<br><br>"
        )

    outbound_id = get_attribute(
        ticket,
        "RC Outbound ID"
    )

    remarks += (
        f"Outbound Caller ID: {outbound_id}<br><br>"
    )

    outbound_other = get_attribute(
        ticket,
        "RC Outbound ID Other"
    )

    if outbound_other:
        remarks += (
            f"Alternate 4-XXXX Number: {outbound_other}<br><br>"
        )

    queue_option = get_attribute(
        ticket,
        "RC Queue Options"
    )

    remarks += (
        f"Queue Required: {queue_option}<br><br>"
    )

    queue_list = get_attribute(
        ticket,
        "RC Queue Options List"
    )

    if queue_list:
        remarks += (
            f"Queue List: {queue_list}<br><br>"
        )

    handset = get_attribute(
        ticket,
        "RC Physical Handset"
    )

    remarks += (
        f"Physical Desk Phone: {handset}<br><br>"
    )

    data_port = get_attribute(
        ticket,
        "RC Physical Handset Data Port"
    )

    if data_port:
        remarks += (
            f"Data Port: {data_port}<br><br>"
        )

    dash_coa = get_attribute(
        ticket,
        "RC DASH COA"
    )

    remarks += (
        f"DASH COA: {dash_coa}<br><br>"
    )

    remarks += (
        f"Description: {ticket['Description']}<br><br>"
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