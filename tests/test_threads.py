import asyncio
from typing import Any

import pytest

from aiothreads import threaded, threaded_separate
from aiothreads.threads import Threaded, _awaiter, run_in_executor


async def test_threaded_repr():
    @threaded
    def foo():
        return 1

    assert "Threaded" in repr(foo)
    assert "foo" in repr(foo)


async def test_threaded_wrap_coroutine_raises():
    with pytest.raises(TypeError, match="coroutine"):

        @threaded
        async def foo():
            pass


async def test_threaded_wrap_generator_raises():
    with pytest.raises(TypeError, match="generator"):
        Threaded(lambda: (yield))


async def test_threaded_separate_wrap_coroutine_raises():
    with pytest.raises(TypeError, match="coroutine"):

        @threaded_separate
        async def foo():
            pass


async def test_awaiter_cancel():
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    task: asyncio.Task[Any] = asyncio.ensure_future(_awaiter(future))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert future.done()


async def test_awaiter_success():
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    future.set_result(42)

    result: Any = await _awaiter(future)
    assert result == 42


def test_run_in_executor_lazy_wrapper():
    awaitable = run_in_executor(lambda: 42)
    result: Any = asyncio.run(awaitable)  # type: ignore[arg-type]
    assert result == 42


async def test_threaded_separate_detach_false():
    decorator: Any = threaded_separate(False)  # type: ignore[arg-type]

    @decorator
    def foo():
        return 42

    assert await foo() == 42
