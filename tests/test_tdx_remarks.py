"""
Exact remarks text sent to PCR360. These strings match what the code
produced before the restructure; change them only on purpose.
"""

from app.services.tdx_remarks import (
    build_access_request_remarks,
    build_ringcentral_request_remarks,
    build_service_request_remarks,
)


def test_access_request_remarks(ticket):
    assert build_access_request_remarks(ticket) == (
        "Access Change: Add<br><br>"
        "Users to Add: a, b<br><br>"
        "Billing Account Number: ACCT-123<br><br>"
        "Attachment: a.pdf<br><br>"
        "Attachment: b.png<br><br>"
        "Requestor Name: Pat Doe<br><br>"
        "Requestor Email: pat@example.edu<br><br>"
        "TDX Ticket ID#: 777<br><br>"
    )


def test_access_request_remarks_with_removals_and_no_attachments(ticket):
    ticket["Attributes"] = [
        {"Name": "PCR Type", "ValueText": "Remove"},
        {"Name": "PCR Remove Users", "ValueText": "c"},
    ]
    ticket["Attachments"] = []

    assert build_access_request_remarks(ticket) == (
        "Access Change: Remove<br><br>"
        "Users to Remove: c<br><br>"
        "Billing Account Number: ACCT-123<br><br>"
        "Requestor Name: Pat Doe<br><br>"
        "Requestor Email: pat@example.edu<br><br>"
        "TDX Ticket ID#: 777<br><br>"
    )


def test_ringcentral_request_remarks(ticket):
    assert build_ringcentral_request_remarks(ticket) == (
        "Extension Request: New<br><br>"
        "Existing Extension: 4-1234<br><br>"
        "Account Type: Standard<br><br>"
        "Work Location: Campus<br><br>"
        "Outbound Caller ID: Main<br><br>"
        "Queue Required: Yes<br><br>"
        "Queue List: Q1<br><br>"
        "Physical Desk Phone: Yes<br><br>"
        "Data Port: P12<br><br>"
        "DASH COA: COA1<br><br>"
        "Description: ACCT-123<br><br>"
        "Requestor Name: Pat Doe<br><br>"
        "Requestor Email: pat@example.edu<br><br>"
        "TDX Ticket ID#: 777<br><br>"
    )


def test_ringcentral_request_remarks_skips_empty_optional_fields(ticket):
    optional = {
        "RC Exist Ext",
        "RC Address",
        "RC Outbound ID Other",
        "RC Queue Options List",
        "RC Physical Handset Data Port",
    }
    ticket["Attributes"] = [a for a in ticket["Attributes"] if a["Name"] not in optional]

    remarks = build_ringcentral_request_remarks(ticket)

    for label in ("Existing Extension", "Location Details", "Alternate", "Queue List", "Data Port"):
        assert label not in remarks


def test_service_request_remarks(ticket):
    assert build_service_request_remarks(ticket) == (
        "Requestor: Pat Doe<br><br>"
        "Email: pat@example.edu<br><br>"
        "Extension Option: New<br><br>"
        "Location: Campus<br><br>"
        "Address: None<br><br>"
        "Outbound ID: Main<br><br>"
        "DASH COA: COA1<br><br>"
        "Account Type: Standard<br><br>"
        "Queue Option: Yes<br><br>"
        "Physical Handset: Yes<br><br>"
        "Data Port: P12<br><br>"
        "TDX Ticket: https://tdx/ticket/777<br><br>"
    )
