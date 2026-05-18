"""File (+ optional stderr) logging for the Godot-spawned solo socket server."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_log_path() -> Path:
    override = os.environ.get("REALM_LOG_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return _engine_root() / "logs" / "realm_solo.log"


def _parse_level(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


def configure_solo_logging() -> Path:
    """
    Attach rotating file logging under ``engine/logs/realm_solo.log`` (override with
  ``REALM_LOG_FILE``). Level from ``REALM_LOG_LEVEL`` (default ``INFO``).

    Set ``REALM_LOG_STDERR=1`` to also mirror logs to stderr (useful when running
    ``realm_solo.py`` manually in a terminal).
    """
    global _CONFIGURED
    log_path = default_log_path()
    if _CONFIGURED:
        return log_path

    log_path.parent.mkdir(parents=True, exist_ok=True)
    level = _parse_level(os.environ.get("REALM_LOG_LEVEL", "INFO"))
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)

    if os.environ.get("REALM_LOG_STDERR", "").strip() in ("1", "true", "yes"):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(fmt)
        stderr_handler.setLevel(level)
        root.addHandler(stderr_handler)

    # Per-request lines from the solo socket (GET /world/map timing, errors, …).
    logging.getLogger("realm.socket_server.request").setLevel(level)
    logging.getLogger("realm.socket_server").setLevel(level)

    _CONFIGURED = True
    logging.getLogger("realm.solo").info("solo logging → %s", log_path)
    return log_path
