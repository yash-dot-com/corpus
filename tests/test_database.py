"""Tests for RDS metadata persistence."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.database import Base, DocumentMetadataRecord, SqlAlchemyMetadataStore
from src.storage import DocumentMetadata


def test_sqlalchemy_metadata_store_persists_document_metadata() -> None:
    """Metadata is stored in RDS-compatible relational fields."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    store = SqlAlchemyMetadataStore(lambda: Session(engine))

    store.save(
        DocumentMetadata(
            crawl_id="crawl-123",
            url="https://example.com/page",
            status_code=200,
            depth=2,
            s3_key="raw/output.jsonl",
            status="SUCCESS",
        )
    )

    with Session(engine) as session:
        record = session.scalar(select(DocumentMetadataRecord))

    assert record is not None
    assert record.url == "https://example.com/page"
    assert record.domain == "example.com"
    assert record.depth == 2
    assert record.s3_key == "raw/output.jsonl"
    assert record.status == "SUCCESS"
