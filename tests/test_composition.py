"""Tests for application composition."""

from pathlib import Path

import pytest

from src.composition import compose_coordinator
from src.config_models import CrawlConfiguration
from src.exceptions import ConfigurationError


class FakeSqsClient:
    """Placeholder client proving composition accepts injected AWS clients."""


class FakeRobotsDownloader:
    """Allow every URL without network access during composition tests."""

    def download(self, robots_url: str) -> str:
        """Return an unrestricted robots policy."""
        return "User-agent: *\nAllow: /\n"


def configuration() -> CrawlConfiguration:
    """Build valid configuration for composition tests."""
    return CrawlConfiguration(
        seed_urls=["https://example.com"],
        allowed_domains=["example.com"],
        max_depth=2,
        user_agent="corpora/0.1",
        output_directory=Path("output"),
    )


def test_compose_coordinator_builds_aws_backed_dependencies() -> None:
    """Composition creates a coordinator from config and environment values."""
    coordinator = compose_coordinator(
        configuration(),
        {"CORPORA_CRAWL_QUEUE_URL": "https://sqs.example/queue"},
        sqs_client=FakeSqsClient(),
        robots_downloader=FakeRobotsDownloader(),
        crawl_id="crawl-123",
    )

    assert coordinator is not None


def test_compose_coordinator_requires_the_crawl_queue_url() -> None:
    """Composition fails clearly when infrastructure configuration is absent."""
    with pytest.raises(ConfigurationError, match="CORPORA_CRAWL_QUEUE_URL"):
        compose_coordinator(
            configuration(),
            {},
            sqs_client=FakeSqsClient(),
            robots_downloader=FakeRobotsDownloader(),
            crawl_id="crawl-123",
        )
