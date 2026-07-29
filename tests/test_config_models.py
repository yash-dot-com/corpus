"""Tests for typed crawl configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config_models import CrawlConfiguration
from src.exceptions import (
    ConfigurationError,
    ConfigurationFileError,
    ConfigurationValidationError,
)


def valid_configuration() -> dict[str, object]:
    """Return valid configuration data for model tests."""
    return {
        "seed_urls": ["https://example.com"],
        "allowed_domains": ["example.com"],
        "max_depth": 2,
        "user_agent": "corpora/0.1",
        "output_directory": "./output",
    }


def test_crawl_configuration_validates_all_supported_fields() -> None:
    """A complete configuration is represented with its expected types."""
    configuration = CrawlConfiguration.model_validate(valid_configuration())

    assert configuration.seed_urls == ["https://example.com"]
    assert configuration.allowed_domains == ["example.com"]
    assert configuration.max_depth == 2
    assert configuration.user_agent == "corpora/0.1"
    assert configuration.output_directory == Path("output")


@pytest.mark.parametrize(
    "field_name",
    [
        "seed_urls",
        "allowed_domains",
        "max_depth",
        "user_agent",
        "output_directory",
    ],
)
def test_crawl_configuration_requires_each_supported_field(field_name: str) -> None:
    """Every configuration setting needed by a crawl is required."""
    configuration = valid_configuration()
    del configuration[field_name]

    with pytest.raises(ValidationError):
        CrawlConfiguration.model_validate(configuration)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("seed_urls", []),
        ("allowed_domains", []),
        ("seed_urls", ["   "]),
        ("allowed_domains", [""]),
        ("max_depth", -1),
        ("max_depth", "2"),
        ("user_agent", "  "),
        ("output_directory", ""),
    ],
)
def test_crawl_configuration_rejects_invalid_field_values(
    field_name: str,
    value: object,
) -> None:
    """Invalid values are rejected before a crawl can begin."""
    configuration = valid_configuration()
    configuration[field_name] = value

    with pytest.raises(ValidationError):
        CrawlConfiguration.model_validate(configuration)


@pytest.mark.parametrize(
    "error_type",
    [ConfigurationFileError, ConfigurationValidationError],
)
def test_configuration_errors_share_a_common_base(
    error_type: type[ConfigurationError],
) -> None:
    """Configuration callers can handle all configuration failures together."""
    assert isinstance(error_type("message"), ConfigurationError)


def test_crawl_configuration_rejects_unknown_fields() -> None:
    """Unexpected configuration keys are rejected to catch misspellings."""
    configuration = valid_configuration()
    configuration["max_dept"] = 2

    with pytest.raises(ValidationError):
        CrawlConfiguration.model_validate(configuration)
