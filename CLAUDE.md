# TS API

FastAPI service connecting TeamDynamix (TDX), PCR360 and RingCentral.
See README.md for the layout, live routes, config and deploy steps.

## Hard rules

- **Never change a live webhook URL.** The TDX admin owns the form and
  web-service config and the URLs can't be changed from our side;
  RingCentral workflows are configured separately. If a route needs a new
  path, add it and keep the old one. `tests/test_route_contract.py` guards this.
- **`/tdx/webhook/access_request` is production-critical** (TDX form ->
  PCR360 production inquiry). Changes to it, `app/services/pcr_access_request.py`,
  `app/services/tdx_remarks.py` or `app/clients/pcr360.py` need tests that
  pin the exact outbound payload.
- **The repo is public** (github.com/ahillhou/tsapi). No secrets, API keys,
  tokens or vendor documentation in git. Secrets live only in `app/.env`
  (git- and docker-ignored). Webhook secrets go in the `X-Webhook-Secret`
  header, never in the URL.
- **Each PCR360 function targets a fixed instance (test or prod) on purpose.**
  Don't "unify" them without asking.
- The hardcoded inquiry email in `pcr_access_request.py` is intentional.

## Working here

- Tests: `uv run pytest` (fakes record every outbound call; nothing touches
  real systems). Run before every commit. CI (GitHub Actions) also builds
  the Docker image and checks `/health`.
- Dependencies: edit `pyproject.toml`, then `uv lock` and
  `uv export --frozen --no-hashes --no-dev --no-emit-project -o requirements.txt`.
- The production server can't be reached from this machine. Deploys are
  manual: `git pull` then `./deploy.sh` on the server (one container,
  port 8000, behind a VIP on the university VPN).
- Layout: routes only parse requests and call a service; services hold
  logic; clients wrap outside APIs. New integration = client + service +
  router, included in `app/main.py`.

## API references

Read the relevant file before changing a client or adding a call:

- `docs/tdx-api.md` (source: https://utk.teamdynamix.com/sbtdwebapi/swagger)
- `docs/pcr360-api.md` (source: https://wiki360.pcr.com/pcr360-wiki/2025.2)
- `docs/ringcentral-api.md` (source: https://developers.ringcentral.com/guide)

These are our own short notes. For anything they don't cover, read the
source docs directly; all three are public.
