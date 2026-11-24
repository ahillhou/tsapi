"""
PCR360 API client.

Each function talks to a fixed PCR360 instance (test or prod). That is
deliberate and matches what is deployed today; see the docstrings.
"""

import base64
import json
import logging

import requests

from app.core.config import HTTP_TIMEOUT, get_settings

logger = logging.getLogger(__name__)

HEADERS = {
    "Content-Type": "application/json",
    "Pcr-Html-Encoded": "TRUE",
}

# See upload_attachment().
ATTACHMENT_HEADERS = {"Content-Type": "application/json"}

VVX_150 = 889


def _servicedesk_url(host: str, api_key: str | None) -> str:
    return f"{host}/api/{api_key}/servicedesk.json"


def _test_url() -> str:
    s = get_settings()
    return _servicedesk_url(s.pcr_test_host, s.pcr_test_api_key)


def _prod_url() -> str:
    s = get_settings()
    return _servicedesk_url(s.pcr_prod_host, s.pcr_prod_api_key)


def _legacy_test_url() -> str:
    """Test instance using PCR_API_KEY (only used by add_equipment)."""
    s = get_settings()
    return _servicedesk_url(s.pcr_test_host, s.pcr_api_key)


def encode_file(filename: str, file_content: bytes) -> dict:
    """One entry of PCR360's `files` list."""

    return {
        "filename": filename,
        "data": base64.b64encode(file_content).decode("utf-8"),
    }


def _short(response: requests.Response, limit: int = 300) -> str:
    """Response text for logs. PCR360 errors can be a whole HTML page."""

    text = " ".join(response.text.split())
    return text if len(text) <= limit else text[:limit] + "..."


class PCR360Error(Exception):
    """A failed PCR360 call. Never includes the URL (it holds the API key)."""


def _post(url: str, payload: dict, headers: dict = HEADERS) -> requests.Response:
    try:
        return requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    except requests.RequestException as exc:
        # requests puts the URL (and so the API key) in its messages.
        raise PCR360Error(f"PCR360 {payload.get('type')} request failed: {type(exc).__name__}") from None


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code >= 400:
        raise PCR360Error(f"PCR360 returned HTTP {response.status_code}: {_short(response, 120)}")


def create_service_order(
    description: str,
    remarks: str,
    sdc: int | None = None,
    files: list[dict] | None = None,
) -> dict:
    """
    Create a Service Order in PCR360 **test**.

    `sdc` is the Service Desk Classification RECID, which picks the
    workflow. It is only sent when given. PCR360's docs list `sdc` for
    IN/WO/IQ but not SO, so confirm on test that an SO accepts it.

    `files` (from encode_file) are attached as part of the create call,
    which the docs allow for any Service Desk item.
    """

    payload = {
        "type": "SO",
        "csr": 1,
        "description": description,
        "remarks": remarks,
    }

    if sdc is not None:
        payload["sdc"] = sdc

    if files:
        payload["files"] = files

    response = _post(_test_url(), payload)

    logger.info(
        "PCR360 SO status %s (%d files): %s",
        response.status_code,
        len(files or []),
        _short(response),
    )

    _raise_for_status(response)
    return response.json()


def create_service_request(description: str, remarks: str) -> dict:
    """
    Create a Service Request in PCR360 **test**.

    Not in the wiki's list of write types, but type=SR works on test
    (SR-000073..76, SR-000096). PCR360 ignores `sdc` on an SR (it created
    SR-000096 with no workflow, 2026-11-19), so an SDC's workflow is copied
    on afterwards with sdc_workflow_steps() + add_workflow_step().
    """

    payload = {
        "type": "SR",
        "csr": 1,
        "description": description,
        "remarks": remarks,
    }

    response = _post(_test_url(), payload)

    logger.info("PCR360 SR status %s: %s", response.status_code, _short(response))

    _raise_for_status(response)
    return response.json()


def _sql_url(host: str, api_key: str | None) -> str:
    return f"{host}/api/{api_key}/sql.json"


SDC_STEPS_SQL = (
    "SELECT SEQUENCE, WORKGROUPS_RECID, WORKER_CONTACTS_RECID "
    "FROM SDC_WORKFLOW WHERE SDC_RECID = {sdc} ORDER BY SEQUENCE"
)


