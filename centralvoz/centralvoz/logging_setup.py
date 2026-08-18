"""Logging para console e arquivo rotativo."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .utils import ensure_dir

_CONSOLE_FORMAT = "%(asctime)s  %(levelname)-7s %(name)-22s %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s %(funcName)s: %(message)s"


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(_CONSOLE_FORMAT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    try:
        ensure_dir(log_dir)
        file_handler = RotatingFileHandler(
            log_dir / "centralvoz.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        root.addHandler(file_handler)
    except OSError as exc:  # cartao SD cheio, permissao, etc.
        root.warning("Nao consegui abrir o arquivo de log: %s", exc)

    # O gpiozero e barulhento demais no nivel DEBUG.
    logging.getLogger("gpiozero").setLevel(logging.WARNING)
