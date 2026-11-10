# TeamDynamix (TDX) Web API - developer reference

Scope: what this project uses (`app/clients/tdx.py`, `app/services/tdx_remarks.py`).
Checked against the live spec on 2026-11-10. Anything unconfirmed is marked "(unverified)".

## 1. Base URLs: sandbox vs production

| Environment | Base URL |
|---|---|
| Sandbox | `https://utk.teamdynamix.com/sbtdwebapi` |
| Production | `https://utk.teamdynamix.com/tdwebapi` (path casing is not significant) |

- **`sbtdwebapi` IS the sandbox ("SB" = sandbox).** TDX's overview article gives the SaaS pattern as
  `https://<tenant>/TDWebAPI/` for production and `https://<tenant>/SBTDWebAPI/` for sandbox.
- The production URL for utk is inferred from that pattern. `https://utk.teamdynamix.com/TDWebApi/swagger`
  returned HTTP 200 and `/TDWebApi/api/auth` returned 405 (route exists, wrong verb), so it exists (credentials not tested).
- Sandbox is a separate copy of the data: tickets, IDs, users, app IDs and custom attribute IDs can all differ from production,
  and sandbox is typically refreshed from production on a schedule (unverified).
  Credentials/web-services keys are also per environment (unverified).
- App ID `2278` (`tdx_app_id`) must be re-checked per environment.
- All requests and responses are JSON: send `Content-Type: application/json`.

Sources: https://utk.teamdynamix.com/sbtdwebapi/swagger ; https://solutions.teamdynamix.com/TDClient/KB/ArticleDet?ID=579

## 2. OpenAPI spec and guides

