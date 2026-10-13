
"""Structured, privacy-conscious event logging."""

import json
import logging
from typing import Any


LOGGER = logging.getLogger("validation_gateway")


def configure_logging(level: int = logging.INFO) -> None:
    """Configure standard-library logging for the application."""
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)

    LOGGER.setLevel(level)
    LOGGER.propagate = False


def emit_event(
    event: str,
    *,
    request_id: str,
    tool: str,
    status: str,
    stage: str | None = None,
) -> dict[str, Any]:
    """Emit only approved metadata; never log raw arguments or secrets."""
    record: dict[str, Any] = {
        "event": event,
        "request_id": request_id,
        "tool": tool,
        "status": status,
    }

    if stage is not None:
        record["stage"] = stage

    LOGGER.info(json.dumps(record, sort_keys=True))
    return record
