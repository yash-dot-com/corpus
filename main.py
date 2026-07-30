import typer
from pathlib import Path
from uuid import uuid4

from src.composition import compose_coordinator
from src.environment import load_dotenv
from src.yaml_parser import load_config

app = typer.Typer()


@app.command()
def crawl(
    config: Path,
    env_file: Path = typer.Option(Path(".env"), "--env-file"),
) -> None:
    """Compose the coordinator and schedule configured seed URLs."""
    cfg = load_config(config)
    environment = load_dotenv(env_file)
    coordinator = compose_coordinator(
        cfg,
        environment,
        crawl_id=str(uuid4()),
    )
    scheduled_count = sum(
        coordinator.schedule(url, depth=0, discovered_from=None)
        for url in cfg.seed_urls
    )
    coordinator.flush()
    typer.echo(f"Scheduled {scheduled_count} seed URL(s).")


if __name__ == "__main__":
    app()
