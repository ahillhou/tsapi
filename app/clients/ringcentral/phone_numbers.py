"""RingCentral company phone numbers (v1 /phone-number)."""

import logging
import time

from app.clients.ringcentral.errors import RingCentralError

logger = logging.getLogger(__name__)

PHONE_NUMBER_PATH = "/restapi/v1.0/account/~/phone-number"
PHONE_NUMBER_PAGE_SIZE = 1000

# The list is in rate group Heavy (about 10 requests a minute). Pause between
# pages, and if RingCentral still says CMN-301 (rate exceeded), wait out the
# window and try again.
PAGE_PAUSE_SECONDS = 7
RATE_LIMIT_WAIT_SECONDS = 65
RATE_LIMIT_RETRIES = 3


def _get_page(platform, page: int, sleep) -> dict:
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            return platform.get(
                PHONE_NUMBER_PATH,
                {"page": page, "perPage": PHONE_NUMBER_PAGE_SIZE},
            ).json_dict()
        except RingCentralError as exc:
            if exc.code != "CMN-301" or attempt == RATE_LIMIT_RETRIES:
                raise
            logger.warning("Phone number list rate limited; waiting %ss", RATE_LIMIT_WAIT_SECONDS)
            sleep(RATE_LIMIT_WAIT_SECONDS)

    raise AssertionError("unreachable")


def list_phone_numbers(platform, sleep=time.sleep) -> list[dict]:
    """
    Every number on the account. Each record has `phoneNumber` (E.164),
    `usageType` (DirectNumber, CompanyNumber, IntegrationNumber,
    ContactCenterNumber, MainCompanyNumber, ...), `status` and, when the
    number is on an extension, `extension` {id, extensionNumber}.
    """

    numbers: list[dict] = []
    page = 1

    while True:
        data = _get_page(platform, page, sleep)
        numbers += data.get("records", [])

        if page >= data.get("paging", {}).get("totalPages", 1):
            return numbers

        page += 1
        sleep(PAGE_PAUSE_SECONDS)
