"""Tests for AWS queue and object-storage adapters."""

from botocore.exceptions import ClientError
from typing import Optional
import pytest

from src.aws import S3ObjectStore, SqsQueue, QueuePublishError


class FakeSqsClient:
    """Capture SQS batch requests."""

    def __init__(self, failures: Optional[list[dict[str, str]]] = None) -> None:
        self.requests: list[dict[str, object]] = []
        self.failures = failures or []

    def send_message_batch(self, **request: object) -> dict[str, object]:
        """Record one SQS send request."""
        self.requests.append(request)
        return {"Successful": [], "Failed": self.failures}


class FakeS3Client:
    """Capture S3 reads and writes in memory."""

    def __init__(self, existing_body: Optional[bytes] = None) -> None:
        self.existing_body = existing_body
        self.put_requests: list[dict[str, object]] = []

    def get_object(self, **request: object) -> dict[str, object]:
        """Return an existing object or an S3 not-found error."""
        if self.existing_body is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "GetObject",
            )
        return {"Body": FakeBody(self.existing_body)}

    def put_object(self, **request: object) -> None:
        """Record an S3 write request."""
        self.put_requests.append(request)


class FakeBody:
    """Readable S3 response body."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        """Return the stored object bytes."""
        return self.body


def test_sqs_queue_splits_messages_into_batches_of_ten() -> None:
    """SQS receives no more than ten entries per request."""
    client = FakeSqsClient()
    queue = SqsQueue(client=client, queue_url="https://sqs.example/queue")

    queue.enqueue_batch([f"job-{number}" for number in range(12)])

    assert [len(request["Entries"]) for request in client.requests] == [10, 2]
    assert client.requests[0]["QueueUrl"] == "https://sqs.example/queue"
    assert client.requests[0]["Entries"][0] == {
        "Id": "message-1",
        "MessageBody": "job-0",
    }


def test_sqs_queue_raises_when_aws_reports_failed_messages() -> None:
    """Partial SQS failures are surfaced instead of being silently dropped."""
    client = FakeSqsClient(
        failures=[{"Id": "message-1", "Code": "InternalError", "Message": "retry"}]
    )
    queue = SqsQueue(client=client, queue_url="queue")

    with pytest.raises(QueuePublishError):
        queue.enqueue_batch(["job-0"])


def test_s3_object_store_creates_a_new_jsonl_object() -> None:
    """A missing S3 object is created with one JSONL record."""
    client = FakeS3Client()
    object_store = S3ObjectStore(client=client, bucket="corpora")

    object_store.append_jsonl("raw/output.jsonl", {"url": "https://example.com"})

    assert client.put_requests == [
        {
            "Bucket": "corpora",
            "Key": "raw/output.jsonl",
            "Body": b'{"url": "https://example.com"}\n',
            "ContentType": "application/x-ndjson",
        }
    ]


def test_s3_object_store_appends_to_an_existing_jsonl_object() -> None:
    """An existing S3 object is preserved when a new record is appended."""
    client = FakeS3Client(existing_body=b'{"url": "first"}\n')
    object_store = S3ObjectStore(client=client, bucket="corpora")

    object_store.append_jsonl("raw/output.jsonl", {"url": "second"})

    assert client.put_requests[0]["Body"] == (
        b'{"url": "first"}\n{"url": "second"}\n'
    )
