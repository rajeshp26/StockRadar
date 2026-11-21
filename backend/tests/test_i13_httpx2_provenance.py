"""I13 -- prove httpcore2/httpx2 are legitimate openai deps, not phantom pins.

requirements.txt declares both ``httpx[http2]==0.28.1`` and ``httpx2==2.15.1`` /
``httpcore2==2.15.1``. The duplicate-looking pair is really two independent HTTP
stacks: openai 3.x depends on the pydantic ``httpx2`` fork, while supabase/edgartools
use mainstream ``httpx``. This reads the *installed distributions'* own metadata so
the provenance claim stays true even if pins change on a future upgrade.
"""
from __future__ import annotations

from importlib import metadata


def _requires(dist: str, needle: str) -> list[str]:
    return [r for r in (metadata.requires(dist) or []) if needle in r.lower()]


def test_openai_declares_httpx2_not_mainstream_httpx():
    reqs = _requires("openai", "httpx")
    assert reqs, "openai declares no httpx-family dependency -- provenance changed"
    assert all("httpx2" in r for r in reqs), (
        f"expected openai to depend on the httpx2 fork, got {reqs}"
    )


def test_httpx2_declares_httpcore2_fork():
    reqs = _requires("httpx2", "httpcore")
    assert reqs, "httpx2 declares no httpcore-family dependency"
    assert all("httpcore2" in r for r in reqs), (
        f"expected httpx2 to depend on httpcore2, got {reqs}"
    )


def test_both_http_stacks_are_installed_and_importable():
    import httpcore2  # noqa: F401
    import httpx
    import httpx2

    assert metadata.version("httpx2")
    assert metadata.version("httpcore2")
    assert str(httpx2.__version__) == metadata.version("httpx2")
    assert str(httpx.__version__) == metadata.version("httpx")
