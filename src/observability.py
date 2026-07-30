"""Structured logging and backend-independent metrics hooks."""

import json
import logging
from typing import Protocol


class Metrics(Protocol):
    """Counter interface implemented by metrics backends."""

    def increment(self, name: str, value: int = 1) -> None:
        """Increment a named counter."""


class EventLogger(Protocol):
    """Structured event interface used by domain components."""

    def info(self, event: str, **fields: object) -> None:
        """Emit an informational structured event."""

    def error(self, event: str, **fields: object) -> None:
        """Emit an error structured event."""


class StructuredLogger:
    """Encode structured events as JSON through a standard logger."""

    def __init__(self, logger: logging.Logger) -> None:
        """Configure the underlying standard-library logger."""
        self._logger = logger

    def info(self, event: str, **fields: object) -> None:
        """Emit an informational JSON event."""
        self._logger.info(_event_json(event, fields))

    def error(self, event: str, **fields: object) -> None:
        """Emit an error JSON event."""
        self._logger.error(_event_json(event, fields))


class InMemoryMetrics:
    """Small counter backend for tests and local execution."""

    def __init__(self) -> None:
        """Initialize empty counters."""
        self._counters: dict[str, int] = {}

    def increment(self, name: str, value: int = 1) -> None:
        """Increment one counter by a positive or negative value."""
        self._counters[name] = self._counters.get(name, 0) + value

    def snapshot(self) -> dict[str, int]:
        """Return a copy of current counter values."""
        return dict(self._counters)


def _event_json(event: str, fields: dict[str, object]) -> str:
    """Serialize an event with stable key ordering."""
    return json.dumps({"event": event, **fields}, sort_keys=True)
