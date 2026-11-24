"""CSV import must accept the current Wealthsimple export format and resume safely.

The real export this was reproduced with uses ``effective_date`` /
``effective_time`` / ``description`` / ``underlying symbol`` instead of the
legacy ``transaction_date`` header, contains quoted commas, blank settlement
dates, mixed currencies, negative sell quantities and non-cash rows with no
``net_cash_amount``. None of those may abort an otherwise valid import.
"""

from decimal import Decimal

import pytest

from application.parsers.portfolio_parser import WealthsimpleParser

CURRENT_HEADER = (
    "effective_date,effective_time,settlement_date,account_id,account_type,"
    "activity_type,activity_sub_type,description,direction,symbol,"
    "underlying symbol,name,currency,quantity,unit_price,commission,net_cash_amount"
)

CURRENT_CSV = f"""{CURRENT_HEADER}
2025-10-07,19:00:17,,HF1337814CAD,Crypto,CryptoStakingReward,-,0.0078701977 of DOT rewards earned,LONG,DOT,DOT,Polkadot,USD,0.0078701977,4.1655322873,,0.0327835626
2025-10-11,18:19:26,2025-10-11,HF1337814CAD,Crypto,Trade,BUY,"Purchase of 2.0000000000 SOL (executed at 2025-10-11), FX Rate: 1.4003",LONG,SOL,SOL,Solana,CAD,2,246.9639624,4.9432002,-498.88
2025-11-07,00:00:00,,HF1337814CAD,Crypto,Correction,ANOMALY,SOL - Solana: Corrected quantity of shares by -2.0000 (executed at 2025-11-07),LONG,SOL,SOL,Solana,,-2,,,
2025-12-01,00:00:00,,HQ035ZHK5CAD,TFSA,CorporateAction,CONSOLIDATION,"TSLY - ETF: Corrected quantity of shares by 2.0000 (executed at 2025-12-01)",,TSLY,TSLY,ETF,,,2,,,
2025-12-20,23:56:46,,HF1337814CAD,Crypto,MoneyMovement,TRANSFER,Money transfer out of the account (executed at 2025-12-21),,,,,CAD,-423,,,-423
2026-01-07,00:00:00,,HQ035ZHK5CAD,TFSA,Dividend,-,"QDTE - ETF: Cash dividend distribution, received on 2026-01-07",,QDTE,QDTE,ETF,USD,4.81,,,4.81
As of 2026-10-07 13:55 GMT-04:00,,,,,,,,,,,,,,,,
"""

LEGACY_CSV = """transaction_date,settlement_date,account_id,account_type,activity_type,activity_sub_type,direction,symbol,name,currency,quantity,unit_price,commission,net_cash_amount
2026-01-15,2026-01-17,H12345CAD,TFSA,Trade,BUY,LONG,AAPL,Apple Inc.,USD,10,150.00,1.00,-1501.00
"""


@pytest.fixture
def parser():
    return WealthsimpleParser()


class TestCurrentExportFormat:
    def test_parses_current_headers_without_losing_rows(self, parser):
        result = parser.parse_csv(CURRENT_CSV)

        assert result.success, result.errors
        assert result.total_rows == 7
        assert result.parsed_rows == 4
        assert result.skipped_rows == 3
        assert result.account_type_summary == {"Crypto": 3, "TFSA": 1}
        assert [tx.activity_type for tx in result.transactions] == [
            "CryptoStakingReward", "Trade", "MoneyMovement", "Dividend"
        ]

    def test_quoted_description_and_numeric_precision_survive_parsing(self, parser):
        result = parser.parse_csv(CURRENT_CSV)

        trade = result.transactions[1]
        assert trade.activity_sub_type == "BUY"
        assert trade.symbol == "SOL"
        assert trade.settlement_date.isoformat() == "2025-10-11"
        assert trade.quantity == Decimal("2")
        assert trade.unit_price == Decimal("246.9639624")
        assert trade.commission == Decimal("4.9432002")
        assert trade.net_cash_amount == Decimal("-498.88")
        assert "FX Rate: 1.4003" in trade.raw_data["description"]

        reward = result.transactions[0]
        assert reward.settlement_date is None
        assert reward.currency == "USD"
        assert reward.quantity == Decimal("0.0078701977")

    def test_non_cash_rows_are_skipped_with_warnings_not_errors(self, parser):
        result = parser.parse_csv(CURRENT_CSV)

        assert result.success
        assert not result.errors
        assert any("Correction" in warning for warning in result.warnings)
        assert any("CorporateAction" in warning for warning in result.warnings)

    def test_footer_row_is_skipped_with_current_headers(self, parser):
        result = parser.parse_csv(CURRENT_CSV)

        assert "As of" not in "".join(str(tx.raw_data) for tx in result.transactions)
        assert result.skipped_rows == 3

    def test_utf8_bom_is_tolerated(self, parser):
        result = parser.parse_csv("\ufeff" + CURRENT_CSV)

        assert result.success, result.errors
        assert result.parsed_rows == 4

    def test_account_filter_applies_to_current_headers(self, parser):
        result = parser.parse_csv(CURRENT_CSV, user_account_filter=["TFSA"])

        assert result.success
        assert result.parsed_rows == 1
        assert result.account_type_summary == {"TFSA": 1}
        assert result.transactions[0].activity_type == "Dividend"

    def test_missing_cash_amount_on_cash_activity_is_still_an_error(self, parser):
        broken = CURRENT_CSV.replace(
            "CAD,2,246.9639624,4.9432002,-498.88",
            "CAD,2,246.9639624,4.9432002,",
        )
        result = parser.parse_csv(broken)

        assert not result.success
        assert any("net_cash_amount" in error for error in result.errors)

    def test_header_without_any_supported_date_column_is_rejected(self, parser):
        broken = CURRENT_CSV.replace("effective_date", "booking_date", 1)
        result = parser.parse_csv(broken)

        assert not result.success
        assert any("effective_date" in error for error in result.errors)
        assert any("transaction_date" in error for error in result.errors)


class TestLegacyExportFormatStillWorks:
    def test_legacy_transaction_date_header_still_parses(self, parser):
        result = parser.parse_csv(LEGACY_CSV)

        assert result.success, result.errors
        assert result.parsed_rows == 1
        assert result.transactions[0].transaction_date.isoformat() == "2026-01-15"
        assert result.transactions[0].commission == Decimal("1.00")
