"""Reconciliation engine: compares CSV truth with stored state, auto-corrects small deltas."""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import logging

from database import supabase
from infrastructure.repositories.event_store import EventStore
from shared.alerting import SlackAlerter

logger = logging.getLogger("stockerpro.reconciliation")


@dataclass
class ReconciliationResult:
    account_id: int
    as_of_date: date
    statements_used: int
    cash_delta: Decimal
    holdings_delta: int
    auto_corrected: bool
    correction_event_id: Optional[str] = None
    needs_review: bool = False
    errors: List[str] = field(default_factory=list)


@dataclass
class BrokerStatement:
    account_external_id: str
    statement_date: date
    cash_balance: Decimal
    holdings: Dict[str, Decimal]  # symbol -> quantity
    currency: str = "CAD"
    source_file: str = ""
    is_parsed_from_csv: bool = True


class BrokerStatementCSVAdapter:
    """Parses BrokerStatement CSV rows into BrokerStatement objects."""

    REQUIRED_COLUMNS = {"account", "date", "cash", "holdings_json"}

    @staticmethod
    def parse_row(row: Dict[str, str]) -> Optional[BrokerStatement]:
        try:
            account = row.get("account", "").strip()
            date_str = row.get("date", "").strip()
            cash_str = row.get("cash", "").strip()
            holdings_json_str = row.get("holdings_json", "").strip()
        except AttributeError:
            return None

        if not account or not date_str:
            return None

        try:
            stmt_date = date.fromisoformat(date_str)
        except (ValueError, TypeError):
            return None

        try:
            cash = Decimal(cash_str) if cash_str else Decimal("0")
        except Exception:
            cash = Decimal("0")

        holdings: Dict[str, Decimal] = {}
        if holdings_json_str:
            import json
            try:
                parsed = json.loads(holdings_json_str)
                if isinstance(parsed, dict):
                    for sym, qty in parsed.items():
                        try:
                            holdings[str(sym).strip()] = Decimal(str(qty))
                        except Exception:
                            pass
            except (json.JSONDecodeError, ValueError):
                pass

        return BrokerStatement(
            account_external_id=account,
            statement_date=stmt_date,
            cash_balance=cash,
            holdings=holdings,
            source_file=row.get("source_file", ""),
            is_parsed_from_csv=True,
        )

    @staticmethod
    def parse_csv(content: str) -> List[BrokerStatement]:
        import csv
        import io

        reader = csv.DictReader(io.StringIO(content))
        statements = []
        for row in reader:
            stmt = BrokerStatementCSVAdapter.parse_row(row)
            if stmt:
                statements.append(stmt)
        return statements


class ReconciliationEngine:
    """Compares BrokerStatement data with stored state and auto-corrects."""

    AUTO_CORRECT_THRESHOLD = Decimal("1000.00")
    DEPOSIT_BASED_THRESHOLD = True

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        alerter: Optional[SlackAlerter] = None,
    ):
        self.event_store = event_store or EventStore()
        self.alerter = alerter or SlackAlerter()

    def reconcile(
        self,
        statement: BrokerStatement,
        account_id: int,
    ) -> ReconciliationResult:
        """Compare a broker statement with stored state. Auto-corrects if delta < $1000."""
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        repo = PortfolioRepository()
        result = ReconciliationResult(
            account_id=account_id,
            as_of_date=statement.statement_date,
            statements_used=1,
            cash_delta=Decimal("0"),
            holdings_delta=0,
            auto_corrected=False,
        )

        # Get stored state
        try:
            stored_cash = repo.get_cash_balance(account_id, statement.statement_date)
        except Exception as e:
            result.errors.append(f"Failed to get stored cash: {e}")
            return result

        # Cash delta
        result.cash_delta = statement.cash_balance - stored_cash
        abs_cash_delta = abs(result.cash_delta)

        # Holdings: count positions that differ
        try:
            stored_holdings = repo.get_account_holdings_as_of(account_id, statement.statement_date)
            stored_symbols = {h.get("symbol"): h.get("quantity", 0) for h in stored_holdings}
        except Exception as e:
            result.errors.append(f"Failed to get stored holdings: {e}")
            stored_symbols = {}

        all_symbols = set(list(stored_symbols.keys()) + list(statement.holdings.keys()))
        for sym in all_symbols:
            stored_qty = Decimal(str(stored_symbols.get(sym, 0)))
            stmt_qty = statement.holdings.get(sym, Decimal("0"))
            if stored_qty != stmt_qty:
                result.holdings_delta += abs(int(stored_qty - stmt_qty))

        # Decide: auto-correct or flag for review
        delta_below_threshold = abs_cash_delta <= self.AUTO_CORRECT_THRESHOLD

        if abs_cash_delta == 0 and result.holdings_delta == 0:
            # Perfect match — no action needed
            result.auto_corrected = True
            return result

        if delta_below_threshold:
            # Auto-create correction event
            correction_event = self._create_correction_event(
                account_id=account_id,
                statement=statement,
                stored_cash=stored_cash,
                cash_delta=result.cash_delta,
            )
            result.correction_event_id = correction_event.get("id")
            result.auto_corrected = True

            self.alerter.alert_info(
                f"Auto-corrected account {account_id}: cash_delta=${float(abs_cash_delta):.2f} "
                f"(threshold=${float(self.AUTO_CORRECT_THRESHOLD):.2f})",
                title="Portfolio Auto-Correction",
            )
        else:
            # Above threshold — needs human review
            result.needs_review = True
            self.alerter.alert_warning(
                f"Account {account_id}: cash_delta=${float(abs_cash_delta):.2f} "
                f"exceeds auto-correct threshold. Manual review required.",
                title="Portfolio Reconciliation: Review Required",
            )

        return result

    def _create_correction_event(
        self,
        account_id: int,
        statement: BrokerStatement,
        stored_cash: Decimal,
        cash_delta: Decimal,
    ) -> dict:
        return self.event_store.append_event(
            event_type="correction_applied",
            aggregate_id=f"account_{account_id}",
            aggregate_type="account",
            data={
                "account_id": account_id,
                "statement_date": statement.statement_date.isoformat(),
                "stated_cash": float(statement.cash_balance),
                "stored_cash": float(stored_cash),
                "cash_delta": float(cash_delta),
                "holdings_at_date": {
                    sym: float(qty) for sym, qty in statement.holdings.items()
                },
                "source": statement.source_file or "broker_statement_csv",
            },
            metadata={
                "reconciliation": True,
                "auto_corrected": True,
                "statement_date": statement.statement_date.isoformat(),
            },
            idempotency_key=f"reconcile_{account_id}_{statement.statement_date.isoformat()}",
        )

    def reconcile_from_csv(
        self,
        csv_content: str,
        account_id_map: Dict[str, int],
    ) -> List[ReconciliationResult]:
        """Reconcile all statements found in a CSV against known account IDs."""
        statements = BrokerStatementCSVAdapter.parse_csv(csv_content)
        results = []
        for stmt in statements:
            aid = account_id_map.get(stmt.account_external_id)
            if aid is None:
                logger.warning(f"No account ID mapping for external_id={stmt.account_external_id}")
                continue
            result = self.reconcile(stmt, aid)
            results.append(result)
        return results
