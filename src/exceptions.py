"""Custom exceptions for Corpora."""


class ConfigurationError(Exception):
    """Base exception for configuration failures."""


class ConfigurationFileError(ConfigurationError):
    """Raised when a configuration file cannot be read or parsed."""


class ConfigurationValidationError(ConfigurationError):
    """Raised when configuration data does not satisfy the schema."""
