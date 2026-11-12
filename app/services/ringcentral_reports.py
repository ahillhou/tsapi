"""Reports built from RingCentral data."""

import csv
import io
import logging
from datetime import datetime, timedelta, timezone

from app.clients.ringcentral import analytics
from app.clients.ringcentral.auth import get_platform

logger = logging.getLogger(__name__)

DEFAULT_UNUSED_DAYS = 180

UNUSED_COLUMNS = ["Extension", "Name", "Email", "Department", "Extension ID", "Calls"]


def unused_licenses(days: int = DEFAULT_UNUSED_DAYS, now: datetime | None = None) -> list[dict]:
    """
    Enabled RingCentral users with no calls (inbound or outbound) in the
    last `days` days. Sorted by department, then name.

    Only the last 184 days of call data exist, so `days` can't go past that.
    Users created during the window show up too if they haven't called yet.
    """

    if not 1 <= days <= analytics.MAX_ANALYTICS_DAYS:
        raise ValueError(f"days must be between 1 and {analytics.MAX_ANALYTICS_DAYS}")

    now = now or datetime.now(timezone.utc)
    platform = get_platform()

    users = analytics.list_user_extensions(platform)
    counts = analytics.call_counts_by_user(platform, now - timedelta(days=days), now)

    rows = []
    for user in users:
        user_id = str(user.get("id"))
        if counts.get(user_id, 0) > 0:
            continue

        contact = user.get("contact") or {}
        rows.append(
            {
                "Extension": user.get("extensionNumber") or "",
                "Name": user.get("name") or "",
                "Email": contact.get("email") or "",
                "Department": contact.get("department") or "",
                "Extension ID": user_id,
                "Calls": 0,
            }
        )

    rows.sort(key=lambda r: (r["Department"].lower(), r["Name"].lower()))

    logger.info(
        "Unused licenses: %d of %d users had no calls in %d days",
        len(rows),
        len(users),
        days,
    )

    return rows


def to_csv(rows: list[dict], columns: list[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows({k: _cell(v) for k, v in row.items()} for row in rows)
    return out.getvalue()


def _cell(value):
    """Stop Excel from running a name like "=HYPERLINK(...)" as a formula."""

    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value
