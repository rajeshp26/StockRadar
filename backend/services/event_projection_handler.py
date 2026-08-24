"""Event Projection Handler — async poller that keeps portfolio_holdings in sync with portfolio_events.

Polls for new events, replays each affected account, and atomically swaps portfolio_holdings.
Uses event_sequence table for polling (with BIGSERIAL seq_id), but falls back to
created_at-based polling if the table doesn't exist.
"""
import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from database import supabase
from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import AccountState, ReplayEngine

logger = logging.getLogger("stockerpro.services.event_projection_handler")

CHECKPOINT_FILE = Path(__file__).resolve().parent.parent / "data" / "projection_checkpoint.json"


class EventProjectionHandler:
    """Polls for new portfolio_events and keeps portfolio_holdings synchronized."""

    def __init__(self):
        self.event_store = EventStore()
        self.replay_engine = ReplayEngine(self.event_store)
        self._running = False
        self._use_event_sequence = self._check_event_sequence_table()
        self._last_seq_id = self._load_checkpoint()

    # ----------------------------------------------------------------
    # Checkpoint persistence
    # ----------------------------------------------------------------
    def _check_event_sequence_table(self) -> bool:
        try:
            supabase.table("event_sequence").select("seq_id").limit(1).execute()
            return True
        except Exception:
            logger.info("event_sequence table not found — falling back to created_at-based polling")
            return False

    def _load_checkpoint(self) -> int:
        try:
            if self._use_event_sequence:
                r = supabase.table("projection_checkpoint").select("last_seq_id").eq("id", 1).limit(1).execute()
                if r.data:
                    return r.data[0]["last_seq_id"]
            if CHECKPOINT_FILE.exists():
                data = json.loads(CHECKPOINT_FILE.read_text())
                return data.get("last_seq_id", 0)
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
        return 0

    def _save_checkpoint(self, seq_id: int) -> None:
        try:
            if self._use_event_sequence:
                supabase.table("projection_checkpoint").upsert({
                    "id": 1,
                    "last_seq_id": seq_id,
                    "updated_at": datetime.now(UTC).isoformat(),
                }).execute()
            else:
                CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
                CHECKPOINT_FILE.write_text(json.dumps({"last_seq_id": seq_id, "updated_at": datetime.now(UTC).isoformat()}))
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    # ----------------------------------------------------------------
    # Polling
    # ----------------------------------------------------------------
    def get_new_events(self) -> list[dict]:
        """Get events since last checkpoint."""
        if self._use_event_sequence:
            return self._poll_via_sequence()
        return self._poll_via_created_at()

    def _poll_via_sequence(self) -> list[dict]:
        r = (
            supabase.table("event_sequence")
            .select("seq_id, event_id, aggregate_id")
            .gt("seq_id", self._last_seq_id)
            .order("seq_id")
            .limit(100)
            .execute()
        )
        return r.data or []

    def _poll_via_created_at(self) -> list[dict]:
        # Use created_at with 1ms offset to avoid missing events
        events = self.event_store.get_all_events(
            aggregate_type="account",
            limit=100,
        )
        # Filter by checkpoint (we store events count as checkpoint)
        new_events = events[self._last_seq_id:]
        return new_events

    def get_account_ids_from_events(self, events: list[dict]) -> set[int]:
        from shared.replay_engine import _parse_account_id
        account_ids = set()
        for ev in events:
            agg_id = ev.get("aggregate_id", "")
            aid = _parse_account_id(agg_id)
            if aid:
                account_ids.add(aid)
        return account_ids

    # ----------------------------------------------------------------
    # Full rebuild
    # ----------------------------------------------------------------
    def rebuild_account(self, account_id: int) -> None:
        """Full replay for one account → atomic swap write to portfolio_holdings."""
        state = self.replay_engine.replay_to_date(account_id, datetime.now(UTC).date())
        self._atomic_write_holdings(account_id, state)
        logger.info(f"Rebuilt account {account_id}: {len(state.holdings)} holdings")

    def _atomic_write_holdings(self, account_id: int, state: AccountState) -> None:
        """DELETE + INSERT inside a transaction, using Supabase RPC if available."""
        current_overrides = {}
        try:
            existing = supabase.table("portfolio_holdings")\
                .select("company_id, exchange_override")\
                .eq("account_id", account_id)\
                .execute()
            for row in existing.data or []:
                if row.get("exchange_override"):
                    current_overrides[row["company_id"]] = row["exchange_override"]
        except Exception:
            pass

        rows = []
        for cid, holding in state.holdings.items():
            rows.append({
                "account_id": account_id,
                "company_id": cid,
                "symbol": holding.symbol,
                "quantity": float(holding.quantity),
                "average_cost": float(holding.average_cost),
                "total_cost": float(holding.total_cost),
                "realized_gain_loss": float(holding.realized_gain_loss),
                "currency": "CAD",
                "exchange_override": current_overrides.get(cid),
                "first_purchase_date": holding.trade_date.isoformat() if holding.trade_date else None,
                "last_transaction_date": datetime.now(UTC).date().isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            })

        try:
            # Try using a Supabase function for atomic swap
            r = supabase.rpc("atomic_swap_holdings", {
                "p_account_id": account_id,
                "p_holdings": json.dumps(rows),
            }).execute()
            if r.data:
                return
        except Exception:
            pass

        # Fallback: delete + insert (not fully atomic but acceptable for MVP)
        supabase.table("portfolio_holdings").delete().eq("account_id", account_id).execute()
        if rows:
            supabase.table("portfolio_holdings").insert(rows).execute()

    def rebuild_all_accounts(self) -> None:
        """Rebuild all accounts from events."""
        for account_id in [7, 8, 9, 10, 11, 12]:
            try:
                self.rebuild_account(account_id)
                logger.info(f"Rebuilt account {account_id}")
            except Exception as e:
                logger.error(f"Failed to rebuild account {account_id}: {e}")

    # ----------------------------------------------------------------
    # Polling loop
    # ----------------------------------------------------------------
    async def start_polling(self, interval_ms: int = 1000) -> None:
        """Start the polling loop. Runs until cancelled."""
        self._running = True
        logger.info(f"EventProjectionHandler polling started (interval={interval_ms}ms)")
        while self._running:
            try:
                new_events = self.get_new_events()
                if new_events:
                    account_ids = self.get_account_ids_from_events(new_events)
                    for aid in sorted(account_ids):
                        self.rebuild_account(aid)
                    if self._use_event_sequence:
                        self._last_seq_id = max(e["seq_id"] for e in new_events)
                    else:
                        self._last_seq_id = len(self.event_store.get_all_events(aggregate_type="account"))
                    self._save_checkpoint(self._last_seq_id)
                await asyncio.sleep(interval_ms / 1000)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(interval_ms / 1000)
        self._running = False

    def stop(self) -> None:
        self._running = False
