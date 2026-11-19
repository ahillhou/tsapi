# TS API

FastAPI service that connects TeamDynamix (TDX), PCR360 and RingCentral.
Runs in Docker on port 8000 behind the university VIP (VPN only).

## Live integrations

| Route | Called by | Does |
| --- | --- | --- |
| `POST /tdx/webhook/access_request` | TDX PCR access form | Creates an Inquiry in PCR360 **production** |
| `POST /tdx/webhook/project_intake` | TDX project intake form (production) | Creates a Project in PCR360 **production**, copies attachments |
| `POST /tdx/webhook/test_project_intake` | TDX project intake form (sandbox) | Creates a Project in PCR360 test, copies attachments |
| `POST /tdx/webhook` | TDX RingCentral request form | Creates a Service Request in PCR360 test, copies attachments |
| `POST /demo/dayoff` | RingCentral SMS workflow | Toggles a nurse's out-of-office call rule, texts back the result |
| `POST /ringcentral/dnd` | RingCentral workflow | Turns Do Not Disturb on/off |
| `POST /ringcentral/parking_event` | RingCentral SMS workflow (Parking staff) | Turns a Parking event message on/off on queue 46031 **production**, texts back the result |
| `POST /ringcentral/test_parking_event` | RingCentral SMS workflow (testing) | Same, on the OIT Design test queue 98765 |

**These URLs must not change.** The TDX admin builds the forms and owns
the webhook URLs configured in TDX; we can't edit them. Renaming or
moving a live route breaks that integration. If a route needs a new
path, add the new one and keep the old one working.
`tests/test_route_contract.py` fails if a live URL disappears.

Manual testing routes are in `app/api/routes/debug.py`. They are only
available when `ENABLE_DEBUG_ROUTES=true`.

## Webhook security

