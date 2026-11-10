# RingCentral API reference (project notes)

Scope: only the RingCentral calls this service makes or receives. Written from the
public developer guide. The interactive API reference (developers.ringcentral.com/api-reference)
is JavaScript-rendered and could not be fetched, so per-endpoint details taken from it
(rate group, exact permissions, field lists) are marked "(unverified)" unless a guide page
confirmed them. Re-check in the Developer Console before relying on them.

Code map: `app/clients/ringcentral/{auth,extensions,interaction_rules,presence,sms}.py`,
`app/services/nurse_dayoff.py`, `app/api/routes/ringcentral.py`.
SDK: `ringcentral` 0.9.2, server `https://platform.ringcentral.com`.

## 1. Authentication (JWT)

- Server-to-server flow: the app holds a client id/secret plus a long-lived JWT credential
  (created in the Developer Console / Admin Portal for one user). `platform.login(jwt=...)`
  exchanges it at the token endpoint for an access token (and a refresh token, if the app has
  "Issue refresh tokens" enabled).
- Access token lifetime: 1 hour. Refresh token lifetime: 7 days (`refresh_token_expires_in`
  604799 s in the sample response).
- Refresh tokens are single use and normally rotate on each refresh; the old one stops
  working ~10 s after the new access token is first used (up to 60 min if never used).
- The JWT credential itself has its own expiry and can be configured to never expire; it is
  independent of the access-token lifetime. When an access token expires, the JWT can be used
  to get a new one. So re-logging in with the JWT after the refresh token ages out is the
  documented-compatible approach (the page does not spell out "refresh token expired" errors).
- Token endpoint is in the **Auth** rate group (see section 3). Do not log in per request.
- Is `if not platform.logged_in(): login(jwt=...)` sound? Largely yes: `logged_in()` is
  false when the session cannot be used, and a fresh JWT login always recovers as long as the
  JWT credential is valid. Caveats: (a) confirmed in the SDK 0.9.2 source
  (`ringcentral/platform/platform.py`): `logged_in()` returns true if the access token is
  valid, otherwise calls `refresh()`; refresh errors are swallowed and it returns False, so
  our code then logs in again with the JWT; (b) it will not help if the JWT credential itself was revoked/expired, or the
  credential's user was disabled - login then raises; (c) a 401 mid-call (token revoked) is
  not caught by `logged_in()`.

Source: https://developers.ringcentral.com/guide/authentication/refresh-tokens ,
https://developers.ringcentral.com/guide/authentication/jwt/troubleshooting

## 2. App permissions (scopes)

Set on the app in the Developer Console; JWT tokens inherit the app's permissions intersected
with the authenticated user's own rights. After changing scopes, create a fresh token.

| Call | Permission needed |
|---|---|
| GET /account/~/extension, /extension/{id} | ReadAccounts (EditExtensions includes it) |
| PUT .../extension/{id}/presence (dndStatus) | EditPresence (includes ReadPresence) |
| v2 comm-handling interaction-rules GET/PATCH | a call-handling permission, name not confirmed: likely ReadCallHandling-type / EditExtensions-type scope (unverified - check "App scopes" list in console; the permissions page did not list an EditCallHandling scope) |
| POST .../extension/~/sms | SMS (includes ReadMessages) |

User-side rights also matter: editing another user's presence/call handling requires the
authenticated (JWT) user to be an admin with rights over that extension (unverified).

Source: https://developers.ringcentral.com/guide/basics/permissions

## 3. Rate limits

Per user, per app, defaults (support can change per app):

| Group | Requests / min | Typical use |
|---|---|---|
| Light | 50 | simple reads/writes |
| Medium | 40 | e.g. extension list, SMS (unverified) |
| Heavy | 10 | bulk / expensive ops |
| Auth | 5 | token endpoint (`login`, refresh) |

Penalty interval: 60 s. Group assignment of our endpoints (unverified, from API reference
which could not be loaded; likely: extension list/get = Medium or Light, presence PUT =
Light/Medium, comm-handling = Medium, SMS POST = Medium, token = Auth). Read the
`X-Rate-Limit-Group` header on real responses to confirm.

Throttled response: HTTP 429. Headers: `Retry-After` (seconds; if absent wait >= 30 s),
`X-Rate-Limit-Group`, `X-Rate-Limit-Limit`, `X-Rate-Limit-Remaining`, `X-Rate-Limit-Window`.
Those headers are present only for user-level limits; a 429 without them means an
account/global/custom limit. Requests sent during a penalty reset the penalty window, so stop
sending until it elapses. Group names may change; do not hardcode the four.

