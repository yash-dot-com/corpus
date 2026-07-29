"""
Contract tests for the crawl coordinator.
These tests intentionally precede the coordinator implementation.
"""

import json
from datetime import datetime, timezone
from typing import Callable, Optional
from pathlib import Path
from src.config_models import CrawlConfiguration
from src.coordinator import Coordinator


class FakeCrawlJobQueue:
    """Capture JSON crawl jobs that the coordinator sends to SQS."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def enqueue_batch(self, job_bodies: list[str]) -> None:
        """Record one submitted batch of serialized crawl jobs."""
        self.batches.append(job_bodies)


class FakeRobotsDownloader:
    """Return fixed robots documents and record requested origins."""

    def __init__(self, robots_document: str) -> None:
        self.robots_document = robots_document
        self.requested_urls: list[str] = []

    def download(self, robots_url: str) -> str:
        """Record the request and return the configured robots document."""
        self.requested_urls.append(robots_url)
        return self.robots_document


def build_configuration(max_depth: int = 2) -> CrawlConfiguration:
    """Create a valid configuration for coordinator tests."""
    return CrawlConfiguration(
        seed_urls=["https://example.com"],
        allowed_domains=["example.com"],
        max_depth=max_depth,
        user_agent="corpora/0.1",
        output_directory=Path("./output"),
    )


def build_coordinator(
    max_depth: int = 2,
    robots_document: str = "User-agent: *\nAllow: /\n",
    job_id_factory: Optional[Callable[[], str]] = None,
) -> tuple[Coordinator, FakeCrawlJobQueue, FakeRobotsDownloader]:
    """Create a coordinator with isolated queue and robots dependencies."""
    queue = FakeCrawlJobQueue()
    robots_downloader = FakeRobotsDownloader(robots_document)
    coordinator = Coordinator(
        configuration=build_configuration(max_depth),
        job_queue=queue,
        robots_downloader=robots_downloader,
        crawl_id="crawl-123",
        job_id_factory=job_id_factory or (lambda: "job-123"),
        clock=lambda: datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc),
    )
    return coordinator, queue, robots_downloader


def queued_jobs(queue: FakeCrawlJobQueue) -> list[dict[str, object]]:
    """Deserialize every queued crawl job for assertions."""
    return [json.loads(job) for batch in queue.batches for job in batch]


def schedule(
    coordinator: Coordinator,
    url: str,
    depth: int,
    discovered_from: Optional[str],
) -> bool:
    """Schedule a candidate URL through the coordinator's public API."""
    return coordinator.schedule(
        url=url,
        depth=depth,
        discovered_from=discovered_from,
    )


def test_coordinator_queues_a_verified_canonical_seed_job() -> None:
    """A verified seed is emitted as the documented JSON crawl-job contract."""
    coordinator, queue, robots_downloader = build_coordinator()

    accepted = schedule(
        coordinator,
        "HTTPS://EXAMPLE.COM:443/start?b=2&a=1#intro",
        depth=0,
        discovered_from=None,
    )
    coordinator.flush()

    assert accepted is True
    assert robots_downloader.requested_urls == ["https://example.com/robots.txt"]
    assert queued_jobs(queue) == [
        {
            "job_id": "job-123",
            "crawl_id": "crawl-123",
            "url": "https://example.com/start?a=1&b=2",
            "depth": 0,
            "discovered_from": None,
            "discovered_at": "2026-07-29T12:00:00Z",
        }
    ]


def test_coordinator_creates_unique_job_ids() -> None:
    """Each scheduled URL receives its own execution identifier."""
    job_ids = iter(["job-1", "job-2"])
    coordinator, queue, _ = build_coordinator(job_id_factory=lambda: next(job_ids))

    assert schedule(coordinator, "https://example.com/first", 0, None)
    assert schedule(coordinator, "https://example.com/second", 0, None)
    coordinator.flush()

    assert [job["job_id"] for job in queued_jobs(queue)] == ["job-1", "job-2"]


def test_coordinator_allows_configured_domains_and_subdomains() -> None:
    """An allowed domain includes its subdomains but not hostname lookalikes."""
    coordinator, queue, _ = build_coordinator()

    assert schedule(coordinator, "https://docs.example.com/guide", 1, "https://example.com")
    assert not schedule(coordinator, "https://example.com.evil.test", 1, "https://example.com")
    coordinator.flush()

    assert [job["url"] for job in queued_jobs(queue)] == [
        "https://docs.example.com/guide"
    ]


def test_coordinator_rejects_duplicate_canonical_urls() -> None:
    """URLs that canonicalize identically produce only one crawl job."""
    coordinator, queue, _ = build_coordinator()

    assert schedule(coordinator, "https://example.com/page?b=2&a=1", 1, None)
    assert not schedule(coordinator, "https://example.com/page?a=1&b=2#section", 1, None)
    coordinator.flush()

    assert len(queued_jobs(queue)) == 1


def test_coordinator_enforces_maximum_crawl_depth() -> None:
    """URLs at the configured limit are accepted but deeper URLs are rejected."""
    coordinator, queue, _ = build_coordinator(max_depth=1)

    assert schedule(coordinator, "https://example.com/allowed", 1, None)
    assert not schedule(coordinator, "https://example.com/too-deep", 2, None)
    coordinator.flush()

    assert [job["url"] for job in queued_jobs(queue)] == [
        "https://example.com/allowed"
    ]


def test_coordinator_rejects_invalid_and_unsupported_urls() -> None:
    """Invalid candidates never reach robots evaluation or the SQS queue."""
    coordinator, queue, robots_downloader = build_coordinator()

    assert not schedule(coordinator, "https://", 0, None)
    assert not schedule(coordinator, "ftp://example.com/file", 0, None)
    coordinator.flush()

    assert robots_downloader.requested_urls == []
    assert queued_jobs(queue) == []


def test_coordinator_caches_robots_policy_per_host() -> None:
    """Later URLs from one host reuse the previously downloaded robots policy."""
    coordinator, queue, robots_downloader = build_coordinator()

    assert schedule(coordinator, "https://example.com/first", 0, None)
    assert schedule(coordinator, "https://example.com/second", 0, None)
    coordinator.flush()

    assert robots_downloader.requested_urls == ["https://example.com/robots.txt"]
    assert len(queued_jobs(queue)) == 2


def test_coordinator_rejects_urls_disallowed_by_robots_policy() -> None:
    """Protego rules are enforced before an SQS job is created."""
    coordinator, queue, _ = build_coordinator(
        robots_document="User-agent: *\nDisallow: /private\n",
    )

    assert not schedule(coordinator, "https://example.com/private/report", 0, None)
    coordinator.flush()

    assert queued_jobs(queue) == []


def test_coordinator_sends_jobs_in_batches_of_ten() -> None:
    """The coordinator submits the configured maximum of ten jobs per batch."""
    coordinator, queue, _ = build_coordinator()

    for number in range(11):
        assert schedule(coordinator, f"https://example.com/page-{number}", 0, None)

    coordinator.flush()

    assert [len(batch) for batch in queue.batches] == [10, 1]
