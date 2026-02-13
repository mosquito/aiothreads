import asyncio
import os
import threading

import pytest
from async_timeout import timeout

from aiothreads import (
    ChannelClosed,
    ChannelTimeout,
    FromThreadChannel,
    threaded,
    threaded_iterable,
    threaded_iterable_separate,
)

gen_decos = (threaded_iterable, threaded_iterable_separate)


async def test_from_thread_channel_wait_before(threaded_decorator):
    channel = FromThreadChannel(maxsize=1)

    @threaded_decorator
    def in_thread():
        with channel:
            for i in range(10):
                channel.put(i)

    asyncio.get_running_loop().call_later(0.1, in_thread)

    result = []
    try:
        with pytest.raises(ChannelClosed):
            while True:
                result.append(await asyncio.wait_for(channel.get(), timeout=5))
    finally:
        assert result == list(range(10))


async def test_from_thread_channel_close():
    channel = FromThreadChannel(maxsize=1)
    with channel:
        channel.put(1)

    with pytest.raises(ChannelClosed):
        channel.put(2)

    channel = FromThreadChannel(maxsize=1)
    task = asyncio.get_running_loop().create_task(channel.get())

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=1)

    asyncio.get_running_loop().call_soon(channel.put, 1)

    assert await channel.get() == 1


async def test_from_thread_channel_timeout():
    """Test channel timeout functionality."""
    # Test with default timeout (0 = disabled)
    channel = FromThreadChannel(maxsize=1)
    channel.put("data")
    assert await channel.get() == "data"

    # Test with timeout parameter on get()
    channel = FromThreadChannel(maxsize=1)
    with pytest.raises(ChannelTimeout):
        await channel.get(timeout=0.1)

    # Test with default timeout set in constructor
    channel = FromThreadChannel(maxsize=1, timeout=0.1)
    with pytest.raises(ChannelTimeout):
        await channel.get()

    # Test that timeout=0 on get() overrides default timeout (disables it)
    # This should NOT timeout because we're using asyncio.wait_for externally
    channel = FromThreadChannel(maxsize=1, timeout=0.1)
    channel.put("data")
    result = await channel.get(timeout=0)  # timeout=0 means no timeout
    assert result == "data"


async def test_from_thread_channel_timeout_with_data(threaded_decorator):
    """Test that timeout works correctly when data arrives in time."""
    channel = FromThreadChannel(maxsize=1, timeout=5)

    @threaded_decorator
    def in_thread():
        import time
        time.sleep(0.1)
        channel.put("delayed_data")

    in_thread()

    # Data should arrive before timeout
    result = await channel.get()
    assert result == "delayed_data"


@pytest.fixture(params=gen_decos)
def iterator_decorator(request):
    return request.param


async def test_threaded_generator():
    @threaded
    def arange(*args):
        return (yield from range(*args))

    async with timeout(10):
        count = 10

        result = []
        agen = arange(count)
        async for item in agen:
            result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_max_size(iterator_decorator):
    @iterator_decorator(max_size=1)
    def arange(*args):
        return (yield from range(*args))

    async with timeout(2):
        count = 10

        result = []
        agen = arange(count)
        async for item in agen:
            result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_exception(iterator_decorator):
    @iterator_decorator
    def arange(*args):
        yield from range(*args)
        raise ZeroDivisionError

    async with timeout(2):
        count = 10

        result = []
        agen = arange(count)

        with pytest.raises(ZeroDivisionError):
            async for item in agen:
                result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_close(iterator_decorator):
    stopped = False

    @iterator_decorator(max_size=2)
    def noise():
        nonlocal stopped

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped = True

    async with timeout(2):
        counter = 0

        async with noise() as gen:
            async for _ in gen:  # NOQA
                counter += 1
                if counter > 9:
                    break

        wait_counter = 0
        while not stopped and wait_counter < 5:
            await asyncio.sleep(1)
            wait_counter += 1

        assert stopped


async def test_threaded_generator_close_cm(iterator_decorator):
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def noise():
        nonlocal stopped  # noqa

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped.set()

    async with timeout(2):
        async with noise() as gen:
            counter = 0
            async for _ in gen:  # NOQA
                counter += 1
                if counter > 9:
                    break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_close_break(iterator_decorator):
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def noise():
        nonlocal stopped  # noqa

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped.set()

    async with timeout(2):
        counter = 0
        async for _ in noise():  # NOQA
            counter += 1
            if counter > 9:
                break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_non_generator_raises(iterator_decorator):
    @iterator_decorator()
    def errored():
        raise RuntimeError("Aaaaaaaa")

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored():  # NOQA
                pass


async def test_threaded_generator_func_raises(iterator_decorator):
    @iterator_decorator
    def errored(val):
        if val:
            raise RuntimeError("Aaaaaaaa")

        yield

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored(True):  # NOQA
                pass
