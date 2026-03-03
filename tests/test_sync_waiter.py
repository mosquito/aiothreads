import asyncio
import threading

import pytest

from aiothreads import sync_await, sync_wait_coroutine, wait_coroutine
from aiothreads.coroutine_waiter import CoroutineWaiter


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


async def test_cancelled_coroutine_unblocks_thread():
    """RACE-13: CancelledError in _on_result must not hang the worker thread."""
    loop = asyncio.get_running_loop()

    async def slow_coro():
        await asyncio.sleep(60)

    waiter = CoroutineWaiter(slow_coro(), loop)
    waiter.start()

    # Give event loop a tick to schedule the task
    await asyncio.sleep(0.05)

    # Cancel the underlying task by cancelling all tasks except current
    current = asyncio.current_task()
    for task in asyncio.all_tasks(loop):
        if task is not current and not task.done():
            task.cancel()

    await asyncio.sleep(0.05)

    # Now wait in a thread - it should unblock with CancelledError
    finished = threading.Event()
    exception_holder: list = [None]

    def waiter_thread():
        try:
            waiter.wait()
        except BaseException as e:
            exception_holder[0] = e
        finally:
            finished.set()

    t = threading.Thread(target=waiter_thread, daemon=True)
    t.start()
    assert finished.wait(timeout=5), "Worker thread hung on cancelled coroutine"
    assert isinstance(exception_holder[0], asyncio.CancelledError)


def test_wait_raises_when_loop_closes_before_awaiter():
    """RACE-12: If the loop closes before _awaiter runs, wait() must not
    hang forever. It should raise RuntimeError."""
    loop = asyncio.new_event_loop()

    async def slow_coro():
        await asyncio.sleep(60)

    coro = slow_coro()
    waiter = CoroutineWaiter(coro, loop)
    # Schedule _awaiter via call_soon_threadsafe
    waiter.start()
    # Immediately stop and close the loop before _awaiter can execute
    loop.stop()
    loop.close()

    finished = threading.Event()
    exception_holder: list = [None]

    def waiter_thread():
        try:
            waiter.wait()
        except BaseException as e:
            exception_holder[0] = e
        finally:
            finished.set()

    t = threading.Thread(target=waiter_thread, daemon=True)
    t.start()
    assert finished.wait(timeout=5), "wait() hung when loop was closed"
    assert isinstance(exception_holder[0], RuntimeError)
    assert "Event loop closed" in str(exception_holder[0])
    # Suppress "coroutine was never awaited" warning for the abandoned coroutine
    coro.close()
