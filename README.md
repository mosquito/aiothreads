# aiothreads Documentation

[![PyPI version](https://img.shields.io/pypi/v/aiothreads.svg)](https://pypi.org/project/aiothreads/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/aiothreads.svg)](https://pypi.org/project/aiothreads/)
[![License](https://img.shields.io/pypi/l/aiothreads.svg)](https://pypi.org/project/aiothreads/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/aiothreads.svg)](https://pypi.org/project/aiothreads/)
[![Coverage Status](https://coveralls.io/repos/github/mosquito/aiothreads/badge.svg?branch=master)](https://coveralls.io/github/mosquito/aiothreads?branch=master)

## Overview

`aiothreads` is a Python library that provides seamless integration between asyncio and thread-based execution. It
offers decorators and utilities to run synchronous functions and generators in threads while maintaining clean
async/await syntax in your asyncio applications.

### Why aiothreads?

While Python 3.9+ provides `asyncio.to_thread()` for running sync functions in threads, `aiothreads` goes far beyond
this basic functionality:

**Limitations of `asyncio.to_thread()`:**

- No support for generators or iterators
- For support for long-running or blocking operations you have to create a separate executors
- No way to calling async code from threads

**asyncio example**

<!-- name: test_asyncio_to_thread_comparison -->
```python
import asyncio
import time


def sync_function(a, b):
    time.sleep(0.01)  # Simulation of blocking call
    return a + b


async def main():
    # Only works for simple functions
    # No support for generators
    result = await asyncio.to_thread(sync_function, 1, 2)
    assert result == 3


asyncio.run(main())
```

**aiothreads - comprehensive solution**

<!-- name: test_comprehensive_example -->
```python
import asyncio
import time
from aiothreads import threaded, threaded_iterable, sync_await


def blocking_operation():
    time.sleep(0.01)  # Simulation of blocking call
    return "sync_result"


def expensive_data_source():
    """Simulation of expensive data source"""
    return range(20)


@threaded
def mixed_sync_async():
    sync_result = blocking_operation()

    # Calling async code from thread
    sync_await(asyncio.sleep, 0.01)
    return sync_result


@threaded_iterable(max_size=100)
def data_stream():
    # Automatic backpressure control
    for item in expensive_data_source():
        yield item


async def main():
    # Rich functionality with clean syntax
    result = await mixed_sync_async()
    assert result == "sync_result"

    # Stream processing with memory control
    items = []
    async for item in data_stream():
        items.append(item)
        if len(items) >= 10:
            break  # Automatically stops sync generator thread execution!

    assert len(items) == 10


asyncio.run(main())
```

### Key Features

- **Zero Dependencies**: Pure Python implementation with no external dependencies
- **Simple Decorators**: Transform sync functions into async-compatible versions with `@threaded`
- **Generator Support**: Convert sync generators to async iterators with `@threaded_iterable`
- **Thread Isolation**: Run code in separate threads with `@threaded_separate`
- **Async-to-Sync Bridge**: Call async code from synchronous threads
- **Context Variable Support**: Proper context propagation across thread boundaries
- **Method Support**: Works with instance methods, class methods, and static methods
- **Full Type Safety**: Complete typing support with `ParamSpec` and `TypeVar` for static type checkers
- **Consistent Interface**: All decorated functions become objects with `sync_call`, `async_call`, and
  `__call__` (alias for `async_call`) methods

## Quick Start

### Installation

```bash
# Assuming standard installation method
pip install aiothreads
```

### Basic Usage

<!-- name: test_basic_usage -->
```python
import asyncio
import time
from aiothreads import threaded


@threaded
def cpu_intensive_task(n):
    """A blocking function that will run in a thread"""
    time.sleep(0.01)  # Simulate CPU work
    return n * n


async def main():
    # Run multiple blocking operations concurrently
    tasks = [cpu_intensive_task(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    assert results == [0, 1, 4, 9, 16]


asyncio.run(main())
```

## Working With Threads

### Choosing the Right Decorator

| Use Case                      | Recommended Decorator         | Reason                                           |
|-------------------------------|-------------------------------|--------------------------------------------------|
| Short I/O operations (< 30s)  | `@threaded`                   | Efficient resource reuse                         |
| CPU-bound tasks (< 30s)       | `@threaded`                   | Controlled concurrency                           |
| Blocking pipe/stream reading  | `@threaded_separate`          | Won't block thread pool, creates a separate thread |
| Operations that may hang      | `@threaded_separate`          | Isolation from pool                              |
| Continuous monitoring tasks   | `@threaded_separate`          | Don't monopolize pool workers                    |
| High-frequency short tasks    | `@threaded`                   | Lower overhead                                   |
| Resource-intensive generators | `@threaded_iterable`          | Controlled memory usage                          |
| Long-lived data streams       | `@threaded_iterable_separate` | Complete isolation                               |

**Thread Pool Benefits:**

- Automatic resource management
- Built-in concurrency limits
- Lower overhead for frequent operations
- Graceful shutdown handling

**Separate Thread Benefits:**

- Complete isolation
- No impact on other threaded operations
- Suitable for blocking/hanging operations
- Won't exhaust thread pool workers

**Separate Thread Risks:**

- Be careful and not create too many separate threads

### The `@threaded` Decorator

The `@threaded` decorator converts synchronous functions to run in the asyncio thread pool:

<!-- name: test_threaded_decorator -->
```python
import asyncio
import time
from aiothreads import threaded


@threaded
def fetch_url(url: str) -> str:
    """Simulation of blocking HTTP request"""
    time.sleep(0.01)  # Simulation of blocking call
    return f"content of {url}"


async def main():
    urls = ['http://example.com', 'http://httpbin.org/json']

    # Both requests run concurrently in separate threads
    results = await asyncio.gather(*[fetch_url(url) for url in urls])
    assert len(results) == 2
    assert all(r.startswith("content of") for r in results)


asyncio.run(main())
```

**Decorated Function Interface**

When you decorate a function with `@threaded`, it becomes a `Threaded` object with three calling methods:

<!-- name: test_decorated_function_interface -->
```python
import asyncio
from aiothreads import threaded


@threaded
def compute(x: int, y: int) -> int:
    return x + y


async def main():
    # Three ways to call the function:

    # 1. Default async call (same as __call__)
    result = await compute(1, 2)
    assert result == 3

    # 2. Explicit async call
    result = await compute.async_call(1, 2)
    assert result == 3

    # 3. Accessing the sync call method
    # This runs the function as usual, blocking the thread
    # and returning the result directly
    result = compute.sync_call(1, 2)
    assert result == 3


asyncio.run(main())
```

**Type Safety**

The decorators preserve type information for static type checkers:

<!-- name: test_type_safety -->
```python
import asyncio
from typing import List
from aiothreads import threaded


@threaded
def process_numbers(numbers: List[int], multiplier: float = 1.0) -> List[float]:
    return [n * multiplier for n in numbers]


async def main():
    result = await process_numbers([1, 2, 3], 2.5)
    assert result == [2.5, 5.0, 7.5]


asyncio.run(main())
```

### Separate Thread Execution

Use `@threaded_separate` to run functions in completely separate threads (not the thread pool):

<!-- name: test_separate_thread_generator -->
```python
import asyncio
import io
import time
from aiothreads import threaded_iterable_separate


@threaded_iterable_separate
def read_unix_pipe(pipe_path):
    """Simulation of reading from a named pipe"""
    # Simulation of blocking pipe read
    simulated_data = io.StringIO("line1\nline2\nline3\n")
    while True:
        time.sleep(0.01)  # Simulation of blocking call
        line = simulated_data.readline()
        if not line:
            break
        yield line.strip()


async def main():
    received = []
    async for line in read_unix_pipe('/tmp/my_pipe'):
        received.append(line)

    assert received == ["line1", "line2", "line3"]


asyncio.run(main())
```

**Important Notice about Separate Functions**

Functions decorated with `@threaded_separate` and `@threaded_iterable_separate` create **new dedicated threads** for
each call, bypassing the thread pool entirely. This has important implications:

**Use separate threads when:**

- Reading from blocking pipes or streams that may hang
- Performing operations that might block indefinitely
- Working with operations that could exhaust the thread pool

**Resource Control Risks:**

- **No automatic limits**: Unlike thread pools, there's no built-in limit on concurrent separate threads
- **Memory overhead**: Each thread consumes ~8MB of stack space by default
- **OS limits**: You can hit system thread limits (typically 1000-4000 per process)
- **CPU context switching**: Too many threads can degrade performance

**Best Practices:**

- Use regular `@threaded` for most use cases (leverages controlled thread pool)
- Reserve separate variants for genuinely long-running or problematic operations

### Class Method Support

The decorators work seamlessly with class methods and preserve typing:

<!-- name: test_class_method_support -->
```python
import asyncio
from typing import ClassVar
from aiothreads import threaded


class DataProcessor:
    default_timeout: ClassVar[int] = 30

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    @threaded
    def process(self, data: str) -> dict:
        return {"result": data.upper()}

    @threaded
    @staticmethod
    def utility_function(value: int) -> int:
        return value * 2

    @threaded
    @classmethod
    def from_config(cls, config: dict) -> 'DataProcessor':
        return cls(**config)


async def main():
    processor = DataProcessor()

    result: dict = await processor.process("data")
    assert result == {"result": "DATA"}

    utility_result: int = await processor.utility_function(10)
    assert utility_result == 20

    new_processor: DataProcessor = await DataProcessor.from_config({"default_timeout": 60})
    assert isinstance(new_processor, DataProcessor)


asyncio.run(main())
```

**Object Interface for All Decorators**

All decorated functions become wrapper objects with consistent interfaces:

<!-- name: test_object_interface -->
```python
import asyncio
from typing import Generator
from aiothreads import threaded, threaded_iterable, Threaded, ThreadedIterable


@threaded
def sync_function(x: int) -> str:
    return str(x)


@threaded_iterable
def sync_generator(n: int) -> Generator[int, None, None]:
    for i in range(n):
        yield i


async def main():
    # Both have the same interface pattern:
    assert isinstance(sync_function, Threaded)
    assert isinstance(sync_generator, ThreadedIterable)

    # All support sync_call and async_call
    sync_result = sync_function.sync_call(42)
    assert sync_result == "42"
    async_result = await sync_function.async_call(42)
    assert async_result == "42"
    default_result = await sync_function(42)  # Same as async_call
    assert default_result == "42"

    # Generators become async iterators when called
    sync_gen = sync_generator.sync_call(5)  # Regular generator
    assert list(sync_gen) == [0, 1, 2, 3, 4]


asyncio.run(main())
```

### Sync and Async Calling

Threaded functions provide both sync and async interfaces with full type safety:

<!-- name: test_sync_and_async_calling -->
```python
import asyncio
from typing import Dict, Any
from aiothreads import threaded


@threaded
def compute(x: int, y: int) -> Dict[str, Any]:
    return {"sum": x + y, "product": x * y}


async def main():
    # Async call (default) - returns Awaitable[Dict[str, Any]]
    result = await compute(1, 2)
    assert result == {"sum": 3, "product": 2}

    # Explicit async call - same type signature
    result = await compute.async_call(1, 2)
    assert result == {"sum": 3, "product": 2}

    # Synchronous call (bypasses threading) - returns Dict[str, Any]
    result = compute.sync_call(1, 2)
    assert result == {"sum": 3, "product": 2}


asyncio.run(main())
```

**Type Preservation**

The wrapper objects maintain the original function signatures for type checkers:

<!-- name: test_type_preservation -->
```python
import asyncio
from typing import Any
from aiothreads import threaded


@threaded
def complex_function(
    required_arg: str,
    optional_arg: int | None = None,
    *args: str,
    **kwargs: str | int
) -> dict[str, Any]:
    return {"args": args, "kwargs": kwargs}


async def main():
    result = await complex_function("hello", 42, "a", "b", key="value")
    assert result == {"args": ("a", "b"), "kwargs": {"key": "value"}}

    # Type checker sees the same signature for all call methods
    result = complex_function.sync_call("test")
    assert result == {"args": (), "kwargs": {}}


asyncio.run(main())
```

## Working With Synchronous Generators

### The `@threaded_iterable` Decorator

Convert sync generators to async iterators:

<!-- name: test_crawl_api_pages -->
```python
import asyncio
import time
from aiothreads import threaded_iterable


# Simulation of paginated API data
PAGES = {
    1: {'items': [{'id': 1}, {'id': 2}], 'total_pages': 3},
    2: {'items': [{'id': 3}, {'id': 4, 'type': 'target_item'}], 'total_pages': 3},
    3: {'items': [{'id': 5}, {'id': 6}], 'total_pages': 3},
}


def fetch_page(url):
    """Simulation of blocking HTTP request"""
    time.sleep(0.01)  # Simulation of blocking call
    page = int(url.split("page=")[1])
    return PAGES.get(page, {})


# If you want to prefetch data from an API with pagination more than 1 next page at a time, you can set
# `max_size` parameter to 10 for example.
@threaded_iterable(max_size=1)
def crawl_api_pages(base_url, start_page=1):
    """Recursively fetch API pages until no more data"""
    page = start_page
    while True:
        url = f"{base_url}?page={page}"
        data = fetch_page(url)

        if not data.get('items'):  # No more data
            break

        # Yield each item from this page
        for item in data['items']:
            yield item

        page += 1
        if page > data.get('total_pages', page):
            break


async def main():
    """Process API data with the ability to stop early"""
    processed_count = 0

    async for item in crawl_api_pages('https://api.example.com/data'):
        processed_count += 1

        # Break early if we find what we need
        if item.get('type') == 'target_item':
            break  # This automatically stops the sync generator!

    assert processed_count == 4


asyncio.run(main())
```

**Key Benefit**: When you break from the async loop, the sync generator automatically stops execution. No more HTTP
requests will be made, and resources are properly cleaned up.

### Backpressure Control

Control memory usage with the `max_size` parameter:

**Default Queue Size Configuration**

When using `@threaded` decorator with generator functions (auto-converted to `@threaded_iterable`), the default
`max_size` can be controlled via environment variable:

```bash
# Set before running your application
export THREADED_ITERABLE_DEFAULT_MAX_SIZE=512
python your_app.py
```

- Default value: 1024 if not set
- Explicit `max_size` parameter always overrides the default

<!-- name: test_backpressure -->
```python
import asyncio
import time
from aiothreads import threaded_iterable


def fetch_search_page(query, page):
    """Simulation of blocking search API call"""
    time.sleep(0.01)  # Simulation of blocking call
    if page > 3:
        return {'items': []}
    return {
        'items': [
            {'title': f'Result {i}', 'url': f'http://example.com/{i}', 'snippet': f'{query} snippet'}
            for i in range((page - 1) * 2, page * 2)
        ],
    }


@threaded_iterable(max_size=50)
def scrape_search_results(query, max_pages=None):
    """Scrape search results with bounded memory usage"""
    page = 1

    while max_pages is None or page <= max_pages:
        results = fetch_search_page(query, page)

        if not results.get('items'):
            break  # No more results

        for item in results['items']:
            yield {
                'title': item['title'],
                'url': item['url'],
                'snippet': item['snippet'],
                'page': page
            }

        page += 1


# Queue won't grow beyond 50 items, even with slow consumer
async def main():
    query = "python asyncio"
    processed = 0

    async for result in scrape_search_results(query, max_pages=100):
        processed += 1

        # Can break early and stop all requests
        if processed >= 4:
            break  # No more scraping will happen

    assert processed == 4


asyncio.run(main())
```

### Context Manager Support

Async iterators support proper cleanup:

<!-- name: test_context_manager -->
```python
import asyncio
import time
from aiothreads import threaded_iterable


# Simulation of paginated API data
USERS_DB = [
    [{'name': 'Alice', 'role': 'user'}, {'name': 'Bob', 'role': 'user'}],
    [{'name': 'Charlie', 'role': 'admin'}],
]
cleanup_called = False


@threaded_iterable
def fetch_paginated_data(api_endpoint):
    """Fetch data with automatic session management"""
    global cleanup_called
    try:
        for page_data in USERS_DB:
            time.sleep(0.01)  # Simulation of blocking call
            for record in page_data:
                yield record
    finally:
        cleanup_called = True  # Always cleanup session


async def main():
    global cleanup_called

    # Process data with guaranteed cleanup
    count = 0
    async with fetch_paginated_data('/api/users') as user_stream:
        async for user in user_stream:
            count += 1

            # Early termination still triggers cleanup
            if user.get('role') == 'admin':
                break  # Session will be properly closed

    assert count == 3
    assert cleanup_called


asyncio.run(main())
```

### Separate Thread Generators

For complete isolation:

<!-- name: test_separate_thread_iterable -->
```python
import asyncio
import time
from aiothreads import threaded_iterable_separate


def heavy_computation(i):
    """Simulation of CPU-intensive computation"""
    time.sleep(0.001)  # Simulation of blocking call
    return i * i


@threaded_iterable_separate(max_size=50)
def cpu_intensive_generator():
    """Runs in dedicated thread, not thread pool"""
    for i in range(10):
        yield heavy_computation(i)


async def main():
    results = []
    async for item in cpu_intensive_generator():
        results.append(item)
    assert results == [i * i for i in range(10)]


asyncio.run(main())
```

**Resource Control Warning**

`@threaded_iterable_separate` creates a new dedicated thread for each iterator instance. Multiple concurrent iterations
can quickly exhaust system resources:

<!-- name: test_resource_control -->
```python
import asyncio
import time
from aiothreads import threaded_iterable_separate, threaded_iterable


def expensive_operation(i):
    """Simulation of expensive operation"""
    time.sleep(0.001)  # Simulation of blocking call
    return i


@threaded_iterable_separate
def data_stream():
    # Each async iteration creates a new thread
    for i in range(5):
        yield expensive_operation(i)


# SAFER: Use regular threaded_iterable with controlled concurrency
@threaded_iterable(max_size=100)
def safer_data_stream():
    for i in range(5):
        yield expensive_operation(i)


async def main():
    results = []
    async for item in safer_data_stream():
        results.append(item)
    assert results == [0, 1, 2, 3, 4]


asyncio.run(main())
```

Reserve `threaded_iterable_separate` for cases where you specifically need each generator to run in complete isolation
from the thread pool.

## Calling Async Code from Threads

When working in threaded functions, you can call back into async code:

### Basic Async Calls

<!-- name: test_sync_await -->
```python
import asyncio
import time
from aiothreads import sync_await, threaded


def blocking_operation():
    time.sleep(0.01)  # Simulation of blocking call
    return {"key": "value"}


async def async_api_call(data):
    """Simulation of async API call"""
    await asyncio.sleep(0.01)  # Simulation of async I/O
    return {**data, "processed": True}


def process_result(data):
    return data


@threaded
def mixed_sync_async_work():
    # Do some sync work
    sync_result = blocking_operation()

    # Call async function from thread
    # Event loop is automatically available from context
    async_result = sync_await(async_api_call, sync_result)

    # Continue with sync work
    return process_result(async_result)


async def main():
    result = await mixed_sync_async_work()
    assert result == {"key": "value", "processed": True}


asyncio.run(main())
```

### Event Loop Context

`@threaded` decorated functions automatically store the current event loop in context variables, making it available for
async calls within the thread:

<!-- name: test_event_loop_context -->
```python
import asyncio
from aiothreads import threaded, sync_await, wait_coroutine


async def some_async_function(arg):
    return f"async_{arg}"


async def another_async_function(arg):
    return f"awaited_{arg}"


@threaded
def thread_with_async_calls():
    # Event loop is automatically available
    result1 = sync_await(some_async_function, "arg1")
    result2 = wait_coroutine(another_async_function("arg2"))
    return result1 + result2


async def main():
    result = await thread_with_async_calls()
    assert result == "async_arg1awaited_arg2"


asyncio.run(main())
```

### Using with `asyncio.to_thread`

When using the sync-to-async bridge functions with `asyncio.to_thread`, you need to manually pass the event loop:

<!-- name: test_asyncio_to_thread_usage -->
```python
import asyncio
from aiothreads import sync_wait_coroutine


async def async_function():
    await asyncio.sleep(0.01)
    return "async result"


current_loop = None


def sync_function_for_to_thread():
    # Must get and pass event loop manually
    return sync_wait_coroutine(current_loop, async_function)


async def main():
    global current_loop

    # Using asyncio.to_thread - requires manual loop setting
    current_loop = asyncio.get_running_loop()
    result = await asyncio.to_thread(sync_function_for_to_thread)
    assert result == "async result"


asyncio.run(main())
```

### Coroutine Waiting

<!-- name: test_coroutine_waiting -->
```python
import asyncio
from aiothreads import wait_coroutine, threaded


@threaded
def thread_worker():
    # Create and wait for a coroutine
    # Event loop is automatically available from context
    async def fetch_data():
        await asyncio.sleep(0.01)
        return "data"

    result = wait_coroutine(fetch_data())
    return result


# When using with asyncio.to_thread, manual loop passing required
def manual_thread_worker(loop):
    async def fetch_data():
        return "data from specific loop"

    from aiothreads import sync_wait_coroutine
    result = sync_wait_coroutine(loop, fetch_data)
    return result


async def main():
    # Automatic loop handling with @threaded
    result1 = await thread_worker()
    assert result1 == "data"

    # Manual loop handling with asyncio.to_thread
    loop = asyncio.get_running_loop()
    result2 = await asyncio.to_thread(manual_thread_worker, loop)
    assert result2 == "data from specific loop"


asyncio.run(main())
```

### Context Variables

Context variables are properly propagated:

<!-- name: test_context_variables -->
```python
import asyncio
import contextvars
from aiothreads import threaded

user_context = contextvars.ContextVar('user')


@threaded
def process_user_data(data):
    # Context variable is available in thread
    current_user = user_context.get()
    return f"Processing {data} for {current_user}"


async def main():
    user_context.set("alice")

    # Context propagates to thread
    result = await process_user_data("report")
    assert result == "Processing report for alice"


asyncio.run(main())
```

## Advanced Usage

### FromThreadChannel with Timeout

The `FromThreadChannel` class provides efficient event-based communication from threads to async code.
It uses `asyncio.Event` instead of polling for immediate wake-up when data is available.

<!-- name: test_from_thread_channel -->
```python
import asyncio
from aiothreads import FromThreadChannel, ChannelClosed, ChannelTimeout, threaded


async def main():
    # Basic usage with timeout
    channel = FromThreadChannel(maxsize=10, timeout=5.0)

    @threaded
    def producer():
        with channel:
            for i in range(10):
                channel.put(i)

    producer()

    results = []
    try:
        while True:
            item = await channel.get()
            results.append(item)
    except ChannelClosed:
        pass

    assert results == list(range(10))

    # Override timeout per-call
    channel2 = FromThreadChannel(timeout=10.0)

    try:
        await channel2.get(timeout=0.01)
        assert False, "Should have raised ChannelTimeout"
    except ChannelTimeout:
        pass  # Expected: timed out after 0.01 seconds


asyncio.run(main())
```

**Timeout Behavior:**
- `timeout=0` (default): No timeout, wait indefinitely
- `timeout=N`: Wait up to N seconds, then raise `ChannelTimeout`
- Per-call timeout overrides the default set in constructor

### Error Handling

<!-- name: test_error_handling -->
```python
import asyncio
from aiothreads import threaded


@threaded
def risky_operation(should_fail: bool = False):
    if should_fail:
        raise ValueError("Something went wrong")
    return "success"


async def main():
    result = await risky_operation(should_fail=False)
    assert result == "success"

    try:
        await risky_operation(should_fail=True)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert str(e) == "Something went wrong"


asyncio.run(main())
```

### Performance Considerations

<!-- name: test_performance -->
```python
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from aiothreads import threaded, threaded_separate


# For CPU-bound tasks, consider using threaded_separate
@threaded_separate
def cpu_bound_task(data):
    time.sleep(0.01)  # Simulation of CPU-intensive work
    return data * 2


# For I/O bound tasks, regular threaded is usually sufficient
@threaded
def io_bound_task(url):
    time.sleep(0.01)  # Simulation of blocking I/O
    return f"response from {url}"


async def main():
    # Control thread pool size at the event loop level
    loop = asyncio.get_running_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=10))

    cpu_result = await cpu_bound_task(21)
    assert cpu_result == 42

    io_result = await io_bound_task("http://example.com")
    assert io_result == "response from http://example.com"


asyncio.run(main())
```
