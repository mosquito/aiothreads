import asyncio
import threading
import time

from aiothreads.new_thread import ThreadCall, run_in_new_thread


async def test_no_return():
    called = False

    def worker():
        nonlocal called
        called = True

    run_in_new_thread(worker, no_return=True)
    await asyncio.sleep(0.5)
    assert called


def test_thread_call_no_unhandled_exception_on_closed_loop():
    """RACE-10: ThreadCall must not raise unhandled CancelledError in a thread
    when the loop closes during execution. It should log and return instead."""
    unhandled_exceptions: list = []
    original_hook = threading.excepthook

    def capture_hook(args):
        unhandled_exceptions.append(args)

    threading.excepthook = capture_hook
    try:
        loop = asyncio.new_event_loop()
        future = loop.create_future()

        def slow_func():
            time.sleep(0.2)
            return 42

        payload = ThreadCall(
            func=slow_func,
            args=(),
            kwargs={},
            loop=loop,
            future=future,
        )

        # Start the thread
        t = threading.Thread(target=payload, daemon=True)
        t.start()

        # Close the loop while the thread is running
        time.sleep(0.05)
        loop.close()

        t.join(timeout=5)
        assert not t.is_alive(), "Thread hung after loop close"

        # No unhandled thread exceptions should have occurred
        assert len(unhandled_exceptions) == 0, (
            f"Unhandled exceptions in thread: {unhandled_exceptions}"
        )
    finally:
        threading.excepthook = original_hook


async def test_thread_starts_immediately():
    """RACE-17: Thread must start immediately, not deferred via call_soon."""
    started = threading.Event()

    def worker():
        started.set()

    run_in_new_thread(worker, no_return=True)
    # Thread should start without yielding to event loop
    started.wait(timeout=5)
    assert started.is_set(), "Thread did not start immediately"
