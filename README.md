# TS API

FastAPI service that connects TeamDynamix (TDX), PCR360 and RingCentral.
Runs in Docker on port 8000 behind the university VIP (VPN only).

## Live integrations

| Route | Called by | Does |
| --- | --- | --- |
| `POST /tdx/webhook/access_request` | TDX PCR access form | Creates an Inquiry in PCR360 **production** |
| `POST /tdx/webhook` | TDX RingCentral request form | Creates a Service Request in PCR360 test, copies attachments |
| `POST /demo/dayoff` | RingCentral SMS workflow | Toggles a nurse's out-of-office call rule, texts back the result |
| `POST /ringcentral/dnd` | RingCentral workflow | Turns Do Not Disturb on/off |

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
   to send the `X-Webhook-Secret` header with that value.
3. Add it to `app/.env` (`TDX_WEBHOOK_SECRET=` or
   `RINGCENTRAL_WEBHOOK_SECRET=`) and run `./deploy.sh`.
4. Submit a test form or text, and check `docker logs` for
   "Rejected ... webhook".

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
`ENABLE_DEBUG_ROUTES` (default off), `LOG_LEVEL` (default `INFO`).

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
