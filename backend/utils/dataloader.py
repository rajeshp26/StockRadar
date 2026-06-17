import asyncio
from collections import defaultdict
from typing import Any, Callable, Generic, List, Optional, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class DataLoader(Generic[K, V]):
    def __init__(
        self,
        batch_load_fn: Callable[[List[K]], List[Optional[V]]],
        cache: bool = True,
        max_batch_size: Optional[int] = None,
    ):
        self._batch_load_fn = batch_load_fn
        self._cache_enabled = cache
        self._max_batch_size = max_batch_size
        self._cache: dict[K, V] = {}
        self._queue: dict[int, list[tuple[K, asyncio.Future]]] = defaultdict(list)
        self._scheduled: set[int] = set()

    async def load(self, key: K) -> V:
        if self._cache_enabled and key in self._cache:
            return self._cache[key]

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        loop_id = id(loop)
        self._queue[loop_id].append((key, future))

        if loop_id not in self._scheduled:
            self._scheduled.add(loop_id)
            loop.call_soon(self._dispatch, loop_id)

        return await future

    def _dispatch(self, loop_id: int) -> None:
        items = self._queue.pop(loop_id, [])
        self._scheduled.discard(loop_id)

        if not items:
            return

        if self._max_batch_size and len(items) > self._max_batch_size:
            chunks = [
                items[i : i + self._max_batch_size]
                for i in range(0, len(items), self._max_batch_size)
            ]
            for chunk in chunks:
                self._execute_batch(chunk)
        else:
            self._execute_batch(items)

    def _execute_batch(self, items: list[tuple[K, asyncio.Future]]) -> None:
        keys = [item[0] for item in items]
        futures = [item[1] for item in items]

        try:
            results = self._batch_load_fn(keys)
            for key, future, result in zip(keys, futures, results):
                if self._cache_enabled and result is not None:
                    self._cache[key] = result
                if not future.done():
                    future.set_result(result)
        except Exception as e:
            for future in futures:
                if not future.done():
                    future.set_exception(e)

    def clear(self, key: Optional[K] = None) -> None:
        if key is None:
            self._cache.clear()
        elif key in self._cache:
            del self._cache[key]

    @property
    def cached_keys(self) -> set[K]:
        return set(self._cache.keys())
