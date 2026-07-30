"""Tests for local environment-file loading."""

from pathlib import Path

from src.environment import load_dotenv


def test_load_dotenv_reads_comments_exports_and_quoted_values(tmp_path: Path) -> None:
    """Environment files are parsed into a clean string mapping."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
# queue configuration
export CORPORA_CRAWL_QUEUE_URL="https://sqs.example/queue"
CORPORA_AWS_REGION=us-east-1
""",
        encoding="utf-8",
    )

    assert load_dotenv(env_path) == {
        "CORPORA_CRAWL_QUEUE_URL": "https://sqs.example/queue",
        "CORPORA_AWS_REGION": "us-east-1",
    }


def test_load_dotenv_returns_empty_mapping_for_missing_file(tmp_path: Path) -> None:
    """A missing optional .env file does not crash configuration loading."""
    assert load_dotenv(tmp_path / ".env") == {}
