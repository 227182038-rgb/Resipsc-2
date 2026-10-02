"""Logging helper for resipsc."""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger("resipsc")
    root.addHandler(handler)
    level = os.environ.get("RESIPSC_LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str = "resipsc") -> logging.Logger:
    """Return a namespaced logger under the resipsc root."""
    _configure_root()
    if not name.startswith("resipsc"):
        name = f"resipsc.{name}"
    return logging.getLogger(name)
