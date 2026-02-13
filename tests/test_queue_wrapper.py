import pytest
from queue import Empty as QueueEmpty

from aiothreads.iterator_wrapper import QueueWrapperBase


def test_put_not_implemented():
    base = QueueWrapperBase()
    with pytest.raises(NotImplementedError):
        base.put(1)


def test_get_not_implemented():
    base = QueueWrapperBase()
    with pytest.raises(NotImplementedError):
        base.get()
