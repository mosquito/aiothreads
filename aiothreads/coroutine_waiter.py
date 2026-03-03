import asyncio
import threading
from typing import Any, Awaitable, Callable, Coroutine, Optional

from aiothreads.types import EVENT_LOOP, T


class CoroutineWaiter:
    def __init__(
        self,
        coroutine: Coroutine[Any, Any, T],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.__coro: Coroutine[Any, Any, T] = coroutine
        self.__loop = loop or EVENT_LOOP.get()
        self.__event = threading.Event()
        self.__result: Optional[T] = None
        self.__exception: Optional[BaseException] = None

    def _on_result(self, task: asyncio.Future) -> None:
        try:
            self.__exception = task.exception()
            if self.__exception is None:
                self.__result = task.result()
        except asyncio.CancelledError as e:
            self.__exception = e
        finally:
            self.__event.set()

    def _awaiter(self) -> None:
        task: asyncio.Future = self.__loop.create_task(self.__coro)
        task.add_done_callback(self._on_result)

    def start(self) -> None:
        self.__loop.call_soon_threadsafe(self._awaiter)

    def wait(self) -> Any:
        while not self.__event.wait(timeout=1.0):
            if self.__loop.is_closed():
                raise RuntimeError(
                    "Event loop closed before coroutine could be scheduled",
                )
        if self.__exception is not None:
            raise self.__exception
        return self.__result


def wait_coroutine(
    coro: Coroutine[Any, Any, T],
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> T:
    waiter = CoroutineWaiter(coro, loop)
    waiter.start()
    return waiter.wait()


def sync_wait_coroutine(
    loop: Optional[asyncio.AbstractEventLoop],
    coro_func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    return wait_coroutine(coro_func(*args, **kwargs), loop=loop)


def sync_await(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    async def awaiter() -> T:
        return await func(*args, **kwargs)

    return wait_coroutine(awaiter())
