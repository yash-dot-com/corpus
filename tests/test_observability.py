"""Tests for structured events and metrics hooks."""

import json
import logging

from src.observability import InMemoryMetrics, StructuredLogger


def test_structured_logger_emits_json_events(caplog: object) -> None:
    """Structured events are machine-readable while using stdlib logging."""
    logger = logging.getLogger("corpora.test")
    structured_logger = StructuredLogger(logger)

    with caplog.at_level(logging.INFO, logger="corpora.test"):  # type: ignore[attr-defined]
        structured_logger.info("worker.completed", job_id="job-123", status_code=200)

    event = json.loads(caplog.records[0].message)  # type: ignore[attr-defined]
    assert event == {
        "event": "worker.completed",
        "job_id": "job-123",
        "status_code": 200,
    }


def test_in_memory_metrics_tracks_counter_values() -> None:
    """The in-memory implementation provides deterministic test metrics."""
    metrics = InMemoryMetrics()

    metrics.increment("worker.started")
    metrics.increment("worker.started", value=2)

    assert metrics.snapshot() == {"worker.started": 3}
