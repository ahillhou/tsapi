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


@dataclass(frozen=True)
class Settings:
    # TeamDynamix
    tdx_base_url: str
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


@lru_cache
def get_settings() -> Settings:
    return Settings(
        tdx_base_url="https://utk.teamdynamix.com/sbtdwebapi",
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
        rc_sms_from_number="+18659749955",
    )
