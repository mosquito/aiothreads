"""Concurrent stress tests for threading.Lock protection (nogil support).

These tests verify that the locks added for free-threaded Python (PEP 703)
work correctly. They pass under the GIL (documenting the contract) and will
catch regressions under nogil (python -X gil=0).
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from queue import Empty as QueueEmpty

from aiothreads.iterator_wrapper import DequeWrapper, FromThreadChannel
from aiothreads.threaded_iterable import threaded_iterable
from aiothreads.threads import threaded


NUM_THREADS = 8
ITEMS_PER_THREAD = 1000


def test_deque_wrapper_concurrent_put_get():
    """Multiple producer/consumer threads hammering DequeWrapper."""
    wrapper = DequeWrapper()
    total_items = NUM_THREADS * ITEMS_PER_THREAD
    produced = threading.Event()
    results: list = []
    errors: list = []

    def producer(thread_id: int) -> None:
        try:
            for i in range(ITEMS_PER_THREAD):
                wrapper.put((thread_id, i))
        except Exception as e:
            errors.append(e)

    def consumer() -> None:
        collected = 0
        while collected < total_items:
            try:
                item = wrapper.get()
                results.append(item)
                collected += 1
            except QueueEmpty:
                if produced.is_set():
                    # Producers done; try once more then break
                    try:
                        item = wrapper.get()
                        results.append(item)
                        collected += 1
                    except QueueEmpty:
                        break

    # Run producers in parallel
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
        futures = [pool.submit(producer, tid) for tid in range(NUM_THREADS)]
        for f in futures:
            f.result()
    produced.set()

    # Drain remaining items with a single consumer
    consumer()

    assert not errors, f"Producer errors: {errors}"
    assert len(results) == total_items


def test_channel_closed_flag_visibility():
    """One thread calls close(), others spin-check is_closed."""
    channel = FromThreadChannel()
    seen_closed: list[bool] = []
    barrier = threading.Barrier(NUM_THREADS + 1)

    def checker() -> None:
        barrier.wait()
        # Spin until closed
        while not channel.is_closed:
            pass
        seen_closed.append(True)

    threads = [threading.Thread(target=checker) for _ in range(NUM_THREADS)]
    for t in threads:
        t.start()

    barrier.wait()
    channel.close()

    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive(), "Checker thread did not see close in time"

    assert len(seen_closed) == NUM_THREADS


def test_threaded_descriptor_concurrent_get():
    """Multiple threads calling obj.method on a @threaded-decorated method."""

    class MyClass:
        @threaded
        def work(self) -> int:
            return 42

    obj = MyClass()
    results: list = []
    errors: list = []

    def accessor() -> None:
        try:
            for _ in range(ITEMS_PER_THREAD):
                bound = obj.work  # triggers __get__
                results.append(bound)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
        futures = [pool.submit(accessor) for _ in range(NUM_THREADS)]
        for f in futures:
            f.result()

    assert not errors, f"Descriptor errors: {errors}"
    assert len(results) == NUM_THREADS * ITEMS_PER_THREAD
    # All should be the same cached BoundThreaded instance
    assert len(set(id(r) for r in results)) == 1


def test_threaded_iterable_descriptor_concurrent_get():
    """Multiple threads calling obj.method on a @threaded_iterable method."""

    class MyClass:
        @threaded_iterable
        def generate(self):
            yield 1
            yield 2
            yield 3

    obj = MyClass()
    results: list = []
    errors: list = []

    def accessor() -> None:
        try:
            for _ in range(ITEMS_PER_THREAD):
                bound = obj.generate  # triggers __get__
                results.append(bound)
        except Exception as e:
            errors.append(e)

    with ThreadPoolExecutor(max_workers=NUM_THREADS) as pool:
        futures = [pool.submit(accessor) for _ in range(NUM_THREADS)]
        for f in futures:
            f.result()

    assert not errors, f"Descriptor errors: {errors}"
    assert len(results) == NUM_THREADS * ITEMS_PER_THREAD
    # All should be the same cached BoundThreadedIterable instance
    assert len(set(id(r) for r in results)) == 1
