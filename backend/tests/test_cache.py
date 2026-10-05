import asyncio

import pytest

from app.services.scheduler.cache import SourceCache


class Counter:
    def __init__(self, value="payload", delay=0.0):
        self.calls = 0
        self.value = value
        self.delay = delay

    async def __call__(self):
        self.calls += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.value


async def test_first_call_collects():
    cache, collect = SourceCache(), Counter()
    assert await cache.get_or_collect("k", 60, collect) == "payload"
    assert collect.calls == 1


async def test_second_call_is_served_from_cache():
    cache, collect = SourceCache(), Counter()
    await cache.get_or_collect("k", 60, collect)
    await cache.get_or_collect("k", 60, collect)
    assert collect.calls == 1
    assert cache.hits == 1


async def test_widgets_sharing_a_key_cost_one_call():
    """The §17 promise: three Tautulli widgets, one get_activity."""
    cache, collect = SourceCache(), Counter()
    for _ in range(3):
        await cache.get_or_collect("tautulli:1:activity", 10, collect)
    assert collect.calls == 1


async def test_different_keys_do_not_share():
    cache, collect = SourceCache(), Counter()
    await cache.get_or_collect("a", 60, collect)
    await cache.get_or_collect("b", 60, collect)
    assert collect.calls == 2


async def test_expired_entry_is_collected_again():
    cache, collect = SourceCache(), Counter()
    await cache.get_or_collect("k", 0, collect)
    await cache.get_or_collect("k", 0, collect)
    assert collect.calls == 2


async def test_concurrent_callers_trigger_a_single_request():
    """Without the per-key lock, widgets due at the same instant would all
    hit the service at once."""
    cache, collect = SourceCache(), Counter(delay=0.02)
    results = await asyncio.gather(
        *(cache.get_or_collect("k", 60, collect) for _ in range(5))
    )
    assert collect.calls == 1
    assert results == ["payload"] * 5


async def test_invalidate_by_prefix():
    cache, collect = SourceCache(), Counter()
    await cache.get_or_collect("weather:1", 60, collect)
    await cache.get_or_collect("zabbix:1", 60, collect)
    cache.invalidate("weather:")
    await cache.get_or_collect("weather:1", 60, collect)
    await cache.get_or_collect("zabbix:1", 60, collect)
    assert collect.calls == 3


async def test_a_failing_collect_is_not_cached():
    cache = SourceCache()

    async def boom():
        raise RuntimeError("upstream down")

    with pytest.raises(RuntimeError):
        await cache.get_or_collect("k", 60, boom)

    collect = Counter()
    assert await cache.get_or_collect("k", 60, collect) == "payload"
    assert collect.calls == 1