Source: https://developers.ringcentral.com/guide/basics/rate-limits

## 4. Extensions

`GET /restapi/v1.0/account/~/extension` - paged list. Params: `page`, `perPage`
(max 1000 reported; sources disagree, default 100), `status` (Enabled, Disabled, Frozen,
NotActivated, Unassigned), `type` (User, etc.; multiple allowed). Response: `records[]`
(each: `id`, `extensionNumber`, `name`, `type`, `status`, `contact{firstName,lastName,
email,department,...}`), plus `paging` (`page`, `perPage`, `totalPages`, `totalElements`)
and `navigation`. (field lists unverified)

`GET /restapi/v1.0/account/~/extension/{id}` - single extension; same fields plus
`permissions`, `regionalSettings` etc. (unverified). `~` as id = authenticated extension.

Finding by number: third-party summaries list an `extensionNumber` filter on the list
endpoint (alongside `email`, `status`, `type`), but the official reference could not be
confirmed (unverified). Try `GET .../extension?extensionNumber=1234&status=Enabled&perPage=10`
against the real account; if honoured it returns 0-1 records and replaces the full scan.
Fallback options: cache the number->id map at startup/TTL, or use the company directory
search (`POST /restapi/v1.0/account/~/directory/contacts/search`, scope ReadAccounts /
directory permission, unverified).

Source: https://developers.ringcentral.com/guide/account ,
https://developers.ringcentral.com/api-reference/Extensions/listExtensions (not loadable)

## 5. Presence / Do Not Disturb

`PUT /restapi/v1.0/account/~/extension/{id}/presence` body `{ "dndStatus": ... }`.
`dndStatus` values: `TakeAllCalls`, `DoNotAcceptAnyCalls`, `DoNotAcceptDepartmentCalls`,
`TakeDepartmentCallsOnly` (unverified, from memory of the reference). We use the first two.
Response returns the presence info (`userStatus`, `dndStatus`, `telephonyStatus`...).
Note: in v2 call handling, DND is also a "state-based rule", triggered by presence.

Source: https://developers.ringcentral.com/api-reference/Presence/updateUserPresence (not
loadable); https://developers.ringcentral.com/guide/voice/call-routing/user-call-handling

## 6. Call handling v2 (interaction rules)

Model: each user's inbound call handling is a set of
- **State-based rules** (system-created, customizable): Forward-All-Calls, Do-Not-Disturb,
  Work-Hours, After-Hours (only if hours are not 24/7), Agent (only for queue members).
  Triggered by schedule; DND by presence.
- **Interaction (custom) rules**: user-defined, triggered by caller IDs, called numbers,
  schedule (range/weekly), and/or state. All conditions are ANDed; priority depends on which
  condition types are set (all three highest). Each has `id`, `displayName`, `enabled`, and
  greeting/ring/no-answer actions.

Endpoints (v2): base `/restapi/v2/accounts/~/extensions/{id}/comm-handling/voice`
- `GET /interaction-rules` -> `records[]` (we match on `displayName`, case-insensitive)
- `GET|PATCH|DELETE /interaction-rules/{ruleId}`, `POST /interaction-rules` to create
- `GET|PATCH /state-rules/{work-hours|after-hours|dnd|agent|forward-all-calls}`
v1.0 `PUT` became v2 `PATCH` in the migration.

PATCH semantics: the migration guide does not define merge behaviour. Our code does
GET-then-PATCH with the whole rule (read-modify-write), which is safe. Whether a minimal body
`{"enabled": false}` is accepted is (unverified); test it, since a smaller body avoids
echoing read-only fields back (`id`, etc.) and races with concurrent edits. `enabled:false`
means the rule is not evaluated, so calls fall through to the next matching rule/state.

Source: https://developers.ringcentral.com/guide/voice/call-routing/user-call-handling ,
.../user-call-handling/interaction-rules , .../user-call-handling/migration-guide

## 7. SMS

`POST /restapi/v1.0/account/~/extension/~/sms` body:
`{"from":{"phoneNumber":"+1..."},"to":[{"phoneNumber":"+1..."}],"text":"..."}`.
Response (message info): `id`, `uri`, `type: SMS`, `direction: Outbound`, `from`, `to[]`
(each with `messageStatus`), `messageStatus` (Queued -> Sent/Delivered/DeliveryFailed/
SendingFailed), `smsDeliveryTime`, `creationTime` (field names unverified). `Queued` on
return is normal; final status needs polling or an event subscription.

