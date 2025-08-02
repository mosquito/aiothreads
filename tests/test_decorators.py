import asyncio
import contextvars
import time

import pytest
from aiothreads import threaded, threaded_iterable
from async_timeout import timeout


async def test_threaded(threaded_decorator, timer):
    sleep = threaded_decorator(time.sleep)

    with timer(1):
        await asyncio.wait_for(
            asyncio.gather(sleep(1), sleep(1), sleep(1), sleep(1), sleep(1)), timeout=5,
        )


async def test_threaded_exc(threaded_decorator):
    @threaded_decorator
    def worker():
        raise Exception

    number = 90

    done, _ = await asyncio.wait(
        [worker() for _ in range(number)], timeout=1,
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
