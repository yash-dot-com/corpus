"""Relational metadata persistence for Corpora."""

from typing import Callable
from urllib.parse import urlparse

from sqlalchemy import Integer, String
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.storage import DocumentMetadata, StoragePersistenceError


class Base(DeclarativeBase):
    """Base class for Corpora relational models."""


class DocumentMetadataRecord(Base):
    """RDS record pointing to a document stored in S3."""

    __tablename__ = "document_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crawl_id: Mapped[str] = mapped_column(String(128), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class SqlAlchemyMetadataStore:
    """Persist document metadata through an injected SQLAlchemy session factory."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        """Configure the session factory used for each metadata write."""
        self._session_factory = session_factory

    def save(self, metadata: DocumentMetadata) -> None:
        """Insert and commit one document metadata record."""
        session = self._session_factory()
        record = DocumentMetadataRecord(
            crawl_id=metadata.crawl_id,
            url=metadata.url,
            domain=urlparse(metadata.url).hostname or "",
            status_code=metadata.status_code,
            depth=metadata.depth,
            s3_key=metadata.s3_key,
            status=metadata.status,
        )
        try:
            session.add(record)
            session.commit()
        except SQLAlchemyError as error:
            session.rollback()
            raise StoragePersistenceError(
                f"Unable to persist metadata for URL: {metadata.url}"
            ) from error
        finally:
            session.close()
