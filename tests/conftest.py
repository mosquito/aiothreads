import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from aiothreads import threaded, threaded_separate


@pytest.fixture
async def executor():
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(16))


@pytest.fixture
def timer():
    @contextmanager
    def timer(expected_time=0, *, dispersion=0.5):
        expected_time = float(expected_time)
        dispersion_value = expected_time * dispersion

        now = time.time()

        yield

        delta = time.time() - now

        lower_bound = expected_time - dispersion_value
        upper_bound = expected_time + dispersion_value

        assert lower_bound < delta < upper_bound

    return timer


@pytest.fixture(params=(threaded, threaded_separate))
def threaded_decorator(request, executor):
    return request.param