def _int_or_none(value) -> int | None:
    return int(value) if value not in (None, "") else None


def _sql(host: str, api_key: str | None, sql: str, limit: int, page: int = 1) -> dict:
    """One page of a read-only query. Raises PCR360Error on any failure."""

    payload = {"sql": sql, "limit": limit}
    if page != 1:
        payload["page"] = page

    response = _post(_sql_url(host, api_key), payload)

    logger.info("PCR360 SQL page %s status %s: %s", page, response.status_code, _short(response, 120))

    _raise_for_status(response)
    result = response.json()

    if result.get("status") != "success":
        raise PCR360Error(f"PCR360 query failed: {result.get('message')}")

    return result


SQL_PAGE_SIZE = 5000


def _sql_all(host: str, api_key: str | None, sql: str) -> list[dict]:
    """Every row of a read-only query, page by page."""

    rows: list[dict] = []
    page = 1

    while True:
        result = _sql(host, api_key, sql, SQL_PAGE_SIZE, page)
        batch = result.get("results") or []
        rows += batch

        if len(batch) < SQL_PAGE_SIZE or len(rows) >= int(result.get("total_count") or 0):
            return rows

        page += 1


# Each phone service is in at most one service pool (Admin > System Tables >
# Service Pools; checked on production 2026-11-19: 25,873 numbers, none in two).
PHONE_NUMBERS_SQL = (
    "SELECT S.SERVICE_ID, L.CODE AS STATUS, PO.POOL_NAME AS POOL FROM SERVICES S "
    "JOIN PHONE_SERVICES P ON P.SERVICES_RECID = S.RECID "
    "JOIN LISTS L ON L.RECID = S.SERVICE_STATUS_LISTS_RECID "
    "LEFT JOIN SERVICES_POOLS SP ON SP.SERVICES_RECID = S.RECID "
    "LEFT JOIN POOLS PO ON PO.RECID = SP.POOLS_RECID"
)


def prod_phone_numbers() -> list[dict]:
    """
    Every phone service in PCR360 **production** with its status code and
    service pool: [{"SERVICE_ID": "8659740485", "STATUS": "AVAILABLE",
    "POOL": "ADMIN"}, ...]. POOL is None for a number in no pool. Statuses
    seen: AVAILABLE, ACTIVE, INACTIVE, ORDER_PENDING.

    Read-only (sql.json); the production key needs SQL read.
    """

    s = get_settings()
    return _sql_all(s.pcr_prod_host, s.pcr_prod_api_key, PHONE_NUMBERS_SQL)


# PCR access requests (TDX form -> production Inquiry, subject "<change> PCR
# Access") that staff finished: status VOID and the "Complete" checkbox
# (UDF COMPLETE_REQUEST) ticked. UDF values live in USER_DEFINED_FIELDS_VALS,
# keyed by TABLE_NAME 'SERVICE_DESK_INQUIRY' and the SERVICE_DESK RECID.
# (The documented V_UDF view fails on production with a collation error.)
# {since} is a 'YYYY-MM-DD HH:MM:SS' string the app builds itself.
COMPLETED_ACCESS_REQUESTS_SQL = (
    "SELECT SD.SD_NUMBER, SD.VOID_DATE, I.MESSAGE FROM SERVICE_DESK_INQUIRY I "
    "JOIN SERVICE_DESK SD ON SD.RECID = I.SERVICE_DESK_RECID "
    "JOIN LISTS L ON L.RECID = SD.SD_STATUS_LISTS_RECID "
    "JOIN USER_DEFINED_FIELDS_VALS V ON V.TABLE_NAME = 'SERVICE_DESK_INQUIRY' AND V.TABLE_RECID = SD.RECID "
    "JOIN USER_DEFINED_FIELDS U ON U.RECID = V.UDF_RECID AND U.IDENTIFIER = 'COMPLETE_REQUEST' "
    "WHERE I.SUBJECT LIKE '%PCR Access' AND L.CODE = 'VOID' AND V.BOOL_VALUE = 1 "
    "AND SD.VOID_DATE >= '{since}' ORDER BY SD.RECID"
)


