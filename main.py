import typer
from pathlib import Path

from src.yaml_parser import load_config

app = typer.Typer()


@app.command()
def crawl(config: Path) -> None:
    """Load and display the crawl configuration."""
    cfg = load_config(config)
    print(cfg)


if __name__ == "__main__":
    app()
