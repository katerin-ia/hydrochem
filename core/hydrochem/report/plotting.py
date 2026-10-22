"""Serialize pyplot operations shared by concurrent web export requests."""
from functools import wraps
from threading import RLock

_lock = RLock()


def serialized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with _lock:
            return function(*args, **kwargs)
    return wrapped
