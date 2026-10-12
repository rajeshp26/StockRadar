#!/usr/bin/env python3
"""Config-driven location resolution for the framework (Phase A patch A1).

The framework must never assume where the app lives. It reads the app root, the
state folder, and gate settings from ONE config file - ``framework.config.json`` -
found by walking up from the current working directory. When no config exists
(the in-repo / legacy layout) it falls back to the historical repo-relative
behaviour, so every existing caller keeps working unchanged.

Resolution is split deliberately:

  * app-controlled   -> config-driven    : app_root, state_root, gate_settings, readiness
  * framework-owned  -> package-relative : framework_root, surface_root

``framework_root()`` is ALWAYS ``Path(__file__).parent`` (where the installed
``framework`` package lives). It never consults the config, so the framework can
locate its own surface regardless of where it is installed or where the app lives.

Legacy fallback contract (this is what makes A2 a behaviour-preserving patch):
  no config present  =>  app_root() == the directory that CONTAINS the framework
                         package (the repo root in-tree; site-packages when
                         installed), and state_root() == <app_root>/.planning.
  With no ``framework.config.json`` in the tree, A2's rewires are byte-for-byte
  equivalent to the ``Path(__file__).resolve().parents[2]`` they replace, so
  ``python framework/validate.py`` must stay green (41/41) after A2.

Public API:
    find_config()          -> Path | None
    config_path()          -> Path | None
    app_root()             -> Path
    state_root()           -> Path
    manifest_dir()         -> Path
    framework_root()       -> Path
    surface_root()         -> Path
    gate_settings()        -> dict
    readiness()            -> dict
    bootstrap_sys_path()   -> Path   (legacy/direct-run import support)
"""
from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

CONFIG_NAME = "framework.config.json"
CONFIG_ENV = "FRAMEWORK_CONFIG"
LEGACY_STATE_FOLDER = ".planning"

# Directory that CONTAINS the `framework` package: site-packages when installed,
# the repository root when running in-tree.
#   framework/locate.py -> .parent = framework/ -> .parent.parent = the root.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent


def find_config(start: Path | None = None) -> Path | None:
    """The ``framework.config.json`` governing this invocation, or None.

    Order: explicit ``FRAMEWORK_CONFIG`` override first, then walk up from
    ``start`` (default: the current working directory) to the filesystem root;
    the first hit wins.
    """
    override = os.environ.get(CONFIG_ENV)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_file() else None
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / CONFIG_NAME
        if candidate.is_file():
            return candidate
    return None


@lru_cache(maxsize=1)
def _config() -> dict:
    """Parsed config, cached per process. Empty dict when absent or malformed.

    A malformed config is treated as absent rather than fatal: the legacy
    fallback keeps the framework runnable, and a hard failure here would take
    down every gate over a single typo. Callers that need strictness validate
    the config themselves (against ``config_schema.json``).
    """
    path = find_config()
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    data["_config_path"] = str(path)
    return data


def config_path() -> Path | None:
    return find_config()


def _resolve(raw: str, base: Path) -> Path:
    p = Path(raw)
    return p if p.is_absolute() else (base / p).resolve()


def app_root() -> Path:
    """Application root: config ``app_root`` (relative to the config file) or legacy fallback."""
    raw = _config().get("app_root")
    if isinstance(raw, str) and raw.strip():
        base = Path(_config().get("_config_path", str(_PACKAGE_ROOT))).parent
        return _resolve(raw, base)
    return _PACKAGE_ROOT


def state_root() -> Path:
    """GSD state root: config ``state_folder`` (relative to app_root) or legacy ``.planning``."""
    raw = _config().get("state_folder")
    if isinstance(raw, str) and raw.strip():
        return _resolve(raw, app_root())
    return app_root() / LEGACY_STATE_FOLDER


def manifest_dir() -> Path:
    """Directory for the machine-specific detection caches (host/gsd/code-intel manifests).

    Config present -> a sibling of the state folder (``<state_parent>/.manifest``), the
    app-repo layout. No config (legacy / in-repo) -> ``framework/.manifest``, the historical
    location, so nothing moves until a ``framework.config.json`` is introduced. This mirrors
    ``state_root()``'s config-then-legacy contract and keeps A3 behaviour-preserving in-tree.
    """
    if _config():
        return state_root().parent / ".manifest"
    return framework_root() / ".manifest"


def framework_root() -> Path:
    """Where the installed ``framework`` package lives - always package-relative."""
    return Path(__file__).resolve().parent


def surface_root() -> Path:
    """The relocated framework surface (agents/skills/rules/...) shipped inside the package."""
    return framework_root() / "opencode"


def gate_settings() -> dict:
    value = _config().get("gate_settings")
    return value if isinstance(value, dict) else {}


def readiness() -> dict:
    value = _config().get("readiness")
    return value if isinstance(value, dict) else {}


def bootstrap_sys_path() -> Path:
    """Put the import root on sys.path and return it (legacy/direct-run support).

    When a leaf script is executed as ``python framework/.../x.py`` the repo root
    is not on ``sys.path``, so ``import framework`` fails. This restores it. Under
    an installed package (``python -m framework...``) it is a no-op.
    """
    root = app_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root
