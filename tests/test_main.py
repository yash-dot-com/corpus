"""Tests for the command-line interface."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import main


runner = CliRunner()

def test_crawl_loads_configuration_from_required_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The CLI delegates the supplied path to the configuration loader."""
    config_path = tmp_path / "config.yaml"
    loaded_paths: list[Path] = []
    configuration = {"seed_urls": ["https://example.com"]}

    def load_test_configuration(path: Path) -> dict[str, list[str]]:
        loaded_paths.append(path)
        return configuration

    monkeypatch.setattr(main, "load_config", load_test_configuration)

    result = runner.invoke(main.app, [str(config_path)])

    assert result.exit_code == 0
    assert loaded_paths == [config_path]
    assert result.stdout == f"{configuration}\n"


def test_crawl_requires_configuration_path() -> None:
    """The CLI rejects invocations that omit the configuration path."""
    result = runner.invoke(main.app, [])

    assert result.exit_code == 2
    assert "Missing argument 'CONFIG'" in result.stdout
