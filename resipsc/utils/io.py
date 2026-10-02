"""JSON / pickle IO helpers with atomic writes."""

from __future__ import annotations

import json
import os
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict


def _atomic_write(path: str, data: bytes) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(Path(path).parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def save_json(obj: Any, path: str) -> None:
    """Atomically write ``obj`` as pretty JSON."""
    payload = json.dumps(obj, indent=2, default=_json_default).encode("utf-8")
    _atomic_write(path, payload)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_pickle(obj: Any, path: str) -> None:
    """Atomically pickle ``obj``."""
    _atomic_write(path, pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))


def load_pickle(path: str) -> Any:
    with open(path, "rb") as fh:
        return pickle.load(fh)


def _json_default(o: Any) -> Any:
    """Coerce numpy / pandas scalars to native python for JSON serialisation."""
    import numpy as np

    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serialisable")
