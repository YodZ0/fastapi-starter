import logging
import logging.config

import yaml
from pathlib import Path

from src.settings import settings


def setup_logging(base_dir: Path) -> None:
    if not settings.debug:
        # Set libraries loggers level to WARNING
        for loud in (
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "asyncio",
            "fastapi",
        ):
            logging.getLogger(loud).setLevel(logging.WARNING)

    # Setup application logging
    files = [".logging.dev.yaml", ".logging.yaml"]
    for file in files:
        ls_file = base_dir / file
        if ls_file.exists():
            with open(ls_file, "rt") as f:
                config = yaml.safe_load(f.read())
            logging.config.dictConfig(config)
            break
    else:
        print(f"Missing configuration logging files: {', '.join(files)}")
        exit(0)
