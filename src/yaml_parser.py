"""YAML configuration loading for Corpora."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from src.config_models import CrawlConfiguration
from src.exceptions import ConfigurationFileError, ConfigurationValidationError


def load_config(path: Path) -> CrawlConfiguration:
    """Load and validate crawl configuration from a YAML file.

    Raises:
        ConfigurationFileError: If the file cannot be read or parsed as YAML.
        ConfigurationValidationError: If the parsed data fails schema validation.
    """
    try:
        with path.open("r", encoding="utf-8") as config_file:
            configuration_data: Any = yaml.safe_load(config_file)
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationFileError(
            f"Unable to load configuration file: {path}"
        ) from error

    if configuration_data is None:
        raise ConfigurationFileError(f"Configuration file is empty: {path}")

    try:
        return CrawlConfiguration.model_validate(configuration_data)
    except ValidationError as error:
        raise ConfigurationValidationError(
            f"Configuration validation failed: {path}"
        ) from error
