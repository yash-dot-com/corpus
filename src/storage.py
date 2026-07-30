"""JSONL document and metadata persistence for Corpora."""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol


class StoragePersistenceError(Exception):
    """Raised when a document or its metadata cannot be persisted."""


@dataclass(frozen=True)
class StorageMessage:
    """Persistence data derived from a worker result."""

    crawl_id: str
    url: str
    status_code: int
    depth: int
    document: dict[str, object]
    fetched_at: str
    processing_time_ms: int

    def to_dict(self) -> dict[str, object]:
        """Return the JSONL record written to object storage."""
        return {
            "crawl_id": self.crawl_id,
            "url": self.url,
            "status_code": self.status_code,
            "depth": self.depth,
            "document": self.document,
            "fetched_at": self.fetched_at,
            "processing_time_ms": self.processing_time_ms,
        }


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata that points from a document record to its object-store key."""

    crawl_id: str
    url: str
    status_code: int
    depth: int
    s3_key: str
    status: str


class ObjectStore(Protocol):
    """Append-only object storage for JSONL records."""

    def append_jsonl(self, key: str, record: dict[str, object]) -> None:
        """Append one JSON-serializable record to an object key."""


class MetadataStore(Protocol):
    """Persistent metadata repository for stored documents."""

    def save(self, metadata: DocumentMetadata) -> None:
        """Save one metadata record."""


class LocalObjectStore:
    """Filesystem-backed object store used for local execution and tests."""

    def __init__(self, root_directory: Path) -> None:
        """Store object keys relative to the supplied local root directory."""
        self._root_directory = root_directory

    def append_jsonl(self, key: str, record: dict[str, object]) -> None:
        """Append a JSON record followed by a newline to the local object key."""
        output_path = self._root_directory / key
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("a", encoding="utf-8") as output_file:
            output_file.write(json.dumps(record, ensure_ascii=False))
            output_file.write("\n")


class InMemoryMetadataStore:
    """Metadata store used for local execution and tests."""

    def __init__(self) -> None:
        """Initialize an empty metadata collection."""
        self.records: list[DocumentMetadata] = []

    def save(self, metadata: DocumentMetadata) -> None:
        """Record metadata in insertion order."""
        self.records.append(metadata)


class StorageWorker:
    """Persist Storage Queue messages through object and metadata stores."""

    def __init__(
        self,
        object_store: ObjectStore,
        metadata_store: MetadataStore,
        worker_id: str,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure persistence dependencies and the worker's object-key prefix."""
        self._object_store = object_store
        self._metadata_store = metadata_store
        self._worker_id = worker_id
        self._clock = clock

    def persist(self, message: StorageMessage) -> DocumentMetadata:
        """Write a document record before saving metadata that references it."""
        s3_key = self._object_key()
        try:
            self._object_store.append_jsonl(s3_key, message.to_dict())
        except OSError as error:
            raise StoragePersistenceError(
                f"Unable to persist document for URL: {message.url}"
            ) from error

        metadata = DocumentMetadata(
            crawl_id=message.crawl_id,
            url=message.url,
            status_code=message.status_code,
            depth=message.depth,
            s3_key=s3_key,
            status=_status(message.status_code),
        )
        try:
            self._metadata_store.save(metadata)
        except OSError as error:
            raise StoragePersistenceError(
                f"Unable to persist metadata for URL: {message.url}"
            ) from error

        return metadata

    def _object_key(self) -> str:
        """Build the date- and worker-partitioned key used for JSONL output."""
        date = self._clock().astimezone(timezone.utc).date().isoformat()
        return f"raw/{date}/worker-{self._worker_id}/output.jsonl"


def _status(status_code: int) -> str:
    """Map an HTTP status code to the stored document status."""
    return "SUCCESS" if 200 <= status_code < 300 else "HTTP_ERROR"