TDX and RingCentral each have their own shared secret, sent in the
`X-Webhook-Secret` header (or `?key=<secret>` on the URL if a platform
can't set headers; the header is better because URLs are logged).
A wrong or missing secret gets `401` and nothing is sent to PCR360 or
RingCentral.

If a secret isn't set, that caller's routes stay open and a warning is
logged at startup. To turn a secret on without breaking anything:

1. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
2. Configure the caller (the TDX web service or the RingCentral workflow)
   to send the `X-Webhook-Secret` header with that value. For TDX this
   is a request to the TDX admin: they add a header to the existing web
   service, and the URL stays the same. Don't use `?key=` for TDX,
   because that changes the URL.
3. Add it to `app/.env` (`TDX_WEBHOOK_SECRET=` or
   `RINGCENTRAL_WEBHOOK_SECRET=`) and run `./deploy.sh`.
4. Submit a test form or text, and check `docker logs` for
   "Rejected ... webhook".

## Reports

`GET /reports/ringcentral/unused-licenses?days=180` downloads a CSV of
enabled RingCentral users with no calls (inbound or outbound) in the last
`days` days (default 180, max 184: RingCentral keeps 184 days of
analytics). Use it to find licenses to reclaim.

Reports are off until `REPORTS_SECRET` is set in `app/.env`, and the
secret is only accepted in the `X-Webhook-Secret` header. The RingCentral
app needs the **Analytics** permission (plus ReadAccounts, which it already
has). From PowerShell on the VPN:

```powershell
Invoke-WebRequest "http://<server>:8000/reports/ringcentral/unused-licenses?days=180" `
  -Headers @{ "X-Webhook-Secret" = "<REPORTS_SECRET>" } -OutFile unused.csv
```

### Phone number audit

`GET /reports/number-audit` downloads a CSV with every phone number found in
PCR360 **production** (phone services, read with `sql.json`; the production
key needs SQL read) or RingCentral, one row each. The **Comparison** column
says where it is in each system, e.g. "PCR360 Available, RingCentral
assigned", "PCR360 Active, not in RingCentral", "Not in PCR360, RingCentral
unassigned". Numbers that agree ("PCR360 Active, RingCentral assigned") are
left out unless `include_matches=true`. The **PCR360 Pool** column is the
number's service pool (Admin > System Tables > Service Pools), so pools never
meant for RingCentral (e.g. RENTAL, ISDN POOL, "Do Not Port to RC") can be
filtered out.

`GET /reports/number-audit/summary` returns just the count per comparison
(JSON), shown on the Swagger page.

"Assigned" = the RingCentral number is on an extension. Numbers are matched
on their last 10 digits. Read-only on both systems; takes 1-3 minutes
because RingCentral rate-limits its number list. Same reports secret and
Swagger Authorize steps as above.

## Parking event messages

Parking & Transportation can switch a temporary message (football games,
concerts, permit sales...) on and off by text. Callers hear it as soon as
they reach the Customer Service queue (46031), before it rings the agents.

Setup, done once by OIT in the RingCentral admin portal (queue > Call
Handling & Agents > Custom rules), one rule per event:

- Name it `Event - <name>`, e.g. `Event - Football`. The app only touches
  rules named this way; the name after the dash is what staff text.
- Condition: Date and/or Time, weekly, the queue's business hours
  (Mon-Fri 7:30-4:30). An enabled custom rule beats the after-hours rule
  whenever its schedule matches, so don't schedule it all day.
- Call handling: Ring call queue agents, the event recording as the
  welcome greeting, and the same agents, wait and voicemail settings as the
  queue. **When the queue's routing changes, change every event rule too.**
- Leave it turned off.

Staff text the RingCentral workflow number: `FOOTBALL ON` (any other event
goes off), `FOOTBALL OFF`, `EVENT OFF`, `STATUS`; anything else gets the
list of commands and events. Only numbers in `PARKING_EVENT_SENDERS` are
answered; texts from other numbers are ignored without a reply. The
workflow posts `{"command": <text>, "sender": <phone number>}`.

## Layout

```
app/
  main.py          creates the app and includes the routers
  core/            settings (env vars) and logging
  api/routes/      one module per caller: tdx, ringcentral, health, debug
  schemas/         request body models
  services/        business logic (what each webhook actually does)
  clients/         thin wrappers around TDX, PCR360 and RingCentral APIs
```

Routes only parse the request and call a service. Services hold the logic.
Clients only talk to the outside API. To add a new integration, add a
client, a service and a router, then include the router in `main.py`.

## Configuration

Secrets live in `app/.env` (never committed, never copied into the image)
and are passed with `docker run --env-file app/.env`:

`USERNAME`, `PASSWORD` (TDX), `PCR_API_KEY`, `PCR_TEST_API_KEY`,
`PCR_PROD_API_KEY`, `RC_CLIENT_ID`, `RC_CLIENT_SECRET`, `RC_JWT_TOKEN`.
Optional: `TDX_WEBHOOK_SECRET`, `RINGCENTRAL_WEBHOOK_SECRET`,
`REPORTS_SECRET` (enables `/reports/...`),
`ENABLE_DEBUG_ROUTES` (default off), `LOG_LEVEL` (default `INFO`),
`RC_SMS_FROM_NUMBER` (nurse SMS reply sender, default `+18659740716`, the
number nurses text; must be an SMS number of the RingCentral JWT user),
`PARKING_EVENT_SENDERS` (comma-separated phone numbers allowed to switch
Parking event messages; empty = nobody).

## Running locally

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
uv run pytest
```

The tests replace TDX, PCR360 and RingCentral with fakes that record every
call, so they never touch the real systems. They check the exact payloads
sent (including which PCR360 instance, test or prod, each route uses),
the remarks text, the RingCentral day-off flow, and the webhook secrets.

GitHub Actions runs the tests and builds/starts the Docker image on every
push (`.github/workflows/tests.yml`). Check that it's green before
deploying.

## Dependencies

Edit `pyproject.toml`, then refresh the lock file and the pinned list the
Docker image installs:

```bash
uv lock
uv export --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt
```

## Deploying

On the server: `git pull`, then `./deploy.sh` (builds the image, replaces
the `voicerequest` container, follows the logs).
