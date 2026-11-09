"""
Build the HTML "remarks" text sent to PCR360 from a TDX ticket.

PCR360 renders remarks as HTML, so each field ends with <br><br>.
"""

from app.clients.tdx import get_attribute


def _line(label: str, value) -> str:
    return f"{label}: {value}<br><br>"


def build_service_request_remarks(ticket: dict) -> str:
    """Remarks for the RingCentral form (used by /process-ticket)."""

    return (
        _line("Requestor", ticket["RequestorName"])
        + _line("Email", ticket["RequestorEmail"])
        + _line("Extension Option", get_attribute(ticket, "RC Ext Options"))
        + _line("Location", get_attribute(ticket, "RC Location"))
        + _line("Address", get_attribute(ticket, "RC Address"))
        + _line("Outbound ID", get_attribute(ticket, "RC Outbound ID"))
        + _line("DASH COA", get_attribute(ticket, "RC DASH COA"))
        + _line("Account Type", get_attribute(ticket, "RC Account Type"))
        + _line("Queue Option", get_attribute(ticket, "RC Queue Options"))
        + _line("Physical Handset", get_attribute(ticket, "RC Physical Handset"))
        + _line("Data Port", get_attribute(ticket, "RC Physical Handset Data Port"))
        + _line("TDX Ticket", ticket["WebUiUrl"])
    )


def build_access_request_remarks(ticket: dict) -> str:
    """Remarks for the PCR account access request form (production)."""

    remarks = _line("Access Change", get_attribute(ticket, "PCR Type"))

    users_to_add = get_attribute(ticket, "PCR New Users")
    if users_to_add:
        remarks += _line("Users to Add", users_to_add)

    users_to_remove = get_attribute(ticket, "PCR Remove Users")
    if users_to_remove:
        remarks += _line("Users to Remove", users_to_remove)

    remarks += _line("Billing Account Number", ticket["Description"])

    for attachment in ticket.get("Attachments", []):
        remarks += _line("Attachment", attachment["Name"])

    remarks += _line("Requestor Name", ticket["RequestorName"])
    remarks += _line("Requestor Email", ticket["RequestorEmail"])
    remarks += _line("TDX Ticket ID#", ticket["ID"])

    return remarks


def build_ringcentral_request_remarks(ticket: dict) -> str:
    """Remarks for the RingCentral new request form."""

    def attr(name):
        return get_attribute(ticket, name)

    remarks = _line("Extension Request", attr("RC Ext Options"))

    if attr("RC Exist Ext"):
        remarks += _line("Existing Extension", attr("RC Exist Ext"))

    remarks += _line("Account Type", attr("RC Account Type"))
    remarks += _line("Work Location", attr("RC Location"))

    if attr("RC Address"):
        remarks += _line("Location Details", attr("RC Address"))

    remarks += _line("Outbound Caller ID", attr("RC Outbound ID"))

    if attr("RC Outbound ID Other"):
        remarks += _line("Alternate 4-XXXX Number", attr("RC Outbound ID Other"))

    remarks += _line("Queue Required", attr("RC Queue Options"))

    if attr("RC Queue Options List"):
        remarks += _line("Queue List", attr("RC Queue Options List"))

    remarks += _line("Physical Desk Phone", attr("RC Physical Handset"))

    if attr("RC Physical Handset Data Port"):
        remarks += _line("Data Port", attr("RC Physical Handset Data Port"))

    remarks += _line("DASH COA", attr("RC DASH COA"))
    remarks += _line("Description", ticket["Description"])
    remarks += _line("Requestor Name", ticket["RequestorName"])
    remarks += _line("Requestor Email", ticket["RequestorEmail"])
    remarks += _line("TDX Ticket ID#", ticket["ID"])

    return remarks
