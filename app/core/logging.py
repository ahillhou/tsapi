import logging
import os


def configure_logging() -> None:
    """Send app logs to stdout so they show up in `docker logs`."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
