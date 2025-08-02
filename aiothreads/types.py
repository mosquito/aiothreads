import asyncio
import contextvars
from typing import Any, Callable, Generator, ParamSpec, TypeVar


# ParamSpec for functions
P = ParamSpec("P")

# bounded ParamSpec for bound methods
BP = ParamSpec("BP")
T = TypeVar("T")
S = TypeVar("S", bound=object)
F = TypeVar("F", bound=Callable[..., Any])
R = TypeVar("R")
GenType = Generator[T, None, None]
FuncType = Callable[[], GenType]

# Context variable to store the current event loop
EVENT_LOOP: contextvars.ContextVar[asyncio.AbstractEventLoop] = contextvars.ContextVar("event_loop")
