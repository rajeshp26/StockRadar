from typing import Any

from infrastructure.repositories.valuation_repository import ValuationRepository
from utils.dataloader import DataLoader


class ValuationDataLoader:
    def __init__(self, repo: ValuationRepository):
        self._repo = repo
        self._snapshot_loader: DataLoader | None = None
        self._company_context_loader: DataLoader | None = None

    def get_snapshot_loader(self) -> DataLoader:
        if self._snapshot_loader is None:
            def batch_snapshots(keys: list[str]) -> list[Any | None]:
                results: list[Any | None] = []
                for key in keys:
                    parts = key.split(":", 2)
                    if len(parts) != 2:
                        results.append(None)
                        continue
                    company_id_str, method = parts
                    try:
                        company_id = int(company_id_str)
                    except ValueError:
                        results.append(None)
                        continue
                    snap = self._repo.get_last_output_snapshot(company_id, method)
                    results.append(snap)
                return results

            self._snapshot_loader = DataLoader(
                batch_load_fn=batch_snapshots,
                cache=True,
                max_batch_size=10,
            )
        return self._snapshot_loader

    def get_company_context_loader(self) -> DataLoader:
        if self._company_context_loader is None:
            def batch_context(keys: list[str]) -> list[Any | None]:
                results: list[Any | None] = []
                for symbol in keys:
                    ctx = self._repo.get_company_context(symbol)
                    results.append(ctx)
                return results

            self._company_context_loader = DataLoader(
                batch_load_fn=batch_context,
                cache=True,
                max_batch_size=20,
            )
        return self._company_context_loader

    async def load_snapshot(self, company_id: int, method: str) -> Any | None:
        key = f"{company_id}:{method}"
        return await self.get_snapshot_loader().load(key)

    async def load_company_context(self, symbol: str) -> Any | None:
        return await self.get_company_context_loader().load(symbol)

    def clear_cache(self) -> None:
        if self._snapshot_loader:
            self._snapshot_loader.clear()
        if self._company_context_loader:
            self._company_context_loader.clear()
