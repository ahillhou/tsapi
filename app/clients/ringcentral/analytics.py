"""RingCentral Business Analytics (call counts) and extension lists for reports."""

from datetime import datetime

AGGREGATION_PATH = "/analytics/calls/v1/accounts/~/aggregation/fetch"
EXTENSION_PATH = "/restapi/v1.0/account/~/extension"

# RingCentral limits: aggregation pages hold at most 200 records, and
# analytics data goes back 184 days.
AGGREGATION_PAGE_SIZE = 200
EXTENSION_PAGE_SIZE = 1000
MAX_ANALYTICS_DAYS = 184


def call_counts_by_user(
    platform,
    time_from: datetime,
    time_to: datetime,
    time_zone: str = "America/New_York",
) -> dict[str, int]:
    """
    Total calls (inbound + outbound) per user extension ID in the range.

    Needs the app permission "Analytics" (rate group Light). Users with no
    calls may be missing from the result, so treat a missing ID as 0.
    """

    body = {
        "grouping": {"groupBy": "Users"},
        "timeSettings": {
            "timeZone": time_zone,
            "timeRange": {
                "timeFrom": time_from.isoformat(),
                "timeTo": time_to.isoformat(),
            },
        },
        "responseOptions": {"counters": {"allCalls": {"aggregationType": "Sum"}}},
    }

    counts: dict[str, int] = {}
    page = 1

    while True:
        data = platform.post(
            AGGREGATION_PATH,
            body,
            {"page": page, "perPage": AGGREGATION_PAGE_SIZE},
        ).json_dict()

        for record in (data.get("data") or {}).get("records") or []:
            all_calls = (record.get("counters") or {}).get("allCalls") or {}
            counts[str(record["key"])] = int(all_calls.get("values") or 0)

        if page >= (data.get("paging") or {}).get("totalPages", 1):
            return counts

        page += 1


def list_user_extensions(platform) -> list[dict]:
    """Every enabled extension of type User (licensed people). ReadAccounts."""

    extensions = []
    page = 1

    while True:
        data = platform.get(
            EXTENSION_PATH,
            {
                "type": "User",
                "status": "Enabled",
                "page": page,
                "perPage": EXTENSION_PAGE_SIZE,
            },
        ).json_dict()

        records = data.get("records") or []
        extensions.extend(records)

        total_pages = (data.get("paging") or {}).get("totalPages")
        if not records or (total_pages is not None and page >= total_pages):
            return extensions

        page += 1
