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

Manual testing routes are in `app/api/routes/debug.py`.

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
Optional: `LOG_LEVEL` (default `INFO`).

## Running locally

```bash
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

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
