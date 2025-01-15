import uvicorn

from src.bootstrap import create_app
from src.settings import settings

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.run.host,
        port=settings.run.port,
        reload=False,
    )
