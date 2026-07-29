"""Typed configuration models for Corpora."""

from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
)


NonEmptyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class CrawlConfiguration(BaseModel):
    """Validated settings required to run a crawl."""

    model_config = ConfigDict(extra="forbid")

    seed_urls: list[NonEmptyString] = Field(min_length=1)
    allowed_domains: list[NonEmptyString] = Field(min_length=1)
    max_depth: StrictInt = Field(ge=0)
    user_agent: NonEmptyString
    output_directory: Path

    @field_validator("output_directory", mode="before")
    @classmethod
    def validate_output_directory(cls, value: object) -> object:
        """Reject an empty output directory before converting it to a path."""
        if isinstance(value, str) and not value.strip():
            raise ValueError("output_directory must not be empty")

        return value