`from` requirements: must be an SMS-enabled number belonging to the authenticated (JWT)
extension. Numbers are not SMS-enabled by default. US/Canada local numbers must be linked to
an approved brand + campaign (10DLC); toll-free numbers need verification. Campaign status
must be `Confirmed` or sends fail. Check with
`GET .../extension/{id}/phone-number/{phoneNumberId}/sms-configuration`. Numbers carry
`SmsSender` features. Content must match a registered campaign use case. Low-volume tier is
capped at 6,000 messages/day to US carriers. TCPA/consent and opt-in/out handling are
covered on separate guide pages that were not readable; for notifications to staff who
texted us first, replying within the thread is low risk but get compliance sign-off
(unverified). Permission: SMS.

Source: https://developers.ringcentral.com/guide/messaging/sms/sms-requirements

## 8. Inbound: RingCentral Workflow Builder calls to us

- No official Workflow Builder page on its HTTP request action was found. Closest docs:
  the RingCentral Automator / RingCX Workflow Studio HTTP request nodes, which support
  GET/POST/PUT/PATCH/DELETE, a key-value Custom Headers list, a content-type field, and a
  string body (used for POST/PUT/PATCH/DELETE). Whether Workflow Builder's action has the
  same fields is (unverified): open the action in the builder UI and look for a Headers
  section before depending on `X-Webhook-Secret`.
- Body: our payload has `command`, `extensionId`, `sender`. The body is a template string
  with variables substituted in, so it is not guaranteed to be valid JSON (quoting is not
  escaped).
- Why NBSP (U+00A0): not documented. Likely the builder's rich-text/template editor inserts
  non-breaking spaces between the JSON tokens or around variables (unverified; plausible
  cause is copy-paste from the browser editor). Our `replace(" "," ")` on the decoded body is the right fix.
- RingCentral docs state that for calls to RingCentral API URLs the Automator adds
  `Authorization` automatically; for third-party URLs it will not, so the shared secret
  header must be configured by hand.

Source: https://ringcentral.github.io/ringcentral-automator-docs/workflows/custom/actions/http-request ,
https://support.ringcentral.com/engagevoice/admin/voice-admin-use-www-node.html

## 9. Gotchas / improvements for this project

1. `get_extension_by_number` pages through every extension on each manager command (a
   1000-record page per call, Medium/Light group). Try the `extensionNumber` filter (add
   `status=Enabled`), or cache a number->id map. It also loops until an empty page; use
   `paging.totalPages` as the stop condition.
2. `get_platform()` holds a lock during login and returns a shared platform object; fine,
   but a 401 mid-request is not handled. Wrap calls with: on 401 force re-login and retry
   once; on 429 sleep `Retry-After` (default 30 s) and retry once, never in a tight loop.
3. Handle `ApiException` from the SDK; `response.json_dict()` errors surface as exceptions
   in the route and return 500 to the workflow. Return a controlled error/retry signal.
4. `send_sms` logs the full payload (phone numbers, message text). Redact or drop to DEBUG.
5. `update_interaction_rule` sends the whole GET body back. Test `{"enabled": x}` alone
   (unverified); if accepted, switch to it. Also `find_dayoff_rule` matches by `displayName`
   string - brittle if an admin renames the rule; consider storing rule ids or a config
   setting for the name.
6. `DAYOFF`/`BACK` via `/ringcentral/dnd` and the rule toggle both change availability
   differently (DND presence vs custom rule); decide on one to avoid conflicting states.
7. SMS `from` (`rc_sms_from_number`) must be SMS-enabled on the JWT user's extension; a
   campaign lapse makes replies fail silently (we only log the exception). Surface it.
8. Webhook parsing: also tolerate other odd whitespace (e.g. U+202F, U+200B, `\r\n` inside
   strings). Use `strict=False` in `json.loads` if the template yields raw newlines. (The
   secret header check in `app/core/security.py` already uses `hmac.compare_digest`.)
9. Workflow caller is only authenticated by the secret header (if Workflow Builder lets us
   set one); `sender` and `extensionId` in the body are trusted values. Validate that
   `sender` matches the extension's own mobile/contact number before acting for a manager.
10. Token budget: Auth group is only 5/min. Avoid constructing a new `SDK()` per request;
    the current singleton is correct.
