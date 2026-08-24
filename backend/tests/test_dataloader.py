import asyncio

import pytest

from utils.dataloader import DataLoader


class TestDataLoader:
    @pytest.mark.asyncio
    async def test_batches_multiple_loads_into_single_call(self):
        call_count = 0

        async def run():
            nonlocal call_count

            def batch_fn(keys):
                nonlocal call_count
                call_count += 1
                return [f"result:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn)
            r1, r2, r3 = await asyncio.gather(
                loader.load("a"), loader.load("b"), loader.load("c")
            )
            assert r1 == "result:a"
            assert r2 == "result:b"
            assert r3 == "result:c"
            assert call_count == 1

        await run()

    @pytest.mark.asyncio
    async def test_respects_max_batch_size(self):
        call_count = 0

        async def run():
            nonlocal call_count

            def batch_fn(keys):
                nonlocal call_count
                call_count += 1
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn, max_batch_size=2)
            results = await asyncio.gather(
                loader.load("a"),
                loader.load("b"),
                loader.load("c"),
                loader.load("d"),
                loader.load("e"),
            )
            assert results == ["val:a", "val:b", "val:c", "val:d", "val:e"]
            assert call_count >= 2

        await run()

    @pytest.mark.asyncio
    async def test_caches_repeated_loads(self):
        call_count = 0

        async def run():
            nonlocal call_count

            def batch_fn(keys):
                nonlocal call_count
                call_count += 1
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn)
            await loader.load("x")
            await loader.load("x")
            await loader.load("x")
            assert call_count == 1

        await run()

    @pytest.mark.asyncio
    async def test_cache_can_be_cleared(self):
        call_count = 0

        async def run():
            nonlocal call_count

            def batch_fn(keys):
                nonlocal call_count
                call_count += 1
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn)
            await loader.load("x")
            loader.clear("x")
            await loader.load("x")
            await loader.load("x")
            assert call_count == 2

        await run()

    @pytest.mark.asyncio
    async def test_cache_false_does_not_cache(self):
        call_count = 0

        async def run():
            nonlocal call_count

            def batch_fn(keys):
                nonlocal call_count
                call_count += 1
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn, cache=False)
            await loader.load("x")
            await loader.load("x")
            await loader.load("x")
            assert call_count == 3

        await run()

    @pytest.mark.asyncio
    async def test_propagates_batch_errors(self):
        async def run():
            def batch_fn(keys):
                raise ValueError("Batch failed")

            loader = DataLoader[str, str](batch_fn)

            with pytest.raises(ValueError, match="Batch failed"):
                await asyncio.gather(loader.load("a"), loader.load("b"))

        await run()

    @pytest.mark.asyncio
    async def test_cached_keys_property(self):
        async def run():
            def batch_fn(keys):
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn)
            await loader.load("a")
            await loader.load("b")
            assert loader.cached_keys == {"a", "b"}

        await run()

    @pytest.mark.asyncio
    async def test_clear_all_cache(self):
        async def run():
            def batch_fn(keys):
                return [f"val:{k}" for k in keys]

            loader = DataLoader[str, str](batch_fn)
            await loader.load("a")
            await loader.load("b")
            loader.clear()
            assert loader.cached_keys == set()

        await run()

    @pytest.mark.asyncio
    async def test_clear_nonexistent_key_does_not_raise(self):
        def batch_fn(keys):
            return [f"val:{k}" for k in keys]

        loader = DataLoader[str, str](batch_fn)
        loader.clear("nonexistent")
        assert True

    @pytest.mark.asyncio
    async def test_empty_batch_does_not_call_batch_fn(self):
        call_count = 0

        def batch_fn(keys):
            nonlocal call_count
            call_count += 1
            return [f"val:{k}" for k in keys]

        loader = DataLoader[str, str](batch_fn)
        assert call_count == 0
