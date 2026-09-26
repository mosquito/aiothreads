import asyncio
import inspect
import threading as _threading
from abc import abstractmethod
from contextlib import suppress
from collections import deque
from concurrent.futures import Executor
from queue import Empty as QueueEmpty
from queue import Full as QueueFull
from types import TracebackType
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Deque,
    Generator,
    Generic,
    NoReturn,
    Optional,
    Type,
)
from weakref import finalize

from .types import P, T


class _ImmediateAwaitable:
    """Awaitable that resolves immediately without being a coroutine.

    Unlike ``async def noop(): pass``, discarding this object without
    awaiting it does **not** trigger 'coroutine was never awaited'.
    Used by :meth:`IteratorWrapper.close` when called from a GC
    finalizer thread where the return value is always discarded.
    """

    __slots__ = ()

    def __await__(self) -> Generator[None, None, None]:
        return iter(())  # type: ignore[return-value]


class ChannelClosed(RuntimeError):
    pass


class ChannelTimeout(asyncio.TimeoutError):
    """Raised when a channel operation times out."""

    pass


class QueueWrapperBase:
    @abstractmethod
    def put(
        self, item: Any, *, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        raise NotImplementedError

    def get(self) -> Any:
        raise NotImplementedError

    def wait_not_full(self, timeout: float) -> None:
        """Wait until the queue has space, ``wake_waiters`` is called, or
        the timeout expires. An unbounded queue always has space.
        """

    def wake_waiters(self) -> None:
        """Wake every thread that waits in ``wait_not_full``."""


class DequeWrapper(QueueWrapperBase):
    __slots__ = ("_lock", "queue")

    def __init__(self) -> None:
        self._lock = _threading.Lock()
        self.queue: Deque[Any] = deque()

    def get(self) -> Any:
        with self._lock:
            if not self.queue:
                raise QueueEmpty
            return self.queue.popleft()

    def put(
        self, item: Any, *, block: bool = True, timeout: Optional[float] = None
    ) -> None:  # noqa: ARG002
        with self._lock:
            self.queue.append(item)


class QueueWrapper(QueueWrapperBase):
    """Bounded thread-safe queue.

    ``get`` and ``put(block=False)`` never block. A producer that finds
    the queue full calls ``wait_not_full`` outside any caller lock.
    """

    __slots__ = ("_condition", "_max_size", "queue")

    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._condition = _threading.Condition()
        self.queue: Deque[Any] = deque()

    def _has_space(self) -> bool:
        return len(self.queue) < self._max_size

    def put(
        self, item: Any, *, block: bool = True, timeout: Optional[float] = None
    ) -> None:
        with self._condition:
            if not self._has_space():
                if not block:
                    raise QueueFull
                if not self._condition.wait_for(self._has_space, timeout):
                    raise QueueFull
            self.queue.append(item)

    def get(self) -> Any:
        with self._condition:
            if not self.queue:
                raise QueueEmpty
            item = self.queue.popleft()
            self._condition.notify()
            return item

    def wait_not_full(self, timeout: float) -> None:
        with self._condition:
            if not self._has_space():
                self._condition.wait(timeout)

    def wake_waiters(self) -> None:
        with self._condition:
            self._condition.notify_all()


def make_queue(max_size: int = 0) -> QueueWrapperBase:
    if max_size > 0:
        return QueueWrapper(max_size)
    return DequeWrapper()


class FromThreadChannel:
    """
    A thread-safe channel for passing data from threads to async code.

    Uses asyncio.Event for efficient waiting instead of polling, which:
    - Eliminates CPU-wasting busy loops
    - Provides immediate wake-up when data is available
    - Supports optional timeout for bounded waiting

    Args:
        maxsize: Maximum queue size (0 = unbounded)
        timeout: Default timeout in seconds for get operations (0 = no timeout)
    """

    __slots__ = ("_lock", "queue", "_closed", "_data_event", "_loop", "_timeout")

    def __init__(self, maxsize: int = 0, timeout: float = 0):
        self._lock = _threading.Lock()
        self.queue: QueueWrapperBase = make_queue(max_size=maxsize)
        self._closed = False
        self._data_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._timeout = timeout

    def _get_event(self) -> asyncio.Event:
        """Get or create the asyncio.Event, ensuring it's bound to the right loop."""
        if self._data_event is None:
            self._loop = asyncio.get_running_loop()
            self._data_event = asyncio.Event()
        return self._data_event

    def _signal_data_available(self) -> None:
        """Signal that data is available. Thread-safe."""
        loop = self._loop
        if loop is not None and self._data_event is not None:
            try:
                loop.call_soon_threadsafe(self._data_event.set)
            except RuntimeError:
                pass  # loop is closed, no waiters to wake

    def close(self) -> None:
        with self._lock:
            self._closed = True
        # Wake producers that wait for space and consumers that wait
        # for data, so that both see that the channel is closed.
        self.queue.wake_waiters()
        self._signal_data_available()

    @property
    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def __enter__(self) -> "FromThreadChannel":
        return self

    def __exit__(
        self,
        exc_type: Type[Exception],
        exc_val: Exception,
        exc_tb: TracebackType,
    ) -> None:
        self.close()

    def put(self, item: Any) -> None:
        """Put an item into the channel. Thread-safe.

        The closed check and the enqueue run under one lock, so the
        channel accepts no item after ``close``. When a bounded queue is
        full, the producer waits for space outside the lock. ``close``
        wakes the producer, and each retry checks the closed flag again.
        Thus producer threads do not block forever when consumers are
        cancelled.
        """
        while True:
            with self._lock:
                if self._closed:
                    raise ChannelClosed
                try:
                    self.queue.put(item, block=False)
                    break
                except QueueFull:
                    pass
            self.queue.wait_not_full(timeout=0.1)

        self._signal_data_available()

    async def get(self, timeout: Optional[float] = None) -> Any:
        """
        Get an item from the channel.

        Args:
            timeout: Timeout in seconds. None uses default, 0 disables timeout.

        Raises:
            ChannelClosed: If the channel is closed and empty.
            ChannelTimeout: If timeout is exceeded.
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        event = self._get_event()

        while True:
            try:
                return self.queue.get()
            except QueueEmpty:
                pass

            if self.is_closed:
                # A producer can put its last item and close the channel
                # between the get above and this check. Drain the queue
                # before the channel is reported closed. Items put before
                # close are visible here because put and close share a lock.
                try:
                    return self.queue.get()
                except QueueEmpty:
                    raise ChannelClosed

            # Clear event before waiting (in case it was set)
            event.clear()

            # Double-check queue after clearing event to avoid race condition
            try:
                return self.queue.get()
            except QueueEmpty:
                pass

            # Wait for data with optional timeout
            if effective_timeout > 0:
                try:
                    await asyncio.wait_for(event.wait(), timeout=effective_timeout)
                except asyncio.TimeoutError:
                    raise ChannelTimeout(
                        f"Channel get timed out after {effective_timeout}s"
                    )
            else:
                await event.wait()

    def __await__(self) -> Any:
        return self.get().__await__()


class IteratorWrapper(Generic[P, T], AsyncIterator):
    __slots__ = (
        "__channel",
        "__close_event",
        "__gen_func",
        "__gen_task",
        "_loop",
        "executor",
    )

    def __init__(
        self,
        gen_func: Callable[P, Generator[T, None, None]],
        loop: Optional[asyncio.AbstractEventLoop] = None,
        max_size: int = 0,
        executor: Optional[Executor] = None,
    ):

        self._loop = loop
        self.executor = executor

        self.__close_event = _threading.Event()
        self.__channel: FromThreadChannel = FromThreadChannel(maxsize=max_size)
        self.__gen_task: Optional[asyncio.Future] = None
        self.__gen_func: Callable = gen_func

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    @property
    def closed(self) -> bool:
        return self.__channel.is_closed

    @staticmethod
    def __throw(e: BaseException) -> NoReturn:
        raise e

    def _in_thread(self) -> None:
        gen: Optional[Generator[Any, None, None]] = None
        with self.__channel:
            try:
                gen = iter(self.__gen_func())

                throw = self.__throw
                if inspect.isgenerator(gen):
                    throw = gen.throw  # type: ignore

                while not self.closed:
                    item = next(gen)
                    try:
                        self.__channel.put((item, False))
                    except Exception as e:
                        throw(e)
                        self.__channel.close()
                        break
                    finally:
                        del item
            except StopIteration:
                return
            except Exception as e:
                if self.closed:
                    return
                self.__channel.put((e, True))
            finally:
                if gen is not None and inspect.isgenerator(gen):
                    with suppress(Exception):
                        gen.close()
                self.__close_event.set()

    def close(self) -> Awaitable[None]:
        self.__channel.close()
        coro = self.wait_closed()
        try:
            return asyncio.ensure_future(coro)
        except RuntimeError:
            # GC finalizer may call close() from a non-event-loop thread
            # where ensure_future fails. Close the abandoned coroutine and
            # fall back to scheduling cleanup via call_soon_threadsafe.
            coro.close()
            try:
                self.loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self.wait_closed()),
                )
            except (RuntimeError, AttributeError):
                pass
            return _ImmediateAwaitable()

    async def wait_closed(self) -> None:
        if self.__gen_task is None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.__close_event.wait)
        await asyncio.gather(self.__gen_task, return_exceptions=True)

    def _run(self) -> Any:
        return self.loop.run_in_executor(self.executor, self._in_thread)

    def __aiter__(self) -> AsyncIterator[T]:
        if not self.loop.is_running():
            raise RuntimeError("Event loop is not running")

        if self.__gen_task is None:
            gen_task = self._run()
            if gen_task is None:
                raise RuntimeError("Iterator task was not created")
            self.__gen_task = gen_task
        return IteratorProxy(self, self.close)

    async def __anext__(self) -> T:
        try:
            item, is_exc = await self.__channel.get()
        except ChannelClosed:
            await self.wait_closed()
            raise StopAsyncIteration

        if is_exc:
            await self.close()
            raise item from item

        return item

    async def __aenter__(self) -> "IteratorWrapper":
        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        # Always wait for the generator thread. A finalizer of the
        # iterator proxy can start close() before this point, and then
        # only the wait below guarantees that the generator finally
        # block has run when the block exits.
        await self.close()


class IteratorProxy(Generic[T], AsyncIterator):
    def __init__(
        self,
        iterator: AsyncIterator[T],
        finalizer: Callable[[], Any],
    ):
        self.__iterator = iterator
        finalize(self, finalizer)

    def __anext__(self) -> Awaitable[T]:
        return self.__iterator.__anext__()
