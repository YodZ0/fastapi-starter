import typer

from .commands.di import di_app
from .commands.system import system_app

cli_app = typer.Typer()
cli_app.add_typer(system_app, name="sys", help="System commands")
cli_app.add_typer(di_app, name="di", help="DI (dishka) commands")


if __name__ == "__main__":
    cli_app()
