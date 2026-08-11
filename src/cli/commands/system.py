import typer

system_app = typer.Typer()


@system_app.command(name="check", help="Check CLI status.")
def check_status() -> None:
    try:
        typer.echo("CLI is working!")
    except Exception as e:
        typer.echo(f"An error occurred: {e}")
        raise typer.Exit(1) from e
