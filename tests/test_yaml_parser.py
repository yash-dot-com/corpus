"""Tests for YAML configuration loading."""

from pathlib import Path

import pytest

from src.config_models import CrawlConfiguration
from src.exceptions import ConfigurationFileError, ConfigurationValidationError
from src.yaml_parser import load_config


def write_configuration(path: Path, content: str) -> Path:
    """Write configuration content to a temporary YAML file."""
    path.write_text(content, encoding="utf-8")
    return path


def test_load_config_returns_validated_configuration(tmp_path: Path) -> None:
    """A valid YAML file is converted to the typed configuration model."""
    config_path = write_configuration(
        tmp_path / "config.yaml",
        """
seed_urls:
  - https://example.com
allowed_domains:
  - example.com
max_depth: 2
user_agent: corpora/0.1
output_directory: ./output
""",
    )

    configuration = load_config(config_path)

    assert isinstance(configuration, CrawlConfiguration)
    assert configuration.seed_urls == ["https://example.com"]
    assert configuration.allowed_domains == ["example.com"]
    assert configuration.max_depth == 2
    assert configuration.user_agent == "corpora/0.1"
    assert configuration.output_directory == Path("output")


def test_load_config_raises_file_error_for_missing_file(tmp_path: Path) -> None:
    """A missing configuration file is reported through the custom error."""
    with pytest.raises(ConfigurationFileError):
        load_config(tmp_path / "missing.yaml")


def test_load_config_raises_file_error_for_unreadable_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An operating-system read failure is reported through the custom error."""
    config_path = tmp_path / "config.yaml"

    def raise_read_error(*args: object, **kwargs: object) -> None:
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "open", raise_read_error)

    with pytest.raises(ConfigurationFileError):
        load_config(config_path)


def test_load_config_raises_file_error_for_empty_file(tmp_path: Path) -> None:
    """An empty YAML document cannot define crawl configuration."""
    config_path = write_configuration(tmp_path / "config.yaml", "")

    with pytest.raises(ConfigurationFileError):
        load_config(config_path)


def test_load_config_raises_file_error_for_malformed_yaml(tmp_path: Path) -> None:
    """Malformed YAML is reported without exposing parser implementation."""
    config_path = write_configuration(tmp_path / "config.yaml", "seed_urls: [")

    with pytest.raises(ConfigurationFileError):
        load_config(config_path)


@pytest.mark.parametrize(
    "content",
    [
        "seed_urls: []\n",
        "- https://example.com\n",
    ],
)
def test_load_config_raises_validation_error_for_invalid_data(
    tmp_path: Path,
    content: str,
) -> None:
    """Valid YAML with an invalid schema is rejected consistently."""
    config_path = write_configuration(tmp_path / "config.yaml", content)

    with pytest.raises(ConfigurationValidationError):
        load_config(config_path)
