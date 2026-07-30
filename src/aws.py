"""AWS queue and object-storage adapters."""

import json
from typing import Any

from botocore.exceptions import ClientError

from src.storage import StoragePersistenceError
from src.fetcher import HttpFetcher


class QueuePublishError(Exception):
    """Raised when an SQS batch cannot be published completely."""


class HttpRobotsDownloader:
    """Download robots.txt documents through the shared HTTP fetcher."""

    def __init__(self, fetcher: HttpFetcher) -> None:
        """Configure the HTTP dependency used for robots documents."""
        self._fetcher = fetcher

    def download(self, robots_url: str) -> str:
        """Return robots content, denying access when retrieval fails."""
        response = self._fetcher.fetch(robots_url)
        if not 200 <= response.status_code < 300:
            return "User-agent: *\nDisallow: /\n"
        return response.content.decode("utf-8", errors="replace")


class SqsQueue:
    """Publish serialized messages to an SQS queue in batches of ten."""

    def __init__(self, client: Any, queue_url: str) -> None:
        """Configure an injected boto3 SQS client and queue URL."""
        self._client = client
        self._queue_url = queue_url

    def enqueue_batch(self, job_bodies: list[str]) -> None:
        """Publish all messages, splitting them at the SQS batch limit."""
        for start in range(0, len(job_bodies), 10):
            batch = job_bodies[start : start + 10]
            entries = [
                {"Id": f"message-{index + 1}", "MessageBody": body}
                for index, body in enumerate(batch)
            ]
            try:
                response = self._client.send_message_batch(
                    QueueUrl=self._queue_url,
                    Entries=entries,
                )
            except ClientError as error:
                raise QueuePublishError("Unable to publish SQS batch") from error

            failures = response.get("Failed", [])
            if failures:
                raise QueuePublishError(f"SQS rejected messages: {failures}")


class S3ObjectStore:
    """Append JSONL records to an S3 object."""

    def __init__(self, client: Any, bucket: str) -> None:
        """Configure an injected boto3 S3 client and bucket name."""
        self._client = client
        self._bucket = bucket

    def append_jsonl(self, key: str, record: dict[str, object]) -> None:
        """Read, append, and rewrite one S3 JSONL object."""
        existing = self._read_existing(key)
        if existing and not existing.endswith(b"\n"):
            existing += b"\n"

        line = json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=existing + line,
                ContentType="application/x-ndjson",
            )
        except ClientError as error:
            raise StoragePersistenceError(
                f"Unable to write S3 object: {key}"
            ) from error

    def _read_existing(self, key: str) -> bytes:
        """Read an existing object, treating S3 not-found as an empty object."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            error_code = error.response.get("Error", {}).get("Code")
            if error_code not in {"NoSuchKey", "404", "NotFound"}:
                raise StoragePersistenceError(
                    f"Unable to read S3 object: {key}"
                ) from error
            return b""

        return response["Body"].read()
