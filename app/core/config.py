"""
Application settings, read once from environment variables.

In production the variables come from `docker run --env-file app/.env`.
For local runs, app/.env is loaded here if it exists (it is never copied
into the Docker image, see .dockerignore). Variables that are already set
in the environment always win over the file.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# (connect, read) seconds for calls to TDX and PCR360. Generous read time
# because attachment uploads can be large, but never wait forever.
HTTP_TIMEOUT = (10, 60)


@dataclass(frozen=True)
class Settings:
    # TeamDynamix. tdx_base_url is the sandbox; the production API is used
    # only to download attachments from production forms.
    tdx_base_url: str
    tdx_prod_base_url: str
    tdx_app_id: int
    tdx_username: str | None
    tdx_password: str | None

    # PCR360
    pcr_test_host: str
    pcr_prod_host: str
    pcr_api_key: str | None
    pcr_test_api_key: str | None
    pcr_prod_api_key: str | None

    # RingCentral
    rc_server_url: str
    rc_client_id: str | None
    rc_client_secret: str | None
    rc_jwt_token: str | None
    rc_sms_from_number: str

    # Phone numbers allowed to switch Parking event messages by text
    # (app/services/parking_events.py). Empty = nobody.
    parking_event_senders: tuple[str, ...]

    # Webhook security (see app/core/security.py)
    tdx_webhook_secret: str | None
    ringcentral_webhook_secret: str | None

    # Report downloads (app/api/routes/reports.py); closed when unset
    reports_secret: str | None

    # Resolve TDX tickets of finished PCR access requests on a timer
    # (app/services/access_request_close.py): "off", "dry_run" or "on".
    access_request_autoclose: str

    # Manual testing routes in app/api/routes/debug.py
    enable_debug_routes: bool


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _env_choice(name: str, choices: tuple[str, ...]) -> str:
    """First choice is the default; anything unrecognised also falls back to it."""

    value = os.getenv(name, "").strip().lower()
    return value if value in choices else choices[0]


def _env_list(name: str) -> tuple[str, ...]:
    """Comma-separated values: "a, (865) 555-0100" -> ("a", "(865) 555-0100")."""

    return tuple(v.strip() for v in os.getenv(name, "").split(",") if v.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings(
        tdx_base_url="https://utk.teamdynamix.com/sbtdwebapi",
        tdx_prod_base_url="https://utk.teamdynamix.com/tdwebapi",
        tdx_app_id=2278,
        # TDX_USERNAME/TDX_PASSWORD are preferred; USERNAME/PASSWORD are
        # what the server's .env uses today.
        tdx_username=os.getenv("TDX_USERNAME") or os.getenv("USERNAME"),
        tdx_password=os.getenv("TDX_PASSWORD") or os.getenv("PASSWORD"),
        pcr_test_host="https://pcr360-test.utk.pcr-360.com",
        pcr_prod_host="https://pcr360.utk.pcr-360.com",
        pcr_api_key=os.getenv("PCR_API_KEY"),
        pcr_test_api_key=os.getenv("PCR_TEST_API_KEY"),
        pcr_prod_api_key=os.getenv("PCR_PROD_API_KEY"),
        rc_server_url="https://platform.ringcentral.com",
        rc_client_id=os.getenv("RC_CLIENT_ID"),
        rc_client_secret=os.getenv("RC_CLIENT_SECRET"),
        rc_jwt_token=os.getenv("RC_JWT_TOKEN"),
        # Replies must come from the number staff text to trigger the
        # workflows: ext 41100 "OIT Design SMS Custom Rule Controller"
        # (SMS-enabled direct number). The JWT in RC_JWT_TOKEN must be that
        # user's, since /extension/~/sms sends as the JWT's user.
        rc_sms_from_number=os.getenv("RC_SMS_FROM_NUMBER") or "+18659741100",
        # Staff phone numbers stay in app/.env, never in git (public repo).
        parking_event_senders=_env_list("PARKING_EVENT_SENDERS"),
        tdx_webhook_secret=os.getenv("TDX_WEBHOOK_SECRET") or None,
        ringcentral_webhook_secret=os.getenv("RINGCENTRAL_WEBHOOK_SECRET") or None,
        reports_secret=os.getenv("REPORTS_SECRET") or None,
        access_request_autoclose=_env_choice("ACCESS_REQUEST_AUTOCLOSE", ("off", "dry_run", "on")),
        enable_debug_routes=_env_bool("ENABLE_DEBUG_ROUTES"),
    )
