"""
Logging setup.

The whole application is configured from one YAML file in the project root.
Verbosity is not stored in that file: `$log_level` is substituted from the
settings, so there is no need for a near identical per environment copy.
"""

import logging
import logging.config
from pathlib import Path
from string import Template
from typing import Any

import yaml

from src.settings import settings

LOGGING_CONFIG_FILENAME = ".logging.yaml"


def setup_logging(base_dir: Path, log_level: str | None = None) -> None:
    """
    Configure logging from the YAML config placed in base_dir.

    The level defaults to DEBUG in debug mode and to INFO otherwise.
    Raises FileNotFoundError if the config file is missing and ValueError if
    the level is unknown.
    """
    config_path = base_dir / LOGGING_CONFIG_FILENAME
    if not config_path.is_file():
        raise FileNotFoundError(f"Missing logging configuration file: {config_path}")

    level = (log_level or ("DEBUG" if settings.debug else "INFO")).upper()
    if level not in logging.getLevelNamesMapping():
        raise ValueError(f"Unknown logging level: {level!r}")

    # substitute(), not safe_substitute(): a typo in a placeholder name has to
    # fail loudly instead of reaching dictConfig as a literal "$log_level".
    template = Template(config_path.read_text(encoding="utf-8"))
    config: dict[str, Any] = yaml.safe_load(template.substitute(log_level=level))
    logging.config.dictConfig(config)
