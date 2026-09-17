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