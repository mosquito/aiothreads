import asyncio
import contextvars
import time
from abc import ABC, ABCMeta, abstractmethod

import pytest
from aiothreads import threaded, threaded_iterable
from async_timeout import timeout


async def test_threaded(threaded_decorator, timer):
    sleep = threaded_decorator(time.sleep)

    with timer(1):
        await asyncio.wait_for(
            asyncio.gather(sleep(1), sleep(1), sleep(1), sleep(1), sleep(1)),
            timeout=5,
        )


async def test_threaded_exc(threaded_decorator):
    @threaded_decorator
    def worker():
        raise Exception

    number = 90

    done, _ = await asyncio.wait(
        [worker() for _ in range(number)],
        timeout=1,
    )

    for task in done:
        with pytest.raises(Exception):
            task.result()


async def test_simple(threaded_decorator, timer):
    sleep = threaded_decorator(time.sleep)

    async with timeout(2):
        with timer(1):
            await asyncio.gather(
                sleep(1),
                sleep(1),
                sleep(1),
                sleep(1),
            )


async def test_context_vars(threaded_decorator):
    ctx_var = contextvars.ContextVar("test")  # type: ignore

    @threaded_decorator
    def test(arg):
        value = ctx_var.get()
        assert value == arg * arg

    futures = []

    for i in range(8):
        ctx_var.set(i * i)
        futures.append(test(i))

    await asyncio.gather(*futures)


async def test_threaded_class_func():
    @threaded
    def foo():
        return 42

    assert foo.sync_call() == 42
    assert await foo() == 42
    assert await foo.async_call() == 42


async def test_threaded_class_method():
    class TestClass:
        @threaded
        def foo(self):
            return 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_class_staticmethod():
    class TestClass:
        @threaded
        @staticmethod
        def foo():
            return 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_class_classmethod():
    class TestClass:
        @threaded
        @classmethod
        def foo(cls):
            return 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_iterator_class_func():
    @threaded_iterable
    def foo():
        yield 42

    assert foo is foo
    assert list(foo.sync_call()) == [42]
    assert [x async for x in foo()] == [42]
    assert [x async for x in foo.async_call()] == [42]


async def test_threaded_iterator_class_method():
    class TestClass:
        @threaded_iterable
        def foo(self):
            yield 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_iterator_class_staticmethod():
    class TestClass:
        @threaded_iterable
        @staticmethod
        def foo():
            yield 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_iterator_class_classmethod():
    class TestClass:
        @threaded_iterable
        @classmethod
        def foo(cls):
            yield 42

    instance = TestClass()
    assert instance.foo is instance.foo
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_abc_method():
    class Base(ABC):
        @abstractmethod
        def foo(self) -> int: ...

    class Impl(Base):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 42

    instance = Impl()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42


async def test_threaded_iterable_abc_method():
    class Base(ABC):
        @abstractmethod
        def foo(self): ...

    class Impl(Base):
        @threaded_iterable
        def foo(self):
            yield 42

    instance = Impl()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]


async def test_threaded_deep_abc_chain():
    class Base(ABC):
        @abstractmethod
        def foo(self) -> int: ...

        @abstractmethod
        def bar(self) -> int: ...

    class Middle(Base):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 1

    class Leaf(Middle):
        @threaded
        def bar(self) -> int:  # type: ignore[override]
            return 2

    instance = Leaf()
    assert instance.foo.sync_call() == 1
    assert await instance.foo() == 1
    assert instance.bar.sync_call() == 2
    assert await instance.bar() == 2


async def test_threaded_iterable_deep_abc_chain():
    class Base(ABC):
        @abstractmethod
        def foo(self): ...

        @abstractmethod
        def bar(self): ...

    class Middle(Base):
        @threaded_iterable
        def foo(self):
            yield 1

    class Leaf(Middle):
        @threaded_iterable
        def bar(self):
            yield 2

    instance = Leaf()
    assert list(instance.foo.sync_call()) == [1]
    assert [x async for x in instance.foo()] == [1]
    assert list(instance.bar.sync_call()) == [2]
    assert [x async for x in instance.bar()] == [2]


