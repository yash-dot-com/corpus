"""Tests for worker processing and WorkerResult fan-out."""

import json
from datetime import datetime, timezone
from typing import Optional

import httpx

from src.coordinator import CrawlJob
from src.fetcher import HttpFetcher
from src.observability import InMemoryMetrics
from src.worker import Worker, WorkerResult, WorkerResultPublisher


class FakeQueue:
    """Capture queue messages produced by a worker publisher."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def enqueue_batch(self, messages: list[str]) -> None:
        """Record serialized messages."""
        self.messages.extend(messages)


def build_job() -> CrawlJob:
    """Create a representative Crawl Queue job."""
    return CrawlJob(
        job_id="job-123",
        crawl_id="crawl-123",
        url="https://example.com/start",
        depth=2,
        discovered_from="https://example.com/index",
        discovered_at="2026-07-30T12:00:00Z",
    )


def build_worker(
    response_status: int = 200,
    content_type: Optional[str] = "text/html",
    metrics: Optional[InMemoryMetrics] = None,
) -> Worker:
    """Create a worker with deterministic mocked HTTP and timing dependencies."""
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(
            response_status,
            headers=headers,
            content=(
                b"<html lang='en'><title>Final</title>"
                b"<body><p>Hello worker</p><a href='/next'>Next</a></body></html>"
            ),
            request=request,
        )

    fetcher = HttpFetcher(
        user_agent="corpora/0.1",
        timeout_seconds=10.0,
        transport=httpx.MockTransport(handler),
    )
    timings = iter([100.0, 100.213])
    return Worker(
        fetcher=fetcher,
        clock=lambda: datetime(2026, 7, 30, 12, 1, tzinfo=timezone.utc),
        monotonic=lambda: next(timings),
        metrics=metrics,
    )


def test_worker_builds_one_result_from_fetch_and_parse() -> None:
    """A successful final page becomes the complete internal WorkerResult."""
    worker = build_worker()

    result = worker.process(build_job())

    assert isinstance(result, WorkerResult)
    assert result.job_id == "job-123"
    assert result.crawl_id == "crawl-123"
    assert result.requested_url == "https://example.com/start"
    assert result.final_url == "https://example.com/start"
    assert result.status_code == 200
    assert result.redirect_chain == ["https://example.com/start"]
    assert result.content_type == "text/html"
    assert result.depth == 2
    assert result.document["title"] == "Final"
    assert result.document["text"] == "Final Hello worker Next"
    assert result.links == ["/next"]
    assert result.fetched_at == "2026-07-30T12:01:00Z"
    assert result.processing_time_ms == 213


def test_worker_records_success_metric() -> None:
    """Successful processing increments started and succeeded counters."""
    metrics = InMemoryMetrics()
    worker = build_worker(metrics=metrics)

    worker.process(build_job())

    assert metrics.snapshot() == {
        "worker.jobs.started": 1,
        "worker.jobs.succeeded": 1,
    }


def test_worker_records_fetch_failure_metric() -> None:
    """Fetcher failures increment the failed counter and remain visible."""
    metrics = InMemoryMetrics()

    class FailingFetcher:
        def fetch(self, url: str) -> object:
            raise RuntimeError("network unavailable")

    worker = Worker(fetcher=FailingFetcher(), metrics=metrics)  # type: ignore[arg-type]

    try:
        worker.process(build_job())
    except RuntimeError as error:
        assert str(error) == "network unavailable"
    else:
        raise AssertionError("expected fetch failure")

    assert metrics.snapshot() == {
        "worker.jobs.started": 1,
        "worker.jobs.failed": 1,
    }


def test_worker_does_not_parse_unsuccessful_responses() -> None:
    """HTTP failures still produce status details but no parsed document."""
    worker = build_worker(response_status=404)

    result = worker.process(build_job())

    assert result.status_code == 404
    assert result.document is None
    assert result.links == []


def test_publisher_derives_storage_and_discovery_messages() -> None:
    """One WorkerResult fans out into two component-specific queue messages."""
    worker = build_worker()
    result = worker.process(build_job())
    storage_queue = FakeQueue()
    discovery_queue = FakeQueue()
    publisher = WorkerResultPublisher(storage_queue, discovery_queue)

    publisher.publish(result)

    assert json.loads(storage_queue.messages[0]) == {
        "crawl_id": "crawl-123",
        "url": "https://example.com/start",
        "status_code": 200,
        "depth": 2,
        "document": result.document,
        "fetched_at": "2026-07-30T12:01:00Z",
        "processing_time_ms": 213,
    }
    assert json.loads(discovery_queue.messages[0]) == {
        "job_id": "job-123",
        "crawl_id": "crawl-123",
        "requested_url": "https://example.com/start",
        "final_url": "https://example.com/start",
        "parent_depth": 2,
        "links": ["/next"],
    }
