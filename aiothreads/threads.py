import asyncio
import contextvars
import inspect
import logging
import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from functools import partial
from types import MappingProxyType
from typing import (
    Any,
    Awaitable,
    Callable,
    Concatenate,
    Generator,
    Generic,
    MutableMapping,
    Optional,
    overload,
)
from weakref import WeakKeyDictionary

from .iterator_wrapper import IteratorWrapper
from .new_thread import run_in_new_thread
from .threaded_iterable import threaded_iterable
from .types import BP, EVENT_LOOP, P, S, T


log = logging.getLogger(__name__)

THREADED_ITERABLE_DEFAULT_MAX_SIZE = int(
    os.getenv("THREADED_ITERABLE_DEFAULT_MAX_SIZE", 1024)
)


class ThreadPoolException(RuntimeError):
    pass


def run_in_executor(
    func: Callable[..., T],
    executor: Optional[ThreadPoolExecutorBase] = None,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
) -> Awaitable[T]:
    try:
        loop = asyncio.get_running_loop()
        context = contextvars.copy_context()

        def in_thread() -> T:
            nonlocal func, args, kwargs, loop, context
            EVENT_LOOP.set(loop)
            return context.run(func, *args, **kwargs)

        return loop.run_in_executor(executor, in_thread)
    except RuntimeError:
        # In case the event loop is not running right now is
        # returning coroutine to avoid DeprecationWarning in Python 3.10
        async def lazy_wrapper() -> T:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(executor, partial(func, *args, **kwargs))

        return lazy_wrapper()


async def _awaiter(future: asyncio.Future) -> T:
    try:
        result = await future
        return result
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


class ThreadedBase(Generic[P, T], ABC):
    func: Callable[P, T]

    @abstractmethod
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def sync_call(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return self.func(*args, **kwargs)

    def async_call(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        EVENT_LOOP.set(asyncio.get_running_loop())
        return run_in_executor(func=self.func, args=args, kwargs=kwargs)

    def __repr__(self) -> str:
        f = getattr(self.func, "func", self.func)
        name = getattr(f, "__name__", f.__class__.__name__)
        return f"<{self.__class__.__name__} {name} at {id(self):#x}>"

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        return self.async_call(*args, **kwargs)


class Threaded(ThreadedBase[P, T]):
    func_type: type

    def __init__(self, func: Callable[P, T]) -> None:
        self.__cache: MutableMapping[Any, Any] = WeakKeyDictionary()

        if isinstance(func, staticmethod):
            self.func_type = staticmethod
            self.func = func.__func__
        elif isinstance(func, classmethod):
            self.func_type = classmethod
            self.func = func.__func__
        else:
            self.func_type = type(func)
            self.func = func

        if inspect.iscoroutinefunction(self.func):
            raise TypeError("Can not wrap coroutine")
        if inspect.isgeneratorfunction(self.func):
            raise TypeError("Can not wrap generator function")

    @overload
    def __get__(
        self: "Threaded[Concatenate[S, BP], T]",
        instance: S,
        owner: Optional[type] = ...,
    ) -> "BoundThreaded[BP, T]": ...

    @overload
    def __get__(
        self: "Threaded[P, T]",
        instance: None,
        owner: Optional[type] = ...,
    ) -> "Threaded[P, T]": ...

    def __get__(
        self,
        instance: Any,
        owner: Optional[type] = None,
    ) -> "Threaded[P, T] | BoundThreaded[Any, T]":
        key = instance
        result: Any
        if key is not None and key in self.__cache:
            return self.__cache[key]
        if self.func_type is staticmethod:
            result = self
        elif self.func_type is classmethod:
            cls = owner if instance is None else type(instance)
            result = BoundThreaded(self.func, cls)
        elif instance is not None:
            result = BoundThreaded(self.func, instance)
        else:
            result = self

        if key is not None:
            self.__cache[key] = result
        return result


class BoundThreaded(ThreadedBase[P, T]):
    __instance: Any

    def __init__(self, func: Callable[..., T], instance: Any) -> None:
        self.__instance = instance
        self.func = lambda *args, **kwargs: func(instance, *args, **kwargs)


@overload
def threaded(func: Callable[P, T]) -> Threaded[P, T]: ...


@overload
def threaded(
    func: Callable[P, Generator[T, None, None]],
) -> Callable[P, IteratorWrapper[P, T]]: ...


def threaded(
    func: Callable[P, T] | Callable[P, Generator[T, None, None]],
) -> Threaded[P, T] | Callable[P, IteratorWrapper[P, T]]:
    if inspect.isgeneratorfunction(func):
        return threaded_iterable(
            func,
            max_size=THREADED_ITERABLE_DEFAULT_MAX_SIZE,
        )

    return Threaded(func)  # type: ignore


class ThreadedSeparate(Threaded[P, T]):
    __slots__ = Threaded.__slots__ + ("detach",)

    def __init__(self, func: Callable[P, T], detach: bool = True) -> None:
        super().__init__(func)
        self.detach = detach

    def async_call(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        return run_in_new_thread(
            self.func, args=args, kwargs=kwargs, detach=self.detach
        )


def threaded_separate(
    func: Callable[P, T],
    detach: bool = True,
) -> ThreadedSeparate[P, T]:
    if isinstance(func, bool):
        # noinspection PyTypeChecker
        return partial(threaded_separate, detach=detach)

    if inspect.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    return ThreadedSeparate(func, detach=detach)
