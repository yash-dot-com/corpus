"""Crawl scheduling and state management for Corpora."""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from protego import Protego

from src.config_models import CrawlConfiguration
from src.urls import InvalidURLException, UnsupportedSchemeError, canonicalize, normalize, validate


SQS_BATCH_SIZE = 10

@dataclass(frozen=True)
class CrawlJob:
    """
    A verified crawl request sent from the coordinator to a worker / enqueued in the SQS queue
    """

    job_id: str
    crawl_id: str
    url: str
    depth: int
    discovered_from: Optional[str]
    discovered_at: str

    def to_json(self) -> str:
        """Serialize this job into the worker message contract."""
        return json.dumps(asdict(self))


class CrawlJobQueue(Protocol):
    """Destination for batches of serialized crawl jobs."""

    def enqueue_batch(self, job_bodies: list[str]) -> None:
        """Enqueue a batch of serialized crawl jobs."""


class RobotsDownloader(Protocol):
    """Downloader used by the coordinator to retrieve robots.txt documents."""

    def download(self, robots_url: str) -> str:
        """Download the robots.txt document at the supplied URL."""


class Coordinator:
    """Own in-memory crawl state and submit verified jobs to the queue."""

    def __init__(
        self,
        configuration: CrawlConfiguration,
        job_queue: CrawlJobQueue,
        robots_downloader: RobotsDownloader,
        crawl_id: str,
        job_id_factory: Callable[[], str] = lambda: str(uuid4()),
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Initialize the coordinator with its configuration and dependencies."""
        self._configuration = configuration
        self._job_queue = job_queue
        self._robots_downloader = robots_downloader
        self._crawl_id = crawl_id
        self._job_id_factory = job_id_factory
        self._clock = clock
        self._visited_urls: set[str] = set()
        self._robots_policies: dict[str, Protego] = {}
        self._pending_jobs: list[CrawlJob] = []

    def schedule(
        self,
        url: str,
        depth: int,
        discovered_from: Optional[str],
    ) -> bool:
        """Verify a candidate URL and queue it when it satisfies crawl rules."""
        try:
            validate(url)
            canonical_url = canonicalize(normalize(url))
        except (InvalidURLException, UnsupportedSchemeError):
            return False

        if depth > self._configuration.max_depth:
            return False

        if not self._is_allowed_domain(canonical_url):
            return False

        if canonical_url in self._visited_urls:
            return False

        if not self._is_allowed_by_robots(canonical_url):
            return False

        self._visited_urls.add(canonical_url)
        self._pending_jobs.append(
            CrawlJob(
                job_id=self._job_id_factory(),
                crawl_id=self._crawl_id,
                url=canonical_url,
                depth=depth,
                discovered_from=discovered_from,
                discovered_at=_format_timestamp(self._clock()),
            )
        )

        if len(self._pending_jobs) == SQS_BATCH_SIZE:
            self._enqueue_pending_jobs()

        return True

    def flush(self) -> None:
        """Submit all verified jobs that have not filled an SQS batch yet."""
        if self._pending_jobs:
            self._enqueue_pending_jobs()

    def _is_allowed_domain(self, url: str) -> bool:
        """Return whether the URL host is an allowed domain or its subdomain."""
        hostname = urlparse(url).hostname
        if hostname is None:
            return False

        normalized_hostname = hostname.lower().rstrip(".")
        return any(
            normalized_hostname == domain.lower().rstrip(".")
            or normalized_hostname.endswith(f".{domain.lower().rstrip('.')}")
            for domain in self._configuration.allowed_domains
        )

    def _is_allowed_by_robots(self, url: str) -> bool:
        """Return whether the cached or downloaded robots policy permits the URL."""
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname is None:
            return False

        policy = self._robots_policies.get(hostname)
        if policy is None:
            robots_url = urlunparse(
                (parsed.scheme, parsed.netloc, "/robots.txt", "", "", "")
            )
            policy = Protego.parse(self._robots_downloader.download(robots_url))
            self._robots_policies[hostname] = policy

        return policy.can_fetch(url, self._configuration.user_agent)

    def _enqueue_pending_jobs(self) -> None:
        """Serialize and submit one pending SQS batch without dropping failures."""
        job_bodies = [job.to_json() for job in self._pending_jobs]
        self._job_queue.enqueue_batch(job_bodies)
        self._pending_jobs.clear()


def _format_timestamp(value: datetime) -> str:
    """Format a timestamp as a UTC ISO 8601 string for a crawl job."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
