import asyncio
import os
import threading
from contextlib import suppress

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


async def test_threaded_generator_error_before_consumption(iterator_decorator):
    """Context manager exit with exception before consuming must not hang."""

    @iterator_decorator(max_size=1)
    def gen():
        while True:
            yield os.urandom(32)

    async def run():
        try:
            async with gen() as iterator:
                _ = iterator
                raise RuntimeError("error before consumption")
        except RuntimeError:
            pass

    await asyncio.wait_for(run(), timeout=5)


async def test_threaded_generator_error_after_partial_consumption(
    iterator_decorator,
):
    """Exception after consuming some items inside context manager must not hang."""
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def gen():
        try:
            for i in range(100):
                yield i
        finally:
            stopped.set()

    async def run():
        try:
            async with gen() as iterator:
                count = 0
                async for _ in iterator:
                    count += 1
                    if count == 3:
                        raise RuntimeError("error after partial consumption")
        except RuntimeError:
            pass

    await asyncio.wait_for(run(), timeout=5)
    stopped.wait(timeout=5)
    assert stopped.is_set()


async def test_threaded_generator_close_without_context_manager_no_consumption(
    iterator_decorator,
):
    """Calling close() directly on unconsumed iterator must not hang."""

    @iterator_decorator(max_size=1)
    def gen():
        while True:
            yield os.urandom(32)

    async def run():
        wrapper = gen()
        await wrapper.close()

    await asyncio.wait_for(run(), timeout=5)


async def test_threaded_generator_double_close(iterator_decorator):
    """Closing an already-closed iterator must not hang."""
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def gen():
        try:
            for i in range(5):
                yield i
        finally:
            stopped.set()

    async def run():
        async with gen() as iterator:
            async for _ in iterator:
                break

        stopped.wait(timeout=5)
        assert stopped.is_set()

    await asyncio.wait_for(run(), timeout=5)


async def test_threaded_generator_cancel_during_iteration(iterator_decorator):
    """Cancelling the consuming task must not leave the generator hanging."""
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def gen():
        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped.set()

    async def consume():
        async with gen() as iterator:
            async for _ in iterator:
                await asyncio.sleep(10)  # will be cancelled

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.1)  # let it start consuming
    task.cancel()

    with suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    stopped.wait(timeout=5)
    assert stopped.is_set()


def test_close_event_set_when_loop_closes():
    """RACE-18: __close_event must be set even when the event loop closes
    during _in_thread execution. Using threading.Event means the thread
    can set it directly without call_soon_threadsafe."""
    import time

    from aiothreads.iterator_wrapper import IteratorWrapper

    gen_finished = threading.Event()

    def slow_gen():
        try:
            while True:
                yield 1
                time.sleep(0.01)
        finally:
            gen_finished.set()

    async def _run():
        wrapper = IteratorWrapper(slow_gen)
        aiter = wrapper.__aiter__()
        # consume one item to start the generator thread
        await aiter.__anext__()
        return wrapper

    loop = asyncio.new_event_loop()
    wrapper = loop.run_until_complete(_run())
    # Close the loop while the generator thread is still running
    loop.close()

    # The generator thread should finish and set the close event
    gen_finished.wait(timeout=5)
    assert gen_finished.is_set(), "Generator thread hung when loop closed"

    # The internal __close_event (threading.Event) should also be set
    # Access it via name mangling
    close_event = wrapper._IteratorWrapper__close_event
    assert close_event.is_set(), "__close_event was not set after loop close"


async def test_gc_finalizer_from_non_event_loop_thread(iterator_decorator):
    """RACE-7: GC finalizer calling close() from non-loop thread must not
    leave orphaned generator threads. The generator's finally block must run."""
    import gc

    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def gen():
        try:
            while True:
                yield 1
        finally:
            stopped.set()

    # Consume a few items, then drop the proxy from a non-event-loop thread
    items = []
    proxy = gen().__aiter__()
    items.append(await proxy.__anext__())
    items.append(await proxy.__anext__())
    assert len(items) == 2

    # Delete proxy from a background thread to simulate GC on a non-loop thread
    deleted = threading.Event()

    def delete_from_thread():
        nonlocal proxy
        del proxy
        gc.collect()
        deleted.set()

    t = threading.Thread(target=delete_from_thread, daemon=True)
    t.start()
    deleted.wait(timeout=5)

    # Generator's finally block should run within a reasonable time
    stopped.wait(timeout=5)
    assert stopped.is_set(), "Generator thread was orphaned (finally block never ran)"


def test_call_soon_threadsafe_on_closed_loop():
    """Test that _in_thread finally block doesn't crash when loop is closed.

    When the event loop shuts down while a producer thread is active,
    call_soon_threadsafe raises RuntimeError. The finally block in
    _in_thread must suppress this so __close_event.set doesn't get lost.
    """
    import time

    channel = FromThreadChannel(maxsize=0)
    finished = threading.Event()

    def producer():
        try:
            for i in range(100):
                channel.put(i)
                time.sleep(0.01)
        except RuntimeError:
            pass  # expected: loop is closed
        finally:
            finished.set()

    async def _run():
        loop = asyncio.get_running_loop()
        channel._loop = loop
        channel._data_event = asyncio.Event()

        t = threading.Thread(target=producer, daemon=True)
        t.start()

        # Consume one item to ensure producer is running
        await channel.get()

    loop = asyncio.new_event_loop()
    loop.run_until_complete(_run())
    loop.close()

    # Producer thread should exit without hanging
    assert finished.wait(timeout=5), "Producer thread hung"
