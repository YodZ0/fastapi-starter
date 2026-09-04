from src.bootstrap import create_app
from src.settings import settings

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="src.main:app",
        host=settings.run.host,
        port=settings.run.port,
        workers=settings.run.workers,
        reload=settings.run.reload,
        log_config=None,
    )