- Swagger UI: `https://utk.teamdynamix.com/sbtdwebapi/swagger`
- OpenAPI JSON (found in the UI's JS): `https://utk.teamdynamix.com/sbtdwebapi/swagger/v1/openapi.json` (about 1.5 MB, OpenAPI 3, version `v1`).
  The usual `swagger.json` paths return 404.
- Guides: `/swagger/guides/rate-limiting`, `/dates`, `/file-submission`, `/patching` (summarised below).

## 3. Authentication

| Endpoint | Body | Use |
|---|---|---|
| `POST /api/auth` | `{"UserName": "...", "Password": "..."}` | Normal user login (what we use). Also aliased as `/api/auth/login`. |
| `POST /api/auth/loginadmin` | `{"BEID": "...", "WebServicesKey": "..."}` | Key-based admin service account. Only for endpoints that say they require it. |

- Response is `text/plain`: the raw JWT string, NOT JSON. We read `auth_response.text`, which is correct.
- Send it as `Authorization: Bearer <jwt>`.
- Token lifetime: 24 hours. The `exp` claim in the JWT holds the exact expiry.
- BEID and WebServicesKey are shown in TDAdmin on the organization detail page, to admins with the "Add BE Administrators" permission.
  The admin service account must be Active.
- A 401 means either the user lacks permission or the token expired.
- `GET /api/auth/getuser` returns the current user (handy as a health check).
- Both auth endpoints are rate limited to 60 requests / 60 s per IP.

Source: https://utk.teamdynamix.com/sbtdwebapi/swagger (Authentication section and `/api/auth*` operations)

## 4. Rate limits

- Most endpoints we use: 60 requests per 60 seconds per IP address (some limits are per user or per organization; "additional limits may apply").
- The period starts at the first request and resets N seconds later. Each method has its own counter.
- Exceeding it returns `429 Too Many Requests`.
- Every rate-limited response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` (RFC 1123 date).
- TDX recommends: wait until `X-RateLimit-Reset`, with at least a 5 s minimum wait.

Source: https://utk.teamdynamix.com/sbtdwebapi/swagger/guides/rate-limiting

## 5. Endpoints we use

### 5.1 `GET /api/tickets/{id}`
- Finds a ticket across every ticketing app the caller can access (no appId needed).
- Caller must be a member of the ticket's app, hold View All Application Instances, or have workspace access.
  Being the requestor alone is not enough (a 403/404 here usually means a permissions problem on the service account).
- Returns a full `Ticket` object (section 6).
- App-scoped equivalent: `GET /api/{appId}/tickets/{id}`.

### 5.2 `POST /api/{appId}/tickets/search`
- Body is a `TicketSearch`; all fields optional. `{}` is valid. We send `search_body or {}`.
- Returns a flat JSON array of tickets, up to `MaxResults`.
- **Results are partial. They omit `Attachments`, `Attributes`, `Description`, `Notify`, `Tasks`.**
  You must call `GET /api/tickets/{id}` per hit to get the fields our remarks builders need.
- For large result sets use `POST /api/{appId}/tickets/search/paged`.
- Commonly useful filters (all documented in the spec):

| Field | Type | Meaning |
|---|---|---|
| `TicketID` | int | exact ID |
| `StatusIDs`, `StatusClassIDs`, `TypeIDs`, `FormIDs`, `ServiceIDs` | int[] | id filters |
| `RequestorEmailSearch`, `RequestorNameSearch` | string | LIKE match |
| `SearchText` | string | title, description, custom attributes (per spec text) |
| `CreatedDateFrom/To`, `ModifiedDateFrom/To` | ISO 8601 UTC | date ranges |
| `CustomAttributes` | array | filter by attribute |
| `MaxResults` | int | cap on results |

### 5.3 Attachment download
- `GET /api/attachments/{id}/content` returns the raw file bytes (needs auth).
- Each item in `Ticket.Attachments[]` carries `ContentUri` ("URI to retrieve the contents via the web API") and `Uri` (metadata).
- Our code builds `f"{tdx_base_url}/{content_uri}"`. This only works if `ContentUri` is a path relative to the API root
  (e.g. `api/attachments/<guid>/content`) with no leading slash. (unverified: not confirmed against a live ticket.)
  If it is absolute or has a leading `/`, the URL will be malformed. See Gotchas.

Sources: https://utk.teamdynamix.com/sbtdwebapi/swagger/v1/openapi.json (operations `/api/tickets/{id}`, `/api/{appId}/tickets/search`, `/api/attachments/{id}/content`)

## 6. Models we rely on

### Ticket (fields we read)

| Field | Type | Notes |
|---|---|---|
| `ID` | int32 | read-only |
| `Title` | string, max 300 | |
| `Description` | string, nullable | absent in search results. We use it as "Billing Account Number" (access request) and "Description" (RingCentral). |
| `RequestorName` | string, nullable, max 75 | read-only |
| `RequestorEmail` | string (email), nullable, max 125 | read-only |
| `WebUiUrl` | string (URI) | absolute link to the ticket in TDNext, read-only |
| `Attributes` | CustomAttribute[], nullable | custom fields on the ticket's form |
| `Attachments` | Attachment[], nullable | read-only |
| `AppID`, `StatusName`, `TypeName` | int / string / string | read-only, may be useful for filtering |

Most of the above can be `null` per the spec. Our code does `ticket["RequestorName"]` etc. directly (fine if the key is present).

### CustomAttribute (inside `Attributes[]`)

| Field | Type | Notes |
|---|---|---|
| `ID` | int | needed for PATCH paths |
| `Name` | string | what `get_attribute()` matches on (e.g. `RC Location`) |
| `Value` | string | raw value. For choice fields this is the choice ID, comma-separated for multi-select. |
| `ValueText` | string | human-readable value, read-only. This is what we use. |
| `FieldType`, `DataType` | string | |
| `Choices` | array | read-only |

### Attachment (inside `Attachments[]`)

`ID` (string), `Name`, `Size` (bytes), `ContentUri`, `Uri`, `CreatedDate`, `CreatedFullName`, `CreatedUid`, `IsPrivate`, `ItemID`, `AttachmentType`.

Dates everywhere are ISO 8601 in UTC (offsets accepted on input). Date-only custom attributes also accept `YYYY-MM-DD`.

Sources: openapi.json (`Ticket`, `CustomAttribute`, `Attachment`, `TicketSearch`); https://utk.teamdynamix.com/sbtdwebapi/swagger/guides/dates

## 7. Other ticket endpoints likely useful later

All are under `/api/{appId}/tickets` and rate limited to 60 / 60 s unless noted.

| Method + path | Purpose |
|---|---|
| `POST /{id}` | Edit ticket (send the full `Ticket`; returns the updated ticket). Query: `notifyNewResponsible`. |
| `PATCH /{id}` | Partial update with a JSON Patch array (tickets and custom attributes only). |
| `POST /{id}/feed` | Add a feed entry / comment (`TicketFeedEntry` body: comments, notify lists, status change, privacy). Returns the item update. |
| `GET /{id}/feed` | Read a ticket's feed. |
| `POST /{id}/attachments` | Upload attachment (`multipart/form-data`, part `file`; query `isPrivate`, `showViewLink`). |
| `POST /{id}/attachments/bulk` | Upload several files in one request. |
| `POST /{id}/attributes/{attributeId}/attachments` | Upload to a file-upload custom attribute. |
| `POST /search/paged` | Paged search. |
| `GET /statuses/search` (POST) | List statuses, to resolve `StatusID`. |

PATCH body example (paths are case-insensitive; custom attributes are addressed by attribute ID, not position;
`remove` clears a value; `test`/`copy`/`move` are unsupported):

```json
[{"op":"add","path":"/title","value":"New title"},
 {"op":"add","path":"/attributes/1234","value":"value"},
 {"op":"remove","path":"/attributes/5678"}]
```

Multipart uploads: `Content-Type: multipart/form-data; boundary=...`; let the HTTP library build it (with `requests`, use `files=`
and do NOT also set `Content-Type: application/json`, which our `authenticate()` headers do by default).

Sources: openapi.json; https://utk.teamdynamix.com/sbtdwebapi/swagger/guides/patching ; https://utk.teamdynamix.com/sbtdwebapi/swagger/guides/file-submission

## 8. Workflow web services / webhooks (TDX calling our server)

What is confirmed (public TDX KB articles, e.g. "Using Web Services to Post to StatusPage"):
- Configured in TDAdmin > Applications > [Ticketing app] > Workflow Web Services.
- A **Web Service Provider** holds a name, a base URL, and an Active flag.
- A **Web Service Method** holds the HTTP verb, a URL (may contain `{placeholders}`), a **Headers tab** (key/value pairs, added manually),
  a **Body tab** (JSON with `{{parameter}}` placeholders), and a **Parameters tab** mapping each placeholder to a ticket field/attribute.
- The documented example sets `Authorization` as a custom header, so **custom headers are supported, so `X-Webhook-Secret` should be
  configurable** on the method's Headers tab. A workflow step then invokes the method on a ticket event.
- Nothing in the public KB says that header values can be encrypted or hidden after saving (unverified).

What is NOT confirmed / how our setup may differ (unverified):
- Our payload shape `{"data": <ticket>}` with a full ticket object looks different from the Body-tab-with-parameters model above.
  It may come from a form-workflow or integration feature, or a Body of `{"data": {{...}}}` hand-built by the TDX admin.
  Ask the TDX admin which mechanism sends it and whether the Headers tab is available on that mechanism before enabling the secret check.
- Retry behaviour, timeout, and whether a non-2xx response blocks or fails the workflow step are not documented in what I found (unverified).
  Keep handlers fast and return 2xx quickly.
- The Web API also exposes an inbound `POST /api/integrations/webhook?token=...` (tag Webhooks). It is for TDX RECEIVING webhooks
  from other systems, not for calling us. Not relevant here.
- Plan for the secret: the TDX admin adds `X-Webhook-Secret: <value>` to the method's Headers tab (per-caller secrets, per our recent commit).
  The URLs must not change. Roll out our check in a "log only" mode first, or after the admin has confirmed the header is being sent.
  Otherwise all workflows will start failing with 401/403.
- The same admin-owned config also decides sandbox vs production: the webhook URL in each environment's TDAdmin points at our server, and the
  `WebUiUrl` / `ContentUri` host in the payload will be whichever environment sent it.

Sources: https://solutions.teamdynamix.com/TDClient/1965/Portal/KB/Article/169898/Using-Web-Services-to-Post-to-StatusPage ;
https://solutions.teamdynamix.com/TDClient/KB/ArticleDet?ID=18979 ; https://solutions.teamdynamix.com/TDClient/KB/ArticleDet?ID=18608

## 9. Gotchas for this project

1. **FIXED 2026-11-10** (token is cached for 12h and refreshed once on a 401). **Token fetched on every call.** `get_ticket`, `search_tickets` and `download_attachment` each call `authenticate()`, so one ticket with N
   attachments costs N+2 auth requests. `/api/auth` is limited to 60/min per IP; this will 429 under load. Cache the JWT (24 h; refresh on 401
   or shortly before `exp`).
2. **No retry/429 handling.** `raise_for_status()` surfaces a 429. Honor `X-RateLimit-Reset` with a minimum 5 s wait.
3. **FIXED 2026-11-10** (`HTTP_TIMEOUT`). **No request timeouts** on any `requests` call, so a hung TDX connection hangs a worker. Add `timeout=`.
4. **Search results are partial** (no `Attributes`, `Description`, `Attachments`). `get_attribute()` and the remarks builders on a search hit
   will raise `KeyError`/return None. Fetch each ticket by ID first.
5. **FIXED 2026-11-10** (now tolerates null/missing Attributes). **`get_attribute()` indexes `ticket["Attributes"]`**, but the field is nullable. `Attributes` may be `null` or missing, so use `ticket.get("Attributes") or []`.
   Matching is by display `Name`, so renaming a field in TDX silently breaks remarks (returns None, rendered as "None").
   Use `ValueText` (readable) and not `Value` (choice IDs).
6. **`ContentUri` joining**: `f"{base}/{content_uri}"` assumes a relative path with no leading slash (unverified). Normalize with `urljoin`
   or strip the leading `/`; if it is absolute, check the host matches the configured base before sending the bearer token to it (token leak risk).
7. **Sandbox vs production is a config switch** (`tdx_base_url`, `tdx_app_id`, credentials). Use matching values together; mixing a production
   ticket ID with the sandbox base URL returns 404 or a different ticket.
8. **Service account permissions**: `GET /api/tickets/{id}` needs app membership / View All; webhook payloads can include tickets the account cannot
   re-fetch. Prefer using the webhook's embedded ticket, and only re-fetch if needed.
9. **Webhook payload**: we expect `{"data": <ticket>}`; the embedded ticket should be treated as untrusted until the `X-Webhook-Secret`
   check is enforced (and the shape might not include `Attachments`/`Attributes` for every workflow, unverified).
10. `authenticate()` sets `Content-Type: application/json` on every request, including the attachment GET (harmless) and any future multipart upload (breaks it).
11. Auth body keys are `UserName`/`Password` (spec casing); the TDX example uses lowercase, and both work (property matching is case-insensitive, unverified for auth).
