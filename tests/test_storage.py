"""Tests for JSONL document and metadata persistence."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.storage import (
    InMemoryMetadataStore,
    LocalObjectStore,
    StorageMessage,
    StoragePersistenceError,
    StorageWorker,
)


def storage_message(url: str = "https://example.com/page") -> StorageMessage:
    """Create a representative Storage Queue message."""
    return StorageMessage(
        crawl_id="crawl-123",
        url=url,
        status_code=200,
        depth=2,
        document={
            "title": "Example page",
            "language": "en",
            "text": "Example text",
            "html": "<html><body>Example text</body></html>",
            "metadata": {"description": "Example", "keywords": ["example"]},
        },
        fetched_at="2026-07-30T10:00:00Z",
        processing_time_ms=213,
    )


def build_storage_worker(
    root_directory: Path,
) -> tuple[StorageWorker, InMemoryMetadataStore]:
    """Create a storage worker with deterministic local dependencies."""
    metadata_store = InMemoryMetadataStore()
    worker = StorageWorker(
        object_store=LocalObjectStore(root_directory),
        metadata_store=metadata_store,
        worker_id="17",
        clock=lambda: datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc),
    )
    return worker, metadata_store


def test_storage_worker_writes_a_jsonl_document_and_metadata(tmp_path: Path) -> None:
    """A Storage Queue message becomes one S3-compatible JSONL record and metadata."""
    worker, metadata_store = build_storage_worker(tmp_path)

    metadata = worker.persist(storage_message())

    assert metadata.crawl_id == "crawl-123"
    assert metadata.url == "https://example.com/page"
    assert metadata.depth == 2
    assert metadata.status == "SUCCESS"
    assert metadata.s3_key == "raw/2026-07-30/worker-17/output.jsonl"
    assert metadata_store.records == [metadata]

    output_path = tmp_path / metadata.s3_key
    assert [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()] == [
        {
            "crawl_id": "crawl-123",
            "url": "https://example.com/page",
            "status_code": 200,
            "depth": 2,
            "document": storage_message().document,
            "fetched_at": "2026-07-30T10:00:00Z",
            "processing_time_ms": 213,
        }
    ]


def test_storage_worker_appends_documents_to_the_same_worker_jsonl_file(
    tmp_path: Path,
) -> None:
    """A worker's documents share its daily JSONL object."""
    worker, _ = build_storage_worker(tmp_path)

    worker.persist(storage_message("https://example.com/one"))
    worker.persist(storage_message("https://example.com/two"))

    output_path = tmp_path / "raw/2026-07-30/worker-17/output.jsonl"
    records = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [record["url"] for record in records] == [
        "https://example.com/one",
        "https://example.com/two",
    ]


def test_storage_worker_does_not_store_metadata_when_document_write_fails() -> None:
    """Metadata cannot reference a document object that was not persisted."""
    metadata_store = InMemoryMetadataStore()
    worker = StorageWorker(
        object_store=FailingObjectStore(),
        metadata_store=metadata_store,
        worker_id="17",
        clock=lambda: datetime(2026, 7, 30, tzinfo=timezone.utc),
    )

    with pytest.raises(StoragePersistenceError):
        worker.persist(storage_message())

    assert metadata_store.records == []


class FailingObjectStore:
    """Object-store fake that rejects all write attempts."""

    def append_jsonl(self, key: str, record: dict[str, object]) -> None:
        """Raise a predictable storage failure for a unit test."""
        raise OSError("object storage unavailable")
