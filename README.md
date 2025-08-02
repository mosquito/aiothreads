# aiothreads Documentation

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

```python
import asyncio


async def with_to_thread():
    # Only works for simple functions
    # No support for generators
    result = await asyncio.to_thread(sync_function, arg1, arg2)
```

**aiothreads - comprehensive solution**

```python
import asyncio
from aiothreads import threaded, threaded_iterable, sync_await


@threaded
def mixed_sync_async():
    sync_result = blocking_operation()

    # Calling async code from thread
    sync_await(asyncio.sleep, 1)
    return sync_result


@threaded_iterable(max_size=100)
def data_stream():
    # Automatic backpressure control
    for item in expensive_data_source():
        yield item


async def with_aiothreads():
    # Rich functionality with clean syntax
    result = await mixed_sync_async()

    # Stream processing with memory control
    count = 0
    async for item in data_stream():
        count += 1
        if count > 10:
            break  # Automatically stops sync generator thread execution!
        print(item)
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

```python
import asyncio
import time
from aiothreads import threaded


@threaded
def cpu_intensive_task(n):
    """A blocking function that will run in a thread"""
    time.sleep(1)  # Simulate CPU work
    return n * n


async def main():
    # Run multiple blocking operations concurrently
    tasks = [cpu_intensive_task(i) for i in range(5)]
    results = await asyncio.gather(*tasks)
    print(results)  # [0, 1, 4, 9, 16]


asyncio.run(main())
```

## Working With Threads

### Choosing the Right Decorator

| Use Case                      | Recommended Decorator         | Reason                                           |
|-------------------------------|-------------------------------|--------------------------------------------------|
| Short I/O operations (< 30s)  | `@threaded`                   | Efficient resource reuse                         |
| CPU-bound tasks (< 30s)       | `@threaded`                   | Controlled concurrency                           |
| Blocking pipe/stream reading  | `@threaded_separate`          | Won't block thread pool create a separate thread |
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

```python
from aiothreads import threaded
import requests


@threaded
def fetch_url(url: str) -> str:
    """Blocking HTTP request"""
    response = requests.get(url)
    return response.text


# The decorated function becomes a Threaded object with multiple call methods
async def fetch_multiple():
    urls = ['http://example.com', 'http://httpbin.org/json']

    # Both requests run concurrently in separate threads
    results = await asyncio.gather(*[fetch_url(url) for url in urls])
    return results
```

**Decorated Function Interface**

When you decorate a function with `@threaded`, it becomes a `Threaded` object with three calling methods:

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

    # 2. Explicit async call 
    result = await compute.async_call(1, 2)

    # 3. Accessing the sync call method
    # This runs the function as usual, blocking the thread
    # and returning the result directly
    result = compute.sync_call(1, 2)


asyncio.run(main())
```

**Type Safety**

The decorators preserve type information for static type checkers:

```python
from typing import List
from aiothreads import threaded


@threaded
def process_numbers(numbers: List[int], multiplier: float = 1.0) -> List[float]:
    return [n * multiplier for n in numbers]


# Type checker knows the return type
async def example():
    # Type checker knows this returns List[float]
    result = await process_numbers([1, 2, 3], 2.5)

    # This would cause a type error
    # bad_result = await process_numbers("not a list", 2.5)  # Type error!

    return result
```

### Separate Thread Execution

Use `@threaded_separate` to run functions in completely separate threads (not the thread pool):

```python
import asyncio
from aiothreads import threaded_separate


@threaded_separate
def read_unix_pipe(pipe_path):
    """Read from a named pipe that might block indefinitely"""
    # Opening a FIFO pipe blocks until a writer connects
    with open(pipe_path, 'r') as pipe:
        while True:
            line = pipe.readline()
            if not line:
                break
            yield line.strip()


async def main():
    async for line in read_unix_pipe('/tmp/my_pipe'):
        print(f"Received line: {line}")


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

```python
from typing import ClassVar
from aiothreads import threaded


class DataProcessor:
    default_timeout: ClassVar[int] = 30

    @threaded
    def process(self, data: str) -> dict:
        return expensive_computation(data)

    @threaded
    @staticmethod
    def utility_function(value: int) -> int:
        return value * 2

    @threaded
    @classmethod
    def from_config(cls, config: dict) -> 'DataProcessor':
        return cls(**config)


# Usage with full type safety
async def example():
    processor = DataProcessor()

    # Type checker knows the return types
    result: dict = await processor.process("data")
    utility_result: int = await processor.utility_function(10)
    new_processor: DataProcessor = await DataProcessor.from_config({"default_timeout": 60})
```

**Object Interface for All Decorators**

All decorated functions become wrapper objects with consistent interfaces:

```python
import asyncio
from typing import Generator
from aiothreads import threaded, threaded_iterable


@threaded
def sync_function(x: int) -> str:
    return str(x)


@threaded_iterable
def sync_generator(n: int) -> Generator[int, None, None]:
    for i in range(n):
        yield i


