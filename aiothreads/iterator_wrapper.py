import asyncio
import inspect
from abc import abstractmethod
from collections import deque
from concurrent.futures import Executor
from queue import Empty as QueueEmpty
from queue import Queue
from types import TracebackType
from typing import Any, AsyncIterator, Awaitable, Callable, Deque, Generator, Generic, NoReturn, Optional, Type, Union
from weakref import finalize

from .types import P, T


class ChannelClosed(RuntimeError):
    pass


class ChannelTimeout(asyncio.TimeoutError):
    """Raised when a channel operation times out."""
    pass


class QueueWrapperBase:
    @abstractmethod
    def put(self, item: Any) -> None:
        raise NotImplementedError

    def get(self) -> Any:
        raise NotImplementedError


class DequeWrapper(QueueWrapperBase):
    __slots__ = "queue",

    def __init__(self) -> None:
        self.queue: Deque[Any] = deque()

    def get(self) -> Any:
        if not self.queue:
            raise QueueEmpty
        return self.queue.popleft()

    def put(self, item: Any) -> None:
        return self.queue.append(item)


class QueueWrapper(QueueWrapperBase):
    __slots__ = "queue",

    def __init__(self, max_size: int) -> None:
        self.queue: Queue = Queue(maxsize=max_size)

    def put(self, item: Any) -> None:
        return self.queue.put(item)

    def get(self) -> Any:
        return self.queue.get_nowait()


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

    __slots__ = ("queue", "_closed", "_data_event", "_loop", "_timeout")

    def __init__(self, maxsize: int = 0, timeout: float = 0):
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
        if self._loop is not None and self._data_event is not None:
            self._loop.call_soon_threadsafe(self._data_event.set)

    def close(self) -> None:
        self._closed = True
        # Wake up any waiters so they can see the channel is closed
        self._signal_data_available()

    @property
    def is_closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "FromThreadChannel":
        return self

    def __exit__(
        self, exc_type: Type[Exception],
        exc_val: Exception, exc_tb: TracebackType,
    ) -> None:
        self.close()

    def put(self, item: Any) -> None:
        """Put an item into the channel. Thread-safe."""
        if self.is_closed:
            raise ChannelClosed

        self.queue.put(item)
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
                result = self.queue.get()
                return result
            except QueueEmpty:
                if self.is_closed:
                    raise ChannelClosed

                # Clear event before waiting (in case it was set)
                event.clear()

                # Double-check queue after clearing event to avoid race condition
                try:
                    result = self.queue.get()
                    return result
                except QueueEmpty:
                    pass

                # Wait for data with optional timeout
                if effective_timeout > 0:
                    try:
                        await asyncio.wait_for(event.wait(), timeout=effective_timeout)
                    except asyncio.TimeoutError:
                        raise ChannelTimeout(f"Channel get timed out after {effective_timeout}s")
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

        self.__close_event = asyncio.Event()
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
    def __throw(_: Any) -> NoReturn:
        raise

    def _in_thread(self) -> None:
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
                self.loop.call_soon_threadsafe(self.__close_event.set)

    def close(self) -> Awaitable[None]:
        self.__channel.close()
        # if the iterator inside thread is blocked on `.put()`
        # we need to wake it up to signal that it is closed.
        try:
            self.__channel.queue.get()
        except QueueEmpty:
            pass
        return asyncio.ensure_future(self.wait_closed())

    async def wait_closed(self) -> None:
        await self.__close_event.wait()
        if self.__gen_task:
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
        self, exc_type: Any, exc_val: Any,
        exc_tb: Any,
    ) -> None:
        if self.closed:
            return

        await self.close()


class IteratorProxy(Generic[T], AsyncIterator):
    def __init__(
        self, iterator: AsyncIterator[T],
        finalizer: Callable[[], Any],
    ):
        self.__iterator = iterator
        finalize(self, finalizer)

    def __anext__(self) -> Awaitable[T]:
        return self.__iterator.__anext__()
