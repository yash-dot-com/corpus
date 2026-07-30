"""Application composition for the CLI and deployment entry points."""

from typing import Any, Optional
from uuid import uuid4

import boto3

from src.config_models import CrawlConfiguration
from src.coordinator import Coordinator, RobotsDownloader
from src.aws import HttpRobotsDownloader, SqsQueue
from src.exceptions import ConfigurationError
from src.fetcher import HttpFetcher


def compose_coordinator(
    configuration: CrawlConfiguration,
    environment: dict[str, str],
    sqs_client: Optional[Any] = None,
    robots_downloader: Optional[RobotsDownloader] = None,
    crawl_id: Optional[str] = None,
) -> Coordinator:
    """Compose a coordinator and its AWS-backed queue dependencies."""
    queue_url = environment.get("CORPORA_CRAWL_QUEUE_URL")
    if not queue_url:
        raise ConfigurationError("CORPORA_CRAWL_QUEUE_URL is required")

    if sqs_client is None:
        sqs_client = boto3.client("sqs")

    if robots_downloader is None:
        robots_downloader = HttpRobotsDownloader(
            HttpFetcher(user_agent=configuration.user_agent, timeout_seconds=10.0)
        )

    return Coordinator(
        configuration=configuration,
        job_queue=SqsQueue(client=sqs_client, queue_url=queue_url),
        robots_downloader=robots_downloader,
        crawl_id=crawl_id or str(uuid4()),
    )
