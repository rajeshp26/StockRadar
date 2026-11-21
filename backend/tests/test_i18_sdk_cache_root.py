"""I18 -- the SDK's runtime-download cache root and its persistent-path mitigation.

The defeatbeta SDK downloads remote data at runtime and caches it under
``tempfile.gettempdir()`` (there is no config option for the base directory):

  * NLTK resources under ``<base>/defeatbeta/nltk`` (I17 removed the unused
    punkt_tab download, but the directory helper is still SDK-owned);
  * DuckDB httpfs parquet blocks under ``<base>/defeatbeta/cache/<version>``.

Because OS temp is ephemeral, a cold boot re-downloads the cached data. The
professional mitigation is to point the worker's TEMP/TMP/TMPDIR at a persistent
(mountable) directory before startup -- tempfile honours those at first call,
and the SDK inherits the redirected root. These tests keep both facts true:
where the root comes from, and that the env override works.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

_SNIPPET = (
    "import sys; "
    f"sys.path.insert(0, r'{_BACKEND_ROOT}'); "
    "from providers.defeatbeta_runtime import import_sdk_module; "
    "util = import_sdk_module('defeatbeta_api.utils.util'); "
    "print('NLTK_DIR=' + util.validate_nltk_directory()); "
    "print('HTTPFS_DIR=' + util.validate_httpfs_cache_directory())"
)


def test_sdk_cache_roots_derive_from_tempfile_gettempdir():
    """Both SDK cache roots sit under tempfile.gettempdir() (no config option)."""
    from providers.defeatbeta_runtime import import_sdk_module

    util = import_sdk_module("defeatbeta_api.utils.util")
    base = Path(tempfile.gettempdir()).resolve()

    nltk_dir = Path(util.validate_nltk_directory()).resolve()
    httpfs_dir = Path(util.validate_httpfs_cache_directory()).resolve()

    assert nltk_dir.is_relative_to(base)
    assert httpfs_dir.is_relative_to(base)
    # The httpfs cache is version-keyed so stale data is never reused.
    sdk_version = import_sdk_module("defeatbeta_api.__version__")
    assert httpfs_dir.name == sdk_version.__version__


def test_sdk_cache_root_honors_persistent_env_override():
    """TEMP/TMP/TMPDIR redirect both roots to a persistent, mountable path."""
    with tempfile.TemporaryDirectory(prefix="i18_persistent_") as scratch:
        root = Path(scratch)
        env = dict(os.environ)
        env.update(TMPDIR=str(root), TEMP=str(root), TMP=str(root))

        result = subprocess.run(
            [sys.executable, "-c", _SNIPPET],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            cwd=str(_BACKEND_ROOT),
        )

        out = dict(
            line.split("=", 1)
            for line in result.stdout.strip().splitlines()
            if "=" in line
        )
        nltk_dir = Path(out.get("NLTK_DIR", "")).resolve()
        httpfs_dir = Path(out.get("HTTPFS_DIR", "")).resolve()
        root_resolved = root.resolve()

        assert result.returncode == 0, result.stderr
        assert nltk_dir.exists() and nltk_dir.is_relative_to(root_resolved)
        assert httpfs_dir.exists() and httpfs_dir.is_relative_to(root_resolved)