async def main():
    # Both have the same interface pattern:
    print(type(sync_function))
    print(type(sync_generator))

    # All support sync_call and async_call
    sync_result = sync_function.sync_call(42)
    async_result = await sync_function.async_call(42)
    default_result = await sync_function(42)  # Same as async_call

    # Generators become async iterators when called
    sync_gen = sync_generator.sync_call(5)  # Regular generator
    async_iter = sync_generator(5)  # IteratorWrapper (async iterator)


asyncio.run(main())
```

### Sync and Async Calling

Threaded functions provide both sync and async interfaces with full type safety:

```python
from typing import Dict, Any
from aiothreads import threaded


@threaded
def compute(x: int, y: int) -> Dict[str, Any]:
    return {"sum": x + y, "product": x * y}


async def example_usage():
    # Async call (default) - returns Awaitable[Dict[str, Any]]
    result = await compute(1, 2)

    # Explicit async call - same type signature
    result = await compute.async_call(1, 2)

    # Synchronous call (bypasses threading) - returns Dict[str, Any]
    result = compute.sync_call(1, 2)
```

**Type Preservation**

The wrapper objects maintain the original function signatures for type checkers:

```python
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

# Type checker sees the same signature for all call methods:
# complex_function.sync_call(required_arg: str, optional_arg: Optional[int] = None, *args: str, **kwargs: Union[str, int]) -> Dict[str, Any]
# complex_function.async_call(required_arg: str, optional_arg: Optional[int] = None, *args: str, **kwargs: Union[str, int]) -> Awaitable[Dict[str, Any]]
# complex_function.__call__(required_arg: str, optional_arg: Optional[int] = None, *args: str, **kwargs: Union[str, int]) -> Awaitable[Dict[str, Any]]
```

## Working With Synchronous Generators

### The `@threaded_iterable` Decorator

Convert sync generators to async iterators:

```python
from aiothreads import threaded_iterable
import requests


# If you want to prefetch data from an API with pagination more than 1 next page at a time, you can set
# `max_size` parameter to 10 for example.
@threaded_iterable(max_size=1)
def crawl_api_pages(base_url, start_page=1):
    """Recursively fetch API pages until no more data"""
    page = start_page
    while True:
        url = f"{base_url}?page={page}"
        response = requests.get(url)

        if response.status_code != 200:
            break

        data = response.json()
        if not data.get('items'):  # No more data
            break

        # Yield each item from this page
        for item in data['items']:
            yield item

        page += 1
        if page > data.get('total_pages', page):
            break


async def process_api_data():
    """Process API data with the ability to stop early"""
    processed_count = 0

    async for item in crawl_api_pages('https://api.example.com/data'):
        await process_item(item)
        processed_count += 1

        # Break early if we find what we need
        if item.get('type') == 'target_item':
            print(f"Found target after {processed_count} items")
            break  # This automatically stops the sync generator!

        # Or stop after processing enough items
        if processed_count >= 1000:
            print("Processed enough items")
            break  # Generator stops, no more HTTP requests made
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

```python
from aiothreads import threaded_iterable


@threaded_iterable(max_size=50)
def scrape_search_results(query, max_pages=None):
    """Scrape search results with bounded memory usage"""
    session = requests.Session()
    page = 1

    try:
        while max_pages is None or page <= max_pages:
            url = f"https://api.search.com/v1/search?q={query}&page={page}"
            response = session.get(url)

            if response.status_code != 200:
                break

            results = response.json()

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
    finally:
        session.close()


# Queue won't grow beyond 50 items, even with slow consumer
async def process_search_results():
    query = "python asyncio"
    processed = 0

    async for result in scrape_search_results(query, max_pages=100):
        # Slow processing - but generator pauses when queue is full
        await asyncio.sleep(0.1)
        await save_result_to_db(result)

        processed += 1

        # Can break early and stop all HTTP requests
        if processed >= 500:
            print(f"Collected enough results from page {result['page']}")
            break  # No more scraping will happen
```

### Context Manager Support

Async iterators support proper cleanup:

```python
from aiothreads import threaded_iterable


@threaded_iterable
def fetch_paginated_data(api_endpoint):
    """Fetch data with automatic session management"""
    session = requests.Session()
    session.headers.update({'Authorization': 'Bearer token'})

    try:
        page = 1
        while True:
            response = session.get(f"{api_endpoint}?page={page}")

            if response.status_code != 200:
                break

            data = response.json()

            for record in data.get('records', []):
                yield record

            # Check if there are more pages
            if not data.get('has_next', False):
                break

            page += 1
    finally:
        session.close()  # Always cleanup session


async def stream_data_safely():
    """Process data with guaranteed cleanup"""
    count = 0

    async with fetch_paginated_data('/api/users') as user_stream:
        async for user in user_stream:
            await process_user(user)
            count += 1

            # Early termination still triggers cleanup
            if user.get('role') == 'admin':
                break  # Session will be properly closed

    print(f"Processed {count} users, session cleaned up")


# Alternative without context manager
async def stream_data_with_break():
    """Breaking from loop also triggers cleanup"""
    async for record in fetch_paginated_data('/api/data'):
        if record.get('error'):
            break  # Generator stops, session.close() called automatically

        await process_record(record)
```

