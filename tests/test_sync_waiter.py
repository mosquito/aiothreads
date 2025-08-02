import asyncio

import pytest

from aiothreads import sync_await, sync_wait_coroutine, wait_coroutine


async def test_wait_coroutine_sync(threaded_decorator):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1

    event_loop = asyncio.get_running_loop()

    @threaded_decorator
    def test():
        sync_wait_coroutine(event_loop, coro)

    await test()
    assert result == 1


async def test_wait_coroutine_sync_current_loop(threaded_decorator):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1

    @threaded_decorator
    def test():
        wait_coroutine(coro())

    await test()
    assert result == 1


async def test_wait_awaitable(threaded_decorator):
    result = 0

    @threaded_decorator
    def in_thread():
        nonlocal result
        result += 1

    @threaded_decorator
    def test():
        sync_await(in_thread)

    await test()
    assert result == 1


async def test_wait_coroutine_sync_exc(threaded_decorator):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1
        raise RuntimeError("Test")

    event_loop = asyncio.get_running_loop()

    @threaded_decorator
    def test():
        sync_wait_coroutine(event_loop, coro)

    with pytest.raises(RuntimeError):
        await test()

    assert result == 1


async def test_wait_coroutine_sync_exc_noloop(threaded_decorator):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1
        raise RuntimeError("Test")

    @threaded_decorator
    def test():
        sync_wait_coroutine(None, coro)

    with pytest.raises(RuntimeError):
        await test()

    assert result == 1