def prod_completed_access_requests(since: str) -> list[dict]:
    """
    Access request inquiries in PCR360 **production** voided since `since`
    with "Complete" ticked: [{"SD_NUMBER", "VOID_DATE", "MESSAGE"}, ...].
    MESSAGE is the inquiry text, which holds "TDX Ticket ID#: <id>".

    Read-only (sql.json).
    """

    s = get_settings()
    sql = COMPLETED_ACCESS_REQUESTS_SQL.format(since=since)
    return _sql_all(s.pcr_prod_host, s.pcr_prod_api_key, sql)


def sdc_workflow_steps(sdc: int) -> list[dict]:
    """
    The workflow steps defined on an SDC in PCR360 **test**, in order:
    [{"sequence": 100, "workgroup": 9, "worker": None}, ...].

    Read with the SQL endpoint (the API key needs SQL read). Raises
    PCR360Error if the query fails.
    """

    s = get_settings()
    result = _sql(s.pcr_test_host, s.pcr_test_api_key, SDC_STEPS_SQL.format(sdc=int(sdc)), 100)

    logger.info("PCR360 SDC %s workflow: %d steps", sdc, len(result.get("results") or []))

    return [
        {
            "sequence": int(row["SEQUENCE"]),
            "workgroup": int(row["WORKGROUPS_RECID"]),
            "worker": _int_or_none(row.get("WORKER_CONTACTS_RECID")),
        }
        for row in result.get("results") or []
    ]


def add_workflow_step(
    sd_number: str, sequence: int, workgroup: int, worker: int | None = None
) -> dict:
    """
    Add a Pending workflow step to a record in PCR360 **test**. Never raises.

    The wiki lists sda_recid/sda_number (an action) as required, but a step
    on the record itself works: SR-000096 got one with no action
    (2026-11-19), the same shape an inquiry's SDC produces.
    """

    payload = {
        "type": "WORKFLOW",
        "sd_number": sd_number,
        "sequence": sequence,
        "workgroup": workgroup,
        "billable": 0,
        "status": "PENDING",
    }

    if worker is not None:
        payload["worker"] = worker

    return _soft_post(_test_url(), payload)


def create_inquiry(subject: str, message: str, email: str, topic: int) -> dict:
    """
    Create an Inquiry in PCR360 **production**.

    Returns {"status": "error", "response": ...} instead of raising when
    PCR360 rejects the request.
    """

    payload = {
        "type": "IQ",
        "email": email,
        "subject": subject,
        "message": message,
        "topic": topic,
        "sdc": 6,
        "csr": 566,
    }

    logger.info("Creating PCR360 inquiry for %s", email)
    logger.info("Payload: %s", json.dumps(payload, indent=2))

    response = _post(_prod_url(), payload)

    logger.info("PCR360 status %s: %s", response.status_code, _short(response))

    if response.status_code >= 400:
        return {
            "status": "error",
            "response": response.text,
        }

    return response.json()


def test_create_inquiry(subject: str, message: str, email: str, topic: int) -> dict:
    """Create an Inquiry in PCR360 **test**."""

    payload = {
        "type": "IQ",
        "email": email,
        "subject": subject,
        "message": message,
        "topic": topic,
    }

    response = _post(_test_url(), payload)

    logger.info("PCR360 status %s: %s", response.status_code, _short(response))

    _raise_for_status(response)
    return response.json()


def _project_payload(description: str, remarks: str, csr: int, sdc: int | None) -> dict:
    payload = {
        "type": "PR",
        "csr": csr,
        "description": description,
        "remarks": remarks,
    }

    if sdc is not None:
        payload["sdc"] = sdc

    return payload


# type=PR creates a Project ("PR-000081"). Not in the wiki's list of write
# types; confirmed on PCR360 test 2026-11-16.


def create_test_project(description: str, remarks: str, csr: int, sdc: int | None = None) -> dict:
    """Create a Project in PCR360 **test**. Never raises (see _soft_post)."""

    return _soft_post(_test_url(), _project_payload(description, remarks, csr, sdc))


def create_project(description: str, remarks: str, csr: int, sdc: int | None = None) -> dict:
    """Create a Project in PCR360 **production**. Never raises (see _soft_post)."""

    return _soft_post(_prod_url(), _project_payload(description, remarks, csr, sdc))


