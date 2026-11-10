# PCR360 REST API: developer reference (as used by this project)

Condensed from the PCR360 2025.2 wiki, paraphrased. Anything the docs did not confirm is marked "(unverified)".
Client code: `app/clients/pcr360.py`.

## 1. Auth, URL format, headers

Sources:
- https://wiki360.pcr.com/pcr360-wiki/2025.2/api
- https://wiki360.pcr.com/pcr360-wiki/2025.2/api-authentication-permissions

- URL shape: `https://<host>/api/<API_KEY>/<request-type>.<output>`, e.g. `.../api/KEY/servicedesk.json`. Output may be `json`, `php` (serialized) or `xml`. Extra params can go in a query string (GET).
- Our hosts: `pcr360-test.utk.pcr-360.com` (test) and `pcr360.utk.pcr-360.com` (prod). Keys are issued by a PCR360 admin (Admin > API > API Keys). Each key carries permission sets (Services, Equipment, Service Desk, SNMP...) with read/write flags and an expiry date. A key outside its permission or past expiry should be rejected (401/403).
- Anonymous mode (what we use): the key in the URL path is the only credential. Token mode exists (`login.json` with `PCR-AUTH-USERNAME`/`PCR-AUTH-PASSWORD` headers, then `PCR-AUTH-TOKEN` on later calls, `logout.json` to end). We do not use it.
- Because the key is in the URL, never log full URLs (our code logs only payloads/responses; keep it that way).
- Headers:
  - `Content-Type: application/json` makes the API read the POST body as JSON. Without it, params are expected as form/query style.
  - `Pcr-Html-Encoded: TRUE` tells PCR360 to decode HTML-encoded special characters in each parameter value (e.g. `&amp;`, `&lt;br&gt;`). Only set it if values are actually encoded (unverified: whether raw `<br>` in `remarks` renders as HTML either way; our SO sample uses literal `<br>`).
  - `Pcr-Debug-Api: true` adds a debug block echoing the received params. Useful for troubleshooting.
- POST ignores query-string params; everything goes in the body. Field names are case-insensitive; responses use lowercase.
- Paging params (`limit` default 20, `page` default 1) apply to reads.
- Create vs update: no `recid` creates, with `recid` updates.
- The docs mark reading via the per-type endpoints (servicedesk, services, equipment...) as deprecated in favour of the `sql` endpoint. Writes via `servicedesk.json` are not marked deprecated.

## 2. Writing service desk records (POST `servicedesk.json`)

Source: https://wiki360.pcr.com/pcr360-wiki/2025.2/service-desk-api-endpoint

General: JSON body with a `type` field. Lookup values (`csr`, `sdc`, `topic`, `eqp_catalog`) are numeric RECIDs obtained from `GET servicedesk.json?LIST=<LISTTYPE>` (CSRS, EQP_CATALOG, SDTYPES, ...), or for topics the SD_INQTOPICS list.

Success response (write):
```json
{ "status": "success", "page": 1, "count": 1, "total_count": 0, "servicedesk": "SO20160600145" }
```
`servicedesk` holds the new SD number (e.g. `SO...`) or, for child records (remarks etc.), the new RECID. Failure:
```json
{ "status": "failure", "message": "..." }
```
Note HTTP status may still be 200 for a "failure" body (unverified). Check `status` in the body, not only the HTTP code.

### SO (Service Order) - used by `create_service_order` (RingCentral Request form via `/tdx/webhook`, PCR360 test)
- Required: `type=SO`, `csr` (RECID of the customer service rep).
- We also send `sdc` (Service Desk Classification, which picks the workflow) once `DESIGN_SDC`/`DEFAULT_SDC` are set in `app/services/ringcentral_request.py`. The 2025.2 docs list `sdc` only for IN/WO/IQ, so whether SO honours it is (unverified) until tested on PCR360 test.
- Useful optional: `description`, `remarks`, `due_date`, `source`, `urgency`, `requestor`, `owner` + `owner_type` (`contact` or `department`), `assoc_proj`, `udf_*` fields.
- `status` may be set to `complete` or `finalize`; finalizing needs `finalized_date` (mm/dd/yyyy) and bills from that date. Completing needs `owner`. Do not set these casually.

### SR (Service Request) - used by `create_service_request`
- NOT documented as a write type on the 2025.2 page. The page's examples only list SO, IN, ES (an error message lists "valid options are: SO, IN, ES") plus WO. "Service Request" appears only as an SD type name in a UDF example. Whether `type=SR` works depends on the instance's SDTYPES list (unverified). Fields we send: `csr`, `description`, `remarks`.