async def test_threaded_abc_diamond_inheritance():
    class Base(ABC):
        @abstractmethod
        def foo(self) -> int: ...

    class Left(Base):
        pass

    class Right(Base):
        pass

    class Diamond(Left, Right):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 42

    instance = Diamond()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42


async def test_threaded_custom_metaclass():
    class Registry(type):
        classes: list = []

        def __new__(mcs, name, bases, namespace):
            cls = super().__new__(mcs, name, bases, namespace)
            mcs.classes.append(cls)
            return cls

    class Base(metaclass=Registry):
        pass

    class Impl(Base):
        @threaded
        def foo(self) -> int:
            return 42

    instance = Impl()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert Impl in Registry.classes


async def test_threaded_iterable_custom_metaclass():
    class Registry(type):
        classes: list = []

        def __new__(mcs, name, bases, namespace):
            cls = super().__new__(mcs, name, bases, namespace)
            mcs.classes.append(cls)
            return cls

    class Base(metaclass=Registry):
        pass

    class Impl(Base):
        @threaded_iterable
        def foo(self):
            yield 42

    instance = Impl()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert Impl in Registry.classes


async def test_threaded_metaclass_with_getattr_inspection():
    """Metaclass that inspects all methods via getattr during class creation."""

    class InspectingMeta(type):
        def __new__(mcs, name, bases, namespace):
            cls = super().__new__(mcs, name, bases, namespace)
            # Simulate what ABCMeta does: getattr on every callable
            for attr_name in list(namespace):
                if not attr_name.startswith("_"):
                    getattr(cls, attr_name)
            return cls

    class Impl(metaclass=InspectingMeta):
        @threaded
        def foo(self) -> int:
            return 42

        @threaded_iterable
        def bar(self):
            yield 99

    instance = Impl()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert list(instance.bar.sync_call()) == [99]
    assert [x async for x in instance.bar()] == [99]


async def test_threaded_abc_combined_with_custom_metaclass():
    """ABCMeta combined with a custom metaclass via diamond."""

    class CustomMeta(type):
        initialized: list = []

        def __init__(cls, name, bases, namespace):
            super().__init__(name, bases, namespace)
            CustomMeta.initialized.append(name)

    class CombinedMeta(ABCMeta, CustomMeta):
        pass

    class Base(ABC, metaclass=CombinedMeta):
        @abstractmethod
        def foo(self) -> int: ...

    class Impl(Base):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 42

    instance = Impl()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert "Impl" in CustomMeta.initialized


async def test_threaded_iterable_abc_combined_with_custom_metaclass():
    class CustomMeta(type):
        initialized: list = []

        def __init__(cls, name, bases, namespace):
            super().__init__(name, bases, namespace)
            CustomMeta.initialized.append(name)

    class CombinedMeta(ABCMeta, CustomMeta):
        pass

    class Base(ABC, metaclass=CombinedMeta):
        @abstractmethod
        def foo(self): ...

    class Impl(Base):
        @threaded_iterable
        def foo(self):
            yield 42

    instance = Impl()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert "Impl" in CustomMeta.initialized


async def test_threaded_abc_override_in_grandchild():
    """Override a threaded method further down the chain."""

    class Base(ABC):
        @abstractmethod
        def foo(self) -> int: ...

    class Middle(Base):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 1

    class Grandchild(Middle):
        @threaded
        def foo(self) -> int:  # type: ignore[override]
            return 2

    mid = Middle()
    assert mid.foo.sync_call() == 1
    assert await mid.foo() == 1

    leaf = Grandchild()
    assert leaf.foo.sync_call() == 2
    assert await leaf.foo() == 2
