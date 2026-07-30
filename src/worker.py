"""Stateless crawl workers and WorkerResult fan-out."""

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from src.coordinator import CrawlJob
from src.fetcher import FetchResponse, HttpFetcher
from src.parser import parse
from src.observability import EventLogger, Metrics


class WorkerQueue(Protocol):
    """Queue destination for serialized worker messages."""

    def enqueue_batch(self, messages: list[str]) -> None:
        """Publish serialized messages to the queue."""


@dataclass(frozen=True)
class WorkerResult:
    """Complete internal result produced by one worker execution."""

    job_id: str
    crawl_id: str
    requested_url: str
    final_url: str
    redirect_chain: list[str]
    status_code: int
    content_type: Optional[str]
    depth: int
    document: Optional[dict[str, object]]
    links: list[str]
    fetched_at: str
    processing_time_ms: int

    def to_dict(self) -> dict[str, object]:
        """Return the complete JSON-ready worker result."""
        return asdict(self)


class Worker:
    """Fetch and parse one Crawl Queue job without owning crawl state."""

    def __init__(
        self,
        fetcher: HttpFetcher,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        monotonic: Callable[[], float] = time.monotonic,
        metrics: Optional[Metrics] = None,
        logger: Optional[EventLogger] = None,
    ) -> None:
        """Configure the fetcher and injectable timing functions."""
        self._fetcher = fetcher
        self._clock = clock
        self._monotonic = monotonic
        self._metrics = metrics
        self._logger = logger

    def process(self, job: CrawlJob) -> WorkerResult:
        """Fetch a job and parse its final successful HTML response."""
        if self._metrics is not None:
            self._metrics.increment("worker.jobs.started")
        started_at = self._monotonic()
        try:
            response = self._fetcher.fetch(job.url)
        except Exception:
            if self._metrics is not None:
                self._metrics.increment("worker.jobs.failed")
            if self._logger is not None:
                self._logger.error("worker.job.failed", job_id=job.job_id)
            raise
        document: Optional[dict[str, object]] = None
        links: list[str] = []

        if _is_successful_html(response):
            parsed_document = parse(response.content.decode("utf-8", errors="replace"))
            document = parsed_document.to_dict()
            links = parsed_document.links

        processing_time_ms = int(round((self._monotonic() - started_at) * 1000))
        result = WorkerResult(
            job_id=job.job_id,
            crawl_id=job.crawl_id,
            requested_url=response.requested_url,
            final_url=response.final_url,
            redirect_chain=response.redirect_chain,
            status_code=response.status_code,
            content_type=response.content_type,
            depth=job.depth,
            document=document,
            links=links,
            fetched_at=_format_timestamp(self._clock()),
            processing_time_ms=processing_time_ms,
        )
        if self._metrics is not None:
            self._metrics.increment("worker.jobs.succeeded")
        if self._logger is not None:
            self._logger.info(
                "worker.job.completed",
                job_id=result.job_id,
                status_code=result.status_code,
            )
        return result


class WorkerResultPublisher:
    """Derive and publish Storage Queue and Discovery Queue messages."""

    def __init__(
        self,
        storage_queue: WorkerQueue,
        discovery_queue: WorkerQueue,
    ) -> None:
        """Configure the two queue destinations for result fan-out."""
        self._storage_queue = storage_queue
        self._discovery_queue = discovery_queue

    def publish(self, result: WorkerResult) -> None:
        """Publish one persistence message and one discovery message."""
        if result.document is not None:
            storage_message = {
                "crawl_id": result.crawl_id,
                "url": result.final_url,
                "status_code": result.status_code,
                "depth": result.depth,
                "document": result.document,
                "fetched_at": result.fetched_at,
                "processing_time_ms": result.processing_time_ms,
            }
            self._storage_queue.enqueue_batch([json.dumps(storage_message)])

        discovery_message = {
            "job_id": result.job_id,
            "crawl_id": result.crawl_id,
            "requested_url": result.requested_url,
            "final_url": result.final_url,
            "parent_depth": result.depth,
            "links": result.links,
        }
        self._discovery_queue.enqueue_batch([json.dumps(discovery_message)])


def _is_successful_html(response: FetchResponse) -> bool:
    """Return whether a response should be parsed as an HTML document."""
    return (
        200 <= response.status_code < 300
        and response.content_type in {"text/html", "application/xhtml+xml"}
    )


def _format_timestamp(value: datetime) -> str:
    """Format a timestamp as a UTC ISO 8601 string."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