### Separate Thread Generators

For complete isolation:

```python
from aiothreads import threaded_iterable_separate


@threaded_iterable_separate(max_size=50)
def cpu_intensive_generator():
    """Runs in dedicated thread, not thread pool"""
    for i in range(1000):
        yield heavy_computation(i)
```

**Resource Control Warning**

`@threaded_iterable_separate` creates a new dedicated thread for each iterator instance. Multiple concurrent iterations
can quickly exhaust system resources:

```python
from aiothreads import threaded_iterable_separate, threaded_iterable


@threaded_iterable_separate
def data_stream():
    # Each async iteration creates a new thread
    for i in range(1000000):
        yield expensive_operation(i)


# DANGEROUS: This could create 100 separate threads!
async def dangerous_pattern():
    iterators = [data_stream() for _ in range(100)]
    # Each iterator gets its own dedicated thread


# SAFER: Use regular threaded_iterable with controlled concurrency
@threaded_iterable(max_size=100)
def safer_data_stream():
    for i in range(1000000):
        yield expensive_operation(i)
```

Reserve `threaded_iterable_separate` for cases where you specifically need each generator to run in complete isolation
from the thread pool.

## Calling Async Code from Threads

When working in threaded functions, you can call back into async code:

### Basic Async Calls

```python
from aiothreads import sync_await, threaded


@threaded
def mixed_sync_async_work():
    # Do some sync work
    sync_result = blocking_operation()

    # Call async function from thread
    # Event loop is automatically available from context
    async_result = sync_await(async_api_call, sync_result)

    # Continue with sync work
    return process_result(async_result)


async def async_api_call(data):
    # This runs in the event loop
    async with aiohttp.ClientSession() as session:
        async with session.post('/api', json=data) as resp:
            return await resp.json()
```

### Event Loop Context

`@threaded` decorated functions automatically store the current event loop in context variables, making it available for
async calls within the thread:

```python
import asyncio
from aiothreads import sync_await, wait_coroutine


@threaded
def thread_with_async_calls():
    # Event loop is automatically available
    result1 = sync_await(some_async_function, "arg1")
    result2 = wait_coroutine(another_async_function("arg2"))
    return result1 + result2


# Works seamlessly
async def main():
    result = await thread_with_async_calls()
    print(result)
```

### Using with `asyncio.to_thread`

When using the sync-to-async bridge functions with `asyncio.to_thread`, you need to manually pass the event loop:

```python
import asyncio
from aiothreads import sync_wait_coroutine


async def async_function():
    await asyncio.sleep(1)
    return "async result"


currnet_loop = None


def sync_function_for_to_thread():
    # Must get and pass event loop manually
    return sync_wait_coroutine(currnet_loop, async_function)


async def example_with_to_thread():
    global currnet_loop

    # Using asyncio.to_thread - requires manual loop setting
    currnet_loop = asyncio.get_running_loop()
    await asyncio.to_thread(sync_function_for_to_thread)
```

### Coroutine Waiting

```python
import asyncio
from aiothreads import wait_coroutine, threaded


@threaded
def thread_worker():
    # Create and wait for a coroutine
    # Event loop is automatically available from context
    async def fetch_data():
        await asyncio.sleep(1)
        return "data"

    result = wait_coroutine(fetch_data())
    return result


# When using with asyncio.to_thread, manual loop passing required
def manual_thread_worker():
    loop = asyncio.get_running_loop()

    async def fetch_data():
        return "data from specific loop"

    from aiothreads import sync_wait_coroutine
    result = sync_wait_coroutine(loop, fetch_data)
    return result


async def comparison_example():
    # Automatic loop handling with @threaded
    result1 = await thread_worker()

    # Manual loop handling with asyncio.to_thread
    result2 = await asyncio.to_thread(manual_thread_worker)

    return result1, result2
```

### Context Variables

Context variables are properly propagated:

```python
import contextvars
from aiothreads import threaded

user_context = contextvars.ContextVar('user')


@threaded
def process_user_data(data):
    # Context variable is available in thread
    current_user = user_context.get()
    return f"Processing {data} for {current_user}"


async def handle_request(user_id, data):
    user_context.set(user_id)

    # Context propagates to thread
    result = await process_user_data(data)
    return result
```

## Advanced Usage

### Error Handling

```python
import random
from aiothreads import threaded


@threaded
def risky_operation():
    if random.random() < 0.5:
        raise ValueError("Something went wrong")
    return "success"


async def handle_errors():
    try:
        result = await risky_operation()
        print(f"Success: {result}")
    except ValueError as e:
        print(f"Handled error: {e}")
```

### Performance Considerations

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

import requests
from aiothreads import threaded, threaded_separate


# For CPU-bound tasks, consider using threaded_separate
@threaded_separate
def cpu_bound_task(data):
    return expensive_cpu_work(data)


# For I/O bound tasks, regular threaded is usually sufficient
@threaded
def io_bound_task(url):
    return requests.get(url)


# Control thread pool size at the event loop level
loop = asyncio.get_event_loop()
loop.set_default_executor(ThreadPoolExecutor(max_workers=10))
```
