"""sitecustomize.py — interpreter-startup environment shim for resipsc (PART 3.1).

Restored 2026-10-04 after the platform reset /home/z/.venv (base image only,
ML stack + this file wiped). Canonical copy lives at
/home/z/my-project/scripts/sitecustomize.py — re-copy it into the venv
site-packages after any environment reset.

Why this exists:
  - The Next.js .env sets DATABASE_URL for Prisma. anndata's pydantic-settings
    stack reads it as a SQLite path and crashes on import.
  - pydantic-settings 2.13+ passes extra keyword args to
    Settings.settings_customise_sources that scverse_misc's signature does
    not accept -> TypeError at import time. We patch in a tolerant wrapper
    that also DROPS the dotenv source entirely (belt-and-suspenders with the
    env-var pop and with resipsc/__init__.py, which covers direct imports).
  - Suppress noisy FutureWarning/DeprecationWarning/UserWarning/RuntimeWarning
    so JSON API output stays clean.
"""

from __future__ import annotations

import os
import warnings

# 1) Remove Prisma's DATABASE_URL from this interpreter's environment.
os.environ.pop("DATABASE_URL", None)
os.environ.pop("DATABASE_URL_FILE", None)
os.environ["PYTHONWARNINGS"] = "ignore"

# 2) Warnings hygiene for subprocess JSON emission.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)


# 3) Patch scverse_misc.Settings.settings_customise_sources so it (a) accepts
#    the extra kwargs newer pydantic-settings passes and (b) drops the dotenv
#    source, which is what surfaces DATABASE_URL into anndata's settings.
def _patch_scverse_misc() -> None:
    try:
        import scverse_misc as _sm
    except Exception:  # not installed or not needed yet
        return

    _Settings = getattr(_sm, "Settings", None)
    if _Settings is None:
        return

    _orig = _Settings.__dict__.get("settings_customise_sources")
    if _orig is not None and getattr(_orig, "_resipsc_patched", False):
        return  # already patched (double import safety)

    def _customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings, **kwargs):
        # Drop the dotenv source; keep init/env/file-secret precedence.
        return (init_settings, env_settings, file_secret_settings)

    _customise_sources._resipsc_patched = True
    _customise_sources.__name__ = "settings_customise_sources"
    _Settings.settings_customise_sources = classmethod(_customise_sources)


_patch_scverse_misc()
