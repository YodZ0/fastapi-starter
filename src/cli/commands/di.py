from pathlib import Path
from typing import Annotated

import typer
from dishka.plotter import render_mermaid

from src.di import setup_async_container
from src.settings import settings

di_app = typer.Typer()
DEFAULT_OUTPUT_DIR = settings.base_dir / "docs" / "di_graph.html"


@di_app.command(name="graph", help="Generate dishka dependency graph.")
def create_dependency_graph(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Output dir."),
    ] = DEFAULT_OUTPUT_DIR,
) -> None:
    container = setup_async_container()
    html_content = render_mermaid(container)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_content, encoding="utf-8")

    typer.echo(f"dishka graph has been created at {output!r}")
