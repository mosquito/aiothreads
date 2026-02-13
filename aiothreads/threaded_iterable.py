from abc import ABC, abstractmethod
from functools import partial
from typing import (
    Any,
    Callable,
    Concatenate,
    Generator,
    Generic,
    MutableMapping,
    Optional,
    Union,
    overload,
)
from weakref import WeakKeyDictionary

from .iterator_wrapper import IteratorWrapper
from .new_thread import run_in_new_thread
from .types import BP, P, S, T


class ThreadedIterableBase(Generic[P, T], ABC):
    func: Callable[P, Generator[T, None, None]]
    max_size: int

    @abstractmethod
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def sync_call(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Generator[T, None, None]:
        return self.func(*args, **kwargs)

    def async_call(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> IteratorWrapper[P, T]:
        return self.create_wrapper(*args, **kwargs)

    def create_wrapper(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> IteratorWrapper[P, T]:
        return IteratorWrapper(
            partial(self.func, *args, **kwargs),
            max_size=self.max_size,
        )

    def __call__(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> IteratorWrapper[P, T]:
        return self.async_call(*args, **kwargs)


class ThreadedIterable(ThreadedIterableBase[P, T]):
    func_type: type

    def __init__(
        self,
        func: Callable[P, Generator[T, None, None]],
        max_size: int = 0,
    ) -> None:
        if isinstance(func, staticmethod):
            self.func_type = staticmethod
            actual_func = func.__func__
        elif isinstance(func, classmethod):
            self.func_type = classmethod
            actual_func = func.__func__
        else:
            self.func_type = type(func)
            actual_func = func

        self.func = actual_func
        self.max_size = max_size
        self.__cache: MutableMapping[Any, Any] = WeakKeyDictionary()

    @overload
    def __get__(
        self: "ThreadedIterable[Concatenate[S, BP], T]",
        instance: S,
        owner: Optional[type] = ...,
    ) -> "BoundThreadedIterable[BP, T]": ...

    @overload
    def __get__(
        self: "ThreadedIterable[P, T]",
        instance: None,
        owner: Optional[type] = ...,
    ) -> "ThreadedIterable[P, T]": ...

    def __get__(
        self,
        instance: Any,
        owner: Optional[type] = None,
    ) -> "ThreadedIterable[P, T] | BoundThreadedIterable[Any, T]":
        key = instance
        result: Any
        if key is not None and key in self.__cache:
            return self.__cache[key]

        if self.func_type is staticmethod:
            result = self
        elif self.func_type is classmethod:
            cls = owner if instance is None else type(instance)
            result = BoundThreadedIterable(self.func, cls, self.max_size)
        elif instance is not None:
            result = BoundThreadedIterable(self.func, instance, self.max_size)
        else:
            result = self

        if key is not None:
            self.__cache[key] = result
        return result


class BoundThreadedIterable(ThreadedIterableBase[P, T]):
    __instance: Any

    def __init__(
        self,
        func: Callable[..., Generator[T, None, None]],
        instance: Any,
        max_size: int = 0,
    ) -> None:
        self.__instance = instance
        self.func = lambda *args, **kwargs: func(instance, *args, **kwargs)
        self.max_size = max_size


@overload
def threaded_iterable(
    func: Callable[P, Generator[T, None, None]],
    *,
    max_size: int = 0,
) -> "ThreadedIterable[P, T]": ...


@overload
def threaded_iterable(
    *,
    max_size: int = 0,
) -> Callable[
    [Callable[P, Generator[T, None, None]]],
    ThreadedIterable[P, T],
]: ...


def threaded_iterable(
    func: Optional[Callable[P, Generator[T, None, None]]] = None,
    *,
    max_size: int = 0,
) -> Union[
    ThreadedIterable[P, T],
    Callable[
        [Callable[P, Generator[T, None, None]]],
        ThreadedIterable[P, T],
    ],
]:
    if func is None:
        return lambda f: ThreadedIterable(f, max_size=max_size)

    return ThreadedIterable(func, max_size=max_size)


class IteratorWrapperSeparate(IteratorWrapper):
    def _run(self) -> Any:
        return run_in_new_thread(self._in_thread)


class ThreadedIterableSeparate(ThreadedIterable[P, T]):
    def create_wrapper(
        self,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> IteratorWrapperSeparate:
        return IteratorWrapperSeparate(
            partial(self.func, *args, **kwargs),
            max_size=self.max_size,
        )


@overload
def threaded_iterable_separate(
    func: Callable[P, Generator[T, None, None]],
    *,
    max_size: int = 0,
) -> "ThreadedIterable[P, T]": ...


@overload
def threaded_iterable_separate(
    *,
    max_size: int = 0,
) -> Callable[
    [Callable[P, Generator[T, None, None]]],
    ThreadedIterableSeparate[P, T],
]: ...


def threaded_iterable_separate(
    func: Optional[Callable[P, Generator[T, None, None]]] = None,
    *,
    max_size: int = 0,
) -> Union[
    ThreadedIterable[P, T],
    Callable[
        [Callable[P, Generator[T, None, None]]],
        ThreadedIterableSeparate[P, T],
    ],
]:
    if func is None:
        return lambda f: ThreadedIterableSeparate(f, max_size=max_size)

    return ThreadedIterableSeparate(func, max_size=max_size)
