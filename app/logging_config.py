import json
import logging
import sys
from typing import Any


def configure_logging() -> None:
    """Ensure app.* loggers emit to stderr (uvicorn does not configure them by default)."""
    app_logger = logging.getLogger("app")
    if app_logger.handlers:
        return

    app_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(levelname)s %(name)s: %(message)s")
    )
    app_logger.addHandler(handler)
    app_logger.propagate = False


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    logger.info(json.dumps(payload, default=str))
