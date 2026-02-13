import asyncio

from aiothreads.new_thread import run_in_new_thread


async def test_no_return():
    called = False

    def worker():
        nonlocal called
        called = True

    run_in_new_thread(worker, no_return=True)
    await asyncio.sleep(0.5)
    assert called
