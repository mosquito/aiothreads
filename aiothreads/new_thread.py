import asyncio
import contextvars
import logging
import threading
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Callable, Dict, Optional, Tuple

from aiothreads.types import EVENT_LOOP, F


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ThreadCall:
    func: Callable[..., Any]
    future: asyncio.Future
    loop: asyncio.AbstractEventLoop
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    context: contextvars.Context = field(default_factory=contextvars.copy_context)

    def __set_result(
        self, result: Optional[Any], exception: Optional[BaseException]
    ) -> None:
        if self.future.done():
            return

        if exception:
            self.future.set_exception(exception)
        else:
            self.future.set_result(result)

    def __in_thread(self) -> None:
        EVENT_LOOP.set(self.loop)
        return self.func(*self.args, **self.kwargs)

    def __call__(self, no_return: bool = False) -> None:
        if self.future.done():
            return

        if self.loop.is_closed():
            log.warning("Event loop is closed. Ignoring %r", self.func)
            raise asyncio.CancelledError

        result, exception = None, None
        try:
            result = self.context.run(self.__in_thread)
        except BaseException as e:
            exception = e

        if no_return:
            return

        if self.loop.is_closed():
            log.warning(
                "Event loop is closed. Forget execution result for %r",
                self.func,
            )
            raise asyncio.CancelledError
        self.loop.call_soon_threadsafe(self.__set_result, result, exception)


def run_in_new_thread(
    func: F,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
    detach: bool = True,
    no_return: bool = False,
) -> asyncio.Future:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    payload = ThreadCall(
        func=func,
        args=args,
        kwargs=kwargs,
        loop=loop,
        future=future,
    )

    thread = threading.Thread(
        target=payload,
        name=func.__name__,
        kwargs=dict(no_return=no_return),
        daemon=detach,
    )
    loop.call_soon(thread.start)
    return future
