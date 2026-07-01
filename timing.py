from contextlib import contextmanager
from time import perf_counter
from functools import wraps

@contextmanager
def timer(name):
    start = perf_counter()
    yield
    elapsed = perf_counter() - start
    print(f"{name:<30} {elapsed*1000:8.2f} ms")


def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = perf_counter()
        result = func(*args, **kwargs)
        print(
            f"{func.__name__}: "
            f"{(perf_counter()-start)*1000:.1f} ms"
        )
        return result
    return wrapper
