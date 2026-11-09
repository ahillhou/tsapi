from typing import Any

from pydantic import BaseModel, ConfigDict


class TDXWebhook(BaseModel):
    """
    Body TDX sends to our webhooks: {"data": <ticket>, ...}.

    The ticket is kept as a plain dict because its shape (custom
    attributes in particular) varies per form.
    """

    model_config = ConfigDict(extra="allow")

    data: dict[str, Any]
