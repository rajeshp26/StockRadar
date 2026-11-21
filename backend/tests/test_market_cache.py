"""REMOVED: obsolete tests for the deleted ``shared.market_cache`` module.

These tests were intentionally retired during I1d (2026-11) remediation.

Evidence: refactor commit 22942cc4 ("fix: CDR pricing...") deleted
``backend/shared/market_cache.py`` and the ``get_cached_prices`` / cache
mechanism it provided. Current price access reads ``current_market_data``
directly (see ``application/services/portfolio_service.py::_get_current_price``
and ``infrastructure/repositories/price_repository.py``). No production caller
of ``get_cached_prices`` / ``invalidate_cache`` remains.

The five former test cases imported ``shared.market_cache`` (a module that no
longer exists) and asserted TTL-cache semantics for a feature that was
deliberately removed. They are obsolete, not a product regression. Per the
I1d burn-down policy, the file is retained as a tombstone so the rationale
travels with the repository; it collects zero tests.
"""