### IQ (Inquiry) - used by `create_inquiry` / `test_create_inquiry`
- Create requires: `subject`, `message`, `topic` (RECID from the SD_INQTOPICS list), `email` (unless token auth supplies the user).
- `sdc` = service delivery category/class RECID (we send 6 in prod). Documented only in the IN row as an optional field and as "cannot be updated" on IQ; exact meaning (unverified).
- `csr` for IQ is not listed in the docs for IQ (it is for SO/IN/ES/WO); we send 566 in prod (unverified that it is honoured).
- Update: pass `recid`; `subject`, `email`, `sdc` cannot be changed after creation.
- Note the test inquiry in our code omits `sdc` and `csr`; prod includes them, so the two paths are not equivalent.

### ATTACHMENT - used by `upload_attachment`
- Required: `type=ATTACHMENT`, `files`, and `sd_recid` OR `sd_number` (one of them, not both).
- `sd_number` is the human-readable string like `SO201301080`; `sd_recid` is the internal numeric id.
- Optional: `sda_recid`/`sda_number` to attach to an action rather than the parent record.
- `files`: array of `{ "filename": "x.pdf", "data": "<base64>" }`. Matches our payload.
- Maximum size / allowed extensions: not documented (unverified).

### EQUIPMENT - used by `add_equipment`
- Required: `type=EQUIPMENT`, `qty`, `sd_recid` or `sd_number`.
- `eqp_catalog` (RECID from the EQP_CATALOG list) is required unless the item is cabling or asset equipment (those use `equipment`, `equipment_id` / `asset_tag`).
- Optional: `to_location`, `from_location`, `billable` (1/0), `override_gla`, `expense_type`, `sda_*`.
- Our `VVX_150 = 889` is a catalog RECID, which is instance-specific (test vs prod may differ; unverified).

### Other types in the docs (not used here)
IN (incident: needs `csr`, `prob_code`, `owner`, `owner_type`), ES (estimate), EST_CHARGES / EST_LABOR / EST_EQP, WO (work order), LABOR, GLA, REMARKS, UDFS, WORKFLOW, CHARGES. Also `servicedesk` actions endpoint (`/service-desk-action-api-endpoint`).

## 3. Looking up records

Source: https://wiki360.pcr.com/pcr360-wiki/2025.2/service-desk-api-endpoint

- Documented read form: `GET servicedesk.TYPE.json` where TYPE is `SO` or `IN` (only these are listed), with `LIMIT`/`PAGE`. Searchable fields include `SD_NUMBER`, `SD_TYPE`, `DESCRIPTION`, `OWNER`, `CSR`, `REQUESTOR`, `status`, `DUE_DATE`; the exact filter syntax is not documented.
- `SEARCH=<value>` is documented only for `?LIST=<type>` lookups (partial matching on searchable lists like CONTACTS, EQP_CATALOG). Using `SEARCH=` on plain `servicedesk.json` as our `lookup_sd` does is undocumented (unverified); it may not filter on SD number as intended.
- Read response:
  ```json
  { "status": "success", "page": 1, "count": 1, "total_count": 1,
    "servicedesk": { "item": [ { "sd_number": "...", "recid": "...", ... } ] } }
  ```
  Child collections (remarks, attachments, equipment, ...) are nested lists. Exact casing/nesting of `item` (list vs object) (unverified).
- RECID vs number: each record has an internal numeric `recid` and a string SD number (`SO...`, `IN...`, `IQ...`). Write endpoints accept either as `sd_recid` or `sd_number`. The number is what the create response returns in `servicedesk`.
- What attachment upload expects: `sd_number` must be the bare SD number string (e.g. `"SO20160600145"`), or use `sd_recid` with the numeric id. It must not be the whole lookup JSON. Extract it from the lookup result (`servicedesk.item[0].sd_number`) or, better, reuse the `servicedesk` value returned when the record was created.
- Alternative: query via the SQL endpoint (see below); the docs' recommended read path.

## 4. SQL endpoint (`sql.json`, unused)

Source: https://wiki360.pcr.com/pcr360-wiki/2025.2/sql-api-endpoint

- `POST https://<host>/api/<KEY>/sql.json`, headers `Content-Type: application/json`, `Pcr-Html-Encoded: TRUE`. POST is required (long statements).
- Body: `sql` (required, a SELECT statement), `limit` (default 20), `page` (default 1).
- Read-only: SELECT only.
- Response: `status`, `page`, `count`, `total_count`, `results` (array of row objects; sample shows uppercase column keys despite the "lowercase" statement).
- Table/column names: see the Data Dictionary (`/pcr360-wiki/2025.2/data-dictionary`). Needs the key to carry SQL read permission (unverified how it is granted).
- Example: `{"sql": "SELECT RECID, CODE, DESCRIPTION FROM CLASSES_OF_SERVICE"}`. This is how Classes of Service (likely what `sdc` refers to, unverified) are retrieved.

