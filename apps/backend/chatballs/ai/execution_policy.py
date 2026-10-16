"""A scoped guard for autonomous work; assistance and analysis remain independent."""

from contextlib import contextmanager
from contextvars import ContextVar

from chatballs.ai.provider.base import ProviderRejected

_guard = ContextVar("autonomous_execution_guard", default=None)


def check_execution():
    guard = _guard.get()
    if guard is not None and not guard():
        raise ProviderRejected("autonomous turn cancelled")


@contextmanager
def execution_guard(check):
    token = _guard.set(check)
    try:
        check_execution()
        yield
    finally:
        _guard.reset(token)