def add_equipment(so_number: str) -> dict:
    """Add a VVX-150 to a Service Order in PCR360 **test**. Debug use only."""

    payload = {
        "type": "EQUIPMENT",
        "sd_number": so_number,
        "qty": 1,
        "eqp_catalog": VVX_150,
    }

    response = _post(_legacy_test_url(), payload)

    logger.info("Equipment status %s: %s", response.status_code, _short(response))

    _raise_for_status(response)
    return response.json()


def _soft_post(url: str, payload: dict, headers: dict = HEADERS) -> dict:
    """
    POST that never raises: returns {"status": "error", "response": ...} on
    a network error, an HTTP error, a non-JSON body or a "failure" body.
    """

    try:
        response = _post(url, payload, headers=headers)
    except PCR360Error as exc:
        return {"status": "error", "response": str(exc)}

    logger.info("PCR360 %s status %s: %s", payload["type"], response.status_code, _short(response))

    if response.status_code >= 400 or not response.text.strip().startswith("{"):
        return {"status": "error", "response": _short(response)}

    result = response.json()

    if result.get("status") == "failure":
        return {"status": "error", "response": result.get("message") or _short(response)}

    return result


def _attachment_payload(target: dict, filename: str, file_content: bytes) -> dict:
    logger.info("Uploading attachment %s (%d bytes) to %s", filename, len(file_content), target)

    return {
        "type": "ATTACHMENT",
        **target,
        "files": [encode_file(filename, file_content)],
    }


# Attachments are sent WITHOUT Pcr-Html-Encoded: that header makes PCR360
# HTML-decode every parameter, and with the nested `files` list it answered
# HTTP 500 (2026-11-10). Nothing in the payload is HTML-encoded, so it isn't
# needed. With the header removed, uploads to an SO work.


def sd_target(servicedesk) -> dict:
    """
    How to point at a record from the `servicedesk` value a create returned.

    Creates return the record number ("SO-000079", "IQ00000127"), which goes
    in sd_number. The wiki says an IQ create returns a RECID, but PCR360
    returned "IQ00000127" (2026-11-10); a bare number is still treated as a
    RECID just in case.
    """

    if isinstance(servicedesk, int) or str(servicedesk).isdigit():
        return {"sd_recid": int(servicedesk)}

    return {"sd_number": str(servicedesk)}


def upload_attachment(
    filename: str,
    file_content: bytes,
    *,
    sd_number: str | None = None,
    sd_recid: int | None = None,
) -> dict:
    """Attach a file to a Service Desk record in PCR360 **test**. Never raises."""

    target = {"sd_recid": sd_recid} if sd_recid is not None else {"sd_number": sd_number}

    return _soft_post(
        _test_url(),
        _attachment_payload(target, filename, file_content),
        headers=ATTACHMENT_HEADERS,
    )


def upload_prod_attachment(
    filename: str,
    file_content: bytes,
    *,
    sd_number: str | None = None,
    sd_recid: int | None = None,
) -> dict:
    """Attach a file to a record in PCR360 **production**. Never raises."""

    target = {"sd_recid": sd_recid} if sd_recid is not None else {"sd_number": sd_number}

    return _soft_post(
        _prod_url(),
        _attachment_payload(target, filename, file_content),
        headers=ATTACHMENT_HEADERS,
    )


def _remark_payload(remarks: str, sd_number: str | None, sd_recid: int | None) -> dict:
    # The wiki documents only sd_recid for REMARKS; sd_number is what we
    # have for records we create (see sd_target).
    target = {"sd_recid": sd_recid} if sd_recid is not None else {"sd_number": sd_number}
    return {"type": "REMARKS", **target, "remarks": remarks}


def add_remark(remarks: str, *, sd_number: str | None = None, sd_recid: int | None = None) -> dict:
    """Add a remark to a record in PCR360 **test**. Never raises."""

    return _soft_post(_test_url(), _remark_payload(remarks, sd_number, sd_recid))


def add_prod_remark(
    remarks: str, *, sd_number: str | None = None, sd_recid: int | None = None
) -> dict:
    """Add a remark to a record in PCR360 **production**. Never raises."""

    return _soft_post(_prod_url(), _remark_payload(remarks, sd_number, sd_recid))
