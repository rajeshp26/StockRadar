from abc import ABC, abstractmethod
from typing import Any


class WatchlistRepository(ABC):
    @abstractmethod
    def find_by_user_id(self, user_id: int) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def find_default_by_user_id(self, user_id: int) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def create_default(self, user_id: int, name: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def get_items_by_watchlist_id(self, watchlist_id: int) -> list[dict[str, Any]]:
        pass

    @abstractmethod
    def delete_item(self, item_id: int) -> None:
        pass

    @abstractmethod
    def update_item_targets(
        self,
        item_id: int,
        target_buy: float | None,
        target_sell: float | None
    ) -> dict[str, Any] | None:
        pass

class UserRepository(ABC):
    @abstractmethod
    def find_by_firebase_uid(self, firebase_uid: str) -> dict[str, Any] | None:
        pass
