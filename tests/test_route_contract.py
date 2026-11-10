"""
The webhook URLs are configured by other teams (the TDX admin builds the
forms; RingCentral workflows are set up separately) and can't be changed
from here. If one of these tests fails, a live integration would break:
keep the old path working instead of renaming it.
"""

import pytest

from app.main import create_app

LIVE_WEBHOOKS = [
    ("POST", "/tdx/webhook"),
    ("POST", "/tdx/webhook/access_request"),
    ("POST", "/tdx/webhook/test_access_request"),
    ("POST", "/demo/dayoff"),
    ("POST", "/ringcentral/dnd"),
    ("POST", "/ringcentral/dayoff"),
    ("GET", "/health"),
]


def _routes(app):
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


@pytest.mark.parametrize("method, path", LIVE_WEBHOOKS)
def test_live_webhook_url_is_unchanged(method, path):
    assert (method, path) in _routes(create_app())


def test_secret_is_not_required_in_the_url():
    """Secrets go in a header so the TDX/RingCentral URLs never change."""

    from app.core import security

    assert security.HEADER_NAME == "X-Webhook-Secret"
