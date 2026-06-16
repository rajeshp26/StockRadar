"""Unit tests for DefeatBetaProvider provider routing logic."""

from backend.providers.defeat_beta_provider import DefeatBetaProvider, PROVIDER_EXCHANGE_RULES


class TestProviderApplicable:
    """_provider_applicable controls which providers are tried per
    exchange + security_type combination."""

    # ── no exchange/security_type → all providers applicable ──

    def test_no_exchange_no_type(self):
        assert DefeatBetaProvider._provider_applicable("stockdex") is True
        assert DefeatBetaProvider._provider_applicable("edgar") is True
        assert DefeatBetaProvider._provider_applicable("yfinance") is True

    def test_no_exchange_with_type(self):
        assert DefeatBetaProvider._provider_applicable("stockdex", security_type="stock") is True
        assert DefeatBetaProvider._provider_applicable("edgar", security_type="stock") is True

    def test_with_exchange_no_type(self):
        assert DefeatBetaProvider._provider_applicable("stockdex", exchange="NYSE") is True
        assert DefeatBetaProvider._provider_applicable("edgar", exchange="NYSE") is True

    # ── unknown provider name → always applicable ──

    def test_unknown_provider(self):
        assert DefeatBetaProvider._provider_applicable("nonexistent") is True
        assert DefeatBetaProvider._provider_applicable("nonexistent", exchange="LSE") is True
        assert DefeatBetaProvider._provider_applicable("nonexistent", security_type="etf") is True

    # ── stockdex: US exchanges ──

    def test_stockdex_us_exchanges(self):
        for exc in ("NYSE", "NYQ", "NMS", "NGM", "NCM", "NASDAQ"):
            assert DefeatBetaProvider._provider_applicable("stockdex", exchange=exc) is True, f"stockdex should apply to {exc}"

    def test_stockdex_ca_exchanges(self):
        for exc in ("TOR", "TSX", "VAN", "TSXV", "V", "CNQ", "NEO"):
            assert DefeatBetaProvider._provider_applicable("stockdex", exchange=exc) is True, f"stockdex should apply to {exc}"

    def test_stockdex_other_exchange(self):
        for exc in ("LSE", "HKSE", "TSE", "FRA", "GER"):
            assert DefeatBetaProvider._provider_applicable("stockdex", exchange=exc) is False, f"stockdex should NOT apply to {exc}"

    def test_stockdex_case_insensitive(self):
        assert DefeatBetaProvider._provider_applicable("stockdex", exchange="nyse") is True
        assert DefeatBetaProvider._provider_applicable("stockdex", exchange="tsx") is True
        assert DefeatBetaProvider._provider_applicable("stockdex", exchange="lse") is False

    # ── edgar: US exchanges + stock type only ──

    def test_edgar_us_exchange_stock(self):
        for exc in ("NYSE", "NYQ", "NMS", "NGM", "NCM", "NASDAQ"):
            assert DefeatBetaProvider._provider_applicable("edgar", exchange=exc, security_type="stock") is True, f"edgar should apply to {exc}+stock"

    def test_edgar_us_exchange_etf(self):
        for exc in ("NYSE", "NASDAQ"):
            assert DefeatBetaProvider._provider_applicable("edgar", exchange=exc, security_type="etf") is False, f"edgar should NOT apply to {exc}+etf"

    def test_edgar_us_exchange_fund(self):
        for exc in ("NYSE", "NASDAQ"):
            assert DefeatBetaProvider._provider_applicable("edgar", exchange=exc, security_type="fund") is False, f"edgar should NOT apply to {exc}+fund"

    def test_edgar_ca_exchange_stock(self):
        for exc in ("TSX", "VAN", "TSXV", "NEO"):
            assert DefeatBetaProvider._provider_applicable("edgar", exchange=exc, security_type="stock") is False, f"edgar should NOT apply to {exc}+stock"

    def test_edgar_ca_exchange_etf(self):
        for exc in ("TSX", "VAN"):
            assert DefeatBetaProvider._provider_applicable("edgar", exchange=exc, security_type="etf") is False

    def test_edgar_case_insensitive(self):
        assert DefeatBetaProvider._provider_applicable("edgar", exchange="NYSE", security_type="Stock") is True
        assert DefeatBetaProvider._provider_applicable("edgar", exchange="nyse", security_type="STOCK") is True
        assert DefeatBetaProvider._provider_applicable("edgar", exchange="tsx", security_type="stock") is False

    # ── yfinance: always applicable (no rules) ──

    def test_yfinance_always_applicable(self):
        assert DefeatBetaProvider._provider_applicable("yfinance", exchange="NYSE") is True
        assert DefeatBetaProvider._provider_applicable("yfinance", exchange="LSE") is True
        assert DefeatBetaProvider._provider_applicable("yfinance", security_type="stock") is True
        assert DefeatBetaProvider._provider_applicable("yfinance", security_type="etf") is True
