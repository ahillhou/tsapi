import requests
#from dotenv import load_dotenv
import os
from app.tdx import build_ringcentral_remarks

PCR_API_KEY = os.getenv("PCR_API_KEY")

URL = (
    f"https://pcr360-test.utk.pcr-360.com/"
    f"api/{PCR_API_KEY}/servicedesk.json"
)

HEADERS = {
    "Content-Type": "application/json",
    "Pcr-Html-Encoded": "TRUE"
}

VVX_150 = 889

# def create_service_order():

#     payload = {
#         "type": "SO",
#         "csr": 1,
#         "description": "New Voice Request",
#         "remarks": "Test Order"
#     }

#     response = requests.post(
#         URL,
#         headers=HEADERS,
#         json=payload
#     )

#     response.raise_for_status()

#     return response.json()

def create_service_order():


    remarks = (
        "Employee Name: John Smith<br><br>"
        "Employee NetID: jsmith27<br><br>"
        "Phone Number: (865) 555-1234<br><br>"
        "Date When Needed: 1/23/27<br><br>"
        "Account Number: 8934563<br><br>"
        "Software Only Account: No<br><br>"
        "Phone Model Requested: VVX-150"
    )

    payload = {
        "type": "SO",
        "csr": 1,
        "description": "New Voice Request",
        "remarks": remarks
    }

    response = requests.post(
        URL,
        headers=HEADERS,
        json=payload
    )

    response.raise_for_status()

    data = response.json()

    return data["servicedesk"]

def create_service_request(description, remarks):

    payload = {
        "type": "SR",
        "csr": 1,
        "description": description,
        "remarks": remarks
    }

    response = requests.post(
        URL,
        headers=HEADERS,
        json=payload
    )

    response.raise_for_status()

    return response.json()

def build_new_account_remarks(ticket):

    remarks = ""

    for attr in ticket.get("Attributes", []):

        remarks += (
            f"{attr['Name']}: "
            f"{attr['ValueText']}<br><br>"
        )

    return remarks

def add_equipment(so_number):

    payload = {
        "type": "EQUIPMENT",
        "sd_number": so_number,
        "qty": 1,
        "eqp_catalog": VVX_150
    }

    response = requests.post(
        URL,
        headers=HEADERS,
        json=payload
    )

    print("Equipment Status:", response.status_code)

    print("Equipment Response:", response.text)

    response.raise_for_status()

    return response.json()