## 5. Errors and status codes

Source: https://wiki360.pcr.com/pcr360-wiki/2025.2/api

| Code | Meaning |
|---|---|
| 200 | Success |
| 400 | Bad data; nothing executed |
| 401 | Permissions do not authorize the operation |
| 403 | User lacks needed permission |
| 404 | Endpoint not found |
| 405 | Operation not allowed |
| 503 | Unavailable, typically maintenance mode |

- Write failures return a body `{"status":"failure","message":...}`. Typical causes: missing required fields (including UDFs required for that SD type), invalid `type`, bad RECIDs.
- No dedicated error page exists; IP restriction behaviour is not documented.

## 6. Gotchas for this project

1. **FIXED 2026-11-10** (test access request now uploads to the `servicedesk` number from the create call). `lookup_sd` (`app/clients/pcr360.py`) returns the full parsed JSON, and per the task notes callers pass that as `sd_number` to `upload_attachment`. That is wrong: `sd_number` must be a string such as `SO2016...`. Extract it (or use the create response's `servicedesk`).
2. **FIXED 2026-11-10** (`lookup_sd` removed; nothing used it after fix 1). `lookup_sd` uses `GET servicedesk.json?SEARCH=...`. The docs show `SEARCH` only for LIST lookups and read types `SO`/`IN` only. Behaviour is unverified; consider `servicedesk.SO.json` with a documented filter, or `sql.json` with `SELECT ... WHERE SD_NUMBER = ...`. It also sends no `HEADERS` and does no status check or `raise_for_status`.
3. `create_service_request` uses `type=SR`, which the 2025.2 page does not list as a supported write type. Verify against `LIST=SDTYPES` on the test instance. (An unsupported type should come back as a failure message listing valid types.)
4. Success is judged by HTTP only: `create_service_request`, `test_create_inquiry`, `add_equipment` use `raise_for_status()` and `create_inquiry`/`upload_attachment` check `>= 400`. A `{"status":"failure"}` body may arrive with HTTP 200 (unverified); check `response.json()["status"]`. `submit_ringcentral_request` now checks for a `servicedesk` number before uploading attachments (502 to TDX otherwise).
5. `create_inquiry` (prod) hardcodes `sdc=6`, `csr=566`, and callers supply `topic`; these are instance RECIDs. `test_create_inquiry` sends neither, so test passing does not prove the prod payload. `csr` is not documented for IQ.
6. `upload_attachment` goes to the **test** instance and `create_inquiry` to **prod**: an SD number from prod will not exist in test. Make sure the record and attachment target the same instance. `add_equipment` uses `_legacy_test_url()` with a different key (`pcr_api_key`).
7. `VVX_150 = 889` is a catalog RECID that may differ per instance.
8. `Pcr-Html-Encoded: TRUE` is sent on all POSTs: user-supplied text containing `&`-entity sequences will be decoded, and literal `<br>` in `remarks` (see `create_service_order`) is intentional HTML.
9. **FIXED 2026-11-10** (all calls use `HTTP_TIMEOUT` from `app/core/config.py`). No timeouts on `requests.*` calls; a hung PCR360 will hang the worker.
10. Logging: `create_inquiry` logs email/payload; `lookup_sd` and attachment logging dump whole responses. Do not log the URL (contains the API key).
11. `requests` `json=` already sets `Content-Type: application/json`; the explicit header is harmless.
12. Attachments + `Pcr-Html-Encoded: TRUE` (seen 2026-11-10 on PCR360 test): `type=ATTACHMENT`, and `files` sent with an SO create, both came back HTTP 500 with PCR360's HTML error page. Likely cause (unverified): the header HTML-decodes every parameter and fails on the nested `files` list. `upload_attachment` now sends only `Content-Type`. The SO is created first, so a failed attachment never loses the SO.
13. `requests` errors include the full URL, which holds the API key. All PCR360 calls go through `_post`/`_raise_for_status`, which raise `PCR360Error` without the URL (`from None`, so the chained exception isn't printed either).
14. Creating an IQ returns its **RECID** in `servicedesk` (e.g. `33359`), not an `IQ...` number, so inquiry attachments and remarks use `sd_recid`. SO creates return the SO number (`SO-000079`), so SO attachments use `sd_number`.
15. `type=REMARKS` (`sd_recid`, `remarks`) is how we add a note after creation, e.g. listing attachments that could not be added. The docs don't say it works on IQ (unverified until tested on PCR360 test).